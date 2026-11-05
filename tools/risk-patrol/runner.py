"""Local patrol: collect candidates or submit explicitly verified events.
No search result is classified automatically. Formal alerts require staff confirmation.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from mcp_client import LocalMcpClient, all_items
from tavily_client import TavilyClient, collect
from schedule import SlotStore, latest_slot
from patrol_state import PatrolState
from urllib.parse import urlsplit


def timestamp():
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')


def eligible(rows):
    return [p for p in rows if str(p.get('is_after_invest')) == '1'
            and str(p.get('del_flag', '0')) == '0']


def validate_candidates(value):
    if not isinstance(value, dict) or set(value) != {'schemaVersion', 'projects'} or value['schemaVersion'] != 1:
        raise ValueError('候选文件格式无效')
    if not isinstance(value['projects'], dict):
        raise ValueError('候选项目映射无效')
    for pid, rows in value['projects'].items():
        if not isinstance(pid, str) or not pid or not isinstance(rows, list):
            raise ValueError('候选项目格式无效')
        for row in rows:
            if (not isinstance(row, dict) or set(row) - {'url', 'title', 'content', 'publishedDate'}
                    or not {'url', 'title', 'content'} <= set(row)
                    or any(not isinstance(row[k], str) for k in ('url', 'title', 'content'))
                    or urlsplit(row['url']).scheme not in ('http', 'https')
                    or not urlsplit(row['url']).netloc
                    or (row.get('publishedDate') is not None and not isinstance(row['publishedDate'], str))):
                raise ValueError('候选证据格式无效')
    return value['projects']


def plugin_coverage(client, evidence, events, slot, now):
    if not isinstance(evidence, dict) or evidence.get('schemaVersion') != 2:
        return None
    if set(evidence) != {'schemaVersion','projects','receipts'}:
        raise ValueError('插件采集凭证格式无效')
    projects = validate_candidates({'schemaVersion':1,'projects':evidence['projects']})
    receipts = evidence['receipts']
    rows = all_items(client, 'agent_portfolio_list', {'afterInvestOnly': True})
    ids = {p.get('projectId') or p.get('id') for p in eligible(rows)}
    if set(projects) != ids or not isinstance(receipts,dict) or set(receipts) != ids:
        raise ValueError('插件采集未完整覆盖投后名单')
    event_ids = {e.get('projectId') for e in events}
    skipped = set()
    names = {p.get('projectId') or p.get('id'):p.get('project_name','') for p in rows}
    for pid in ids:
        receipt = receipts[pid]
        if isinstance(receipt,dict) and receipt.get('conclusion') == 'skip_test_project':
            import re
            if (not re.search(r'QA|模拟|验收|测试|qat9|青云智行',names.get(pid,'')) or projects[pid]
                    or pid in event_ids or receipt.get('source') != 'test_scope' or not receipt.get('reason')):
                raise ValueError('仅明确测试项目可跳过外部检索')
            skipped.add(pid)
            continue
        if (not isinstance(receipt,dict) or receipt.get('source') != 'tavily_plugin'
                or receipt.get('reviewed') is not True or not isinstance(receipt.get('query'),str)
                or not receipt['query'].strip()
                or receipt.get('conclusion') != ('events' if pid in event_ids else 'no_anomaly')):
            raise ValueError('插件采集须逐项目核实结论')
        when = datetime.fromisoformat(receipt.get('searchedAt',''))
        if when.tzinfo is None or not datetime.fromisoformat(slot) <= when <= now:
            raise ValueError('插件采集时间不属于当前巡检时段')
    return ({'schemaVersion':1,'projects':projects}, skipped)


def execute_due(client, search, store, now, events=None, candidates=None):
    health = client.call('agent_health')
    tenant = health.get('customerId')
    if not tenant:
        raise ValueError('租户未知')
    config = client.call('risk_config_get')
    slot = latest_slot(config.get('patrolTimes'), now)
    if not store.claim(tenant, slot, now.timestamp()):
        return {'mode': 'not_due', 'errors': 0, 'slot': slot}
    health_state = None
    try:
        health_state = PatrolState(store.db.execute('PRAGMA database_list').fetchone()[2] or ':memory:')
        def record_health(rows):
            # Test scope skips are neither searched successes nor search failures.
            for row in rows:
                if row.get('status') in ('ok', 'failed'):
                    row.update(health_state.record(tenant, row['projectId'], now, row['status'] == 'ok'))
        plugin = plugin_coverage(client, candidates, events, slot, now) if events is not None else None
        coverage = execute(client, search, candidates=plugin[0] if plugin else None,
                           skip_test_ids=plugin[1] if plugin else None, health_recorder=record_health) if events is not None else None
        if coverage is not None and coverage['errors']:
            result = coverage
            result['mode'] = 'search_incomplete'
        else:
            result = execute(client, search, events, None if plugin is not None else candidates, health_recorder=record_health if events is None else None)
        if coverage is not None:
            result['coverageRunId'] = coverage['runId']
            result['coverageComplete'] = coverage['errors'] == 0
            result['coverageProjectIds'] = [r['projectId'] for r in coverage['results']]
            result['coverageResults'] = [{k:v for k,v in row.items() if k != 'candidates'} for row in coverage['results']]
        result['retryProjectIds'] = health_state.retry_projects(tenant, now.date().isoformat())
        result['failureAlerts'] = health_state.alerts(tenant)
        store.finish(tenant, slot, result['errors'] == 0 and events is not None and result.get('coverageComplete') is True)
        result['slot'] = slot
        return result
    except Exception:
        store.finish(tenant, slot, False)
        raise
    finally:
        if health_state is not None:
            health_state.db.close()


def execute(client, search, events=None, candidates=None, skip_test_ids=None, health_recorder=None):
    if events is not None and (not isinstance(events, list) or any(not isinstance(e, dict) for e in events)):
        raise ValueError('事件文件须为对象数组')
    if candidates is not None:
        candidates = validate_candidates(candidates)
    started = timestamp()
    config = client.call('risk_config_get')
    rows = all_items(client, 'agent_portfolio_list', {'afterInvestOnly': True})
    projects = eligible(rows)
    ids = {p.get('projectId') or p.get('id') for p in projects}
    run = client.call('risk_run_record', {'runType': 'patrol', 'startedAt': started,
         'scanned': 0, 'hits': 0, 'draftsCreated': 0, 'errors': 0, 'details': []})
    run_id = run['runId']
    created = errors = hits = 0
    details = [{'source': 'risk_tyc_news', 'hits': 0, 'status': 'skipped',
                'error': '新闻源未开通'}]
    if events is None:
        if candidates is None:
            results = collect(projects, search)
        else:
            results = []
            for project in projects:
                pid = project.get('projectId') or project.get('id')
                if skip_test_ids and pid in skip_test_ids:
                    results.append({'projectId':pid,'query':'测试项目不检索外部主体','source':'test_scope','hits':0,'status':'skipped','error':'测试样本，无外部主体'})
                    continue
                def saved_search(query, project_id=pid):
                    if project_id not in candidates:
                        raise ValueError('本项目尚未搜索')
                    return candidates[project_id]
                results.extend(collect([project], saved_search))
        if health_recorder is not None:
            health_recorder(results)
        for row in results:
            hits += row['hits']
            errors += row['status'] == 'failed'
            details.append({k: v for k, v in row.items() if k != 'candidates'})
        mode = 'collect_only'
    else:
        if not isinstance(events, list):
            raise ValueError('事件文件须为数组')
        results = []
        mode = 'verified_events'
        for event in events:
            detail = {'projectId': event.get('projectId'), 'source': 'bot_search',
                      'query': '已核实事件提交', 'hits': 0}
            try:
                if (event.get('verified') is not True or not event.get('rule')
                        or event.get('projectId') not in ids
                        or event.get('grade') not in ('medium', 'high')
                        or not event.get('sources') or not event.get('eventKey')):
                    raise ValueError('事件核实、范围或必填条件不满足')
                fields = ('projectId', 'riskType', 'grade', 'title', 'eventDate',
                          'conclusion', 'sources', 'eventKey', 'stage')
                args = {k: event[k] for k in fields if k in event}
                args.update(source='bot_search', runId=run_id)
                response = client.call('create_risk_draft', args)
                outcome = response.get('result')
                if outcome not in ('created', 'merged', 'upgraded', 'duplicate', 'skipped'):
                    raise ValueError('草稿未被服务端接受')
                created += outcome in ('created', 'upgraded')
                hits += 1
                detail.update(status='ok', hits=1)
                results.append({'projectId': event['projectId'], 'result': outcome})
            except Exception:
                errors += 1
                detail.update(status='failed', error='事件校验或草稿提交失败')
            details.append(detail)
    client.call('risk_run_record', {'runType': 'patrol', 'runId': run_id,
        'endedAt': timestamp(), 'scanned': len(projects), 'hits': hits,
        'draftsCreated': created, 'errors': errors, 'details': details})
    return {'mode': mode, 'runId': run_id, 'scanned': len(projects),
            'hits': hits, 'draftsCreated': created, 'errors': errors,
            'patrolTimes': config.get('patrolTimes'), 'results': results}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--collect-only', action='store_true')
    mode.add_argument('--events', type=Path, help='已核实分级事件JSON数组')
    parser.add_argument('--due', action='store_true', help='按服务端北京时间段认领任务')
    parser.add_argument('--state', type=Path, default=Path.home() / '.qtou-patrol-state.sqlite')
    parser.add_argument('--candidates-file', type=Path, help='插件搜索候选证据，不能用作已核实事件')
    parser.add_argument('--output', type=Path, help='保存候选证据到本地，不在终端打印正文')
    args = parser.parse_args()
    try:
        events = json.loads(args.events.read_text()) if args.events else None
        candidates = json.loads(args.candidates_file.read_text()) if args.candidates_file else None
        if events is not None and candidates is not None and not args.due:
            raise ValueError('插件核实凭证须使用due时段校验')
        client = LocalMcpClient()
        if args.due:
            slot_store = SlotStore(str(args.state))
            try:
                result = execute_due(client, TavilyClient().search, slot_store,
                                     datetime.now(ZoneInfo('Asia/Shanghai')), events, candidates)
            finally:
                slot_store.db.close()
        else:
            result = execute(client, TavilyClient().search, events, candidates)
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            args.output.chmod(0o600)
        print(json.dumps({k: v for k, v in result.items() if k != 'results'}, ensure_ascii=False))
        return 1 if result['errors'] else 0
    except Exception:
        print(json.dumps({'status': 'failed', 'error': '本地巡检未完成，请检查服务与凭据配置'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Tavily 采集层。搜索结果是候选证据，不自动判定风险。"""
import json
import os
import urllib.error
import urllib.request


class SearchUnavailable(RuntimeError):
    pass


class TavilyClient:
    def __init__(self, key=None, opener=None):
        self._key = key or os.environ.get('TAVILY_API_KEY', '')
        self._open = opener or urllib.request.build_opener(NoRedirect()).open

    def search(self, query):
        if not self._key:
            raise SearchUnavailable('Tavily 运行凭据未配置')
        payload = json.dumps({'query': query, 'search_depth': 'advanced',
                              'max_results': 5, 'include_raw_content': False}).encode()
        req = urllib.request.Request('https://api.tavily.com/search', data=payload,
                                     headers={'Authorization': 'Bearer ' + self._key,
                                              'Content-Type': 'application/json'})
        try:
            with self._open(req, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            # Never include server body, request headers, query or credentials.
            status = exc.code
            exc.close()
            raise SearchUnavailable('Tavily HTTP %d' % status) from None
        except Exception:
            raise SearchUnavailable('Tavily 请求失败或响应无效') from None
        results = data.get('results') if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise SearchUnavailable('Tavily 响应缺少结果列表')
        return [{'url': row['url'], 'title': row.get('title', ''),
                 'content': row.get('content', ''),
                 'publishedDate': row.get('published_date')}
                for row in results if isinstance(row, dict)
                and isinstance(row.get('url'), str)
                and row['url'].startswith(('https://', 'http://'))]


def collect(projects, search):
    """Strict scope check even when upstream portfolio filtering is broader."""
    records = []
    for project in projects:
        if str(project.get('is_after_invest')) != '1' or str(project.get('del_flag', '0')) != '0':
            continue
        name = project.get('company_full_name') or project.get('project_name')
        if not name:
            continue
        query = name + ' 处罚 诉讼 被执行 失信 重大公告'
        record = {'projectId': project.get('projectId') or project.get('id'),
                  'query': query, 'source': 'bot_search', 'hits': 0}
        try:
            items = search(query)
            record.update(status='ok', hits=len(items), candidates=items)
        except Exception:
            record.update(status='failed', error='外网检索失败')
        records.append(record)
    return records


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

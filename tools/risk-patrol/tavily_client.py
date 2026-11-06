"""Tavily 采集层。搜索结果是候选证据，不自动判定风险。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qtou_shared  # noqa: E402


class SearchUnavailable(RuntimeError):
    pass


class TavilyClient:
    def __init__(self, key=None, opener=None):
        self._key = key or qtou_shared.tavily_key()
        self._open = opener or qtou_shared.no_redirect_opener()

    def search(self, query):
        if not self._key:
            raise SearchUnavailable('Tavily 运行凭据未配置')
        request = lambda url, payload: qtou_shared.post_json(url, payload, self._key, self._open, timeout=30)
        try:
            rows, _ = qtou_shared.tavily_search(request, query)
        except qtou_shared.HttpFailure as failure:
            # Never include server body, request headers, query or credentials.
            raise SearchUnavailable('Tavily HTTP %d' % failure.status if failure.status else 'Tavily 请求失败或响应无效') from None
        except ValueError:
            raise SearchUnavailable('Tavily 响应缺少结果列表') from None
        return rows


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

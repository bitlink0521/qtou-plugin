import io
import unittest
import urllib.error
from tavily_client import TavilyClient, SearchUnavailable, collect


class SearchTests(unittest.TestCase):
    def test_missing_key(self):
        client = TavilyClient(key='')
        client._key = ''
        with self.assertRaises(SearchUnavailable):
            client.search('测试')

    def test_http_error_never_exposes_secret(self):
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError('https://api.tavily.com/search', 401,
                                         'secret-value', {}, None)
        with self.assertRaises(SearchUnavailable) as caught:
            TavilyClient('secret-value', fail).search('测试')
        self.assertEqual(str(caught.exception), 'Tavily HTTP 401')

    def test_only_valid_source_urls(self):
        def reply(*args, **kwargs):
            return io.BytesIO(b'{"results":[{"url":"https://example.com"},{"url":"javascript:bad"}]}')
        self.assertEqual(len(TavilyClient('test', reply).search('测试')), 1)

    def test_scope_and_failure_isolation(self):
        projects = [{'id': 'a', 'is_after_invest': 0, 'project_name': '未投'},
                    {'id': 'b', 'is_after_invest': 1, 'project_name': '失败'},
                    {'id': 'c', 'is_after_invest': 1, 'project_name': '正常'},
                    {'id': 'd', 'is_after_invest': 1, 'del_flag': 1, 'project_name': '删除'}]
        def search(query):
            if query.startswith('失败'):
                raise RuntimeError('private details')
            return []
        result = collect(projects, search)
        self.assertEqual([r['projectId'] for r in result], ['b', 'c'])
        self.assertEqual([r['status'] for r in result], ['failed', 'ok'])
        self.assertNotIn('private details', str(result))


if __name__ == '__main__':
    unittest.main()

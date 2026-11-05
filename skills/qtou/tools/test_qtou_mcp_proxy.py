import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import qtou_mcp_proxy as proxy

GOOD = 'qtpat_good'


class FakeQtou(BaseHTTPRequestHandler):
    logins = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.path.endswith('/auth/login'):
            FakeQtou.logins.append(body.decode())
            ok = 'password=right' in body.decode()
            reply = {'data': {'agentKey': GOOD}} if ok else {'msg': '密码错误'}
            return self.send_json(200, reply)
        message = json.loads(body)
        if self.headers.get('Authorization') != 'Bearer ' + GOOD:
            return self.send_json(401, {'jsonrpc': '2.0', 'error': {'code': 10007, 'message': 'bad key'}})
        self.send_json(200, {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {'method': message.get('method')}},
                       session='s1')

    def send_json(self, status, payload, session=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        if session:
            self.send_header('Mcp-Session-Id', session)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeQtou)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % cls.server.server_port
        cls.patches = [mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
                       mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login')]
        for patch in cls.patches:
            patch.start()

    @classmethod
    def tearDownClass(cls):
        for patch in cls.patches:
            patch.stop()
        cls.server.shutdown()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.token_patch = mock.patch.object(proxy, 'TOKEN_PATH', os.path.join(self.dir.name, 'qtou', 'connector-token'))
        self.token_patch.start()
        proxy.session.update(id=None, initialize=None)
        FakeQtou.logins = []

    def tearDown(self):
        self.token_patch.stop()
        self.dir.cleanup()

    def test_first_use_logs_in_and_saves_key(self):
        with mock.patch.object(proxy, 'ask_credentials', return_value=('u', 'right')) as ask:
            replies = proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        self.assertEqual(replies[0]['result']['method'], 'tools/list')
        self.assertEqual(proxy.read_token(), GOOD)
        self.assertEqual(oct(os.stat(proxy.TOKEN_PATH).st_mode & 0o777), '0o600')
        ask.assert_called_once()

    def test_saved_key_is_reused_without_prompt(self):
        proxy.save_token(GOOD)
        with mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        ask.assert_not_called()

    def test_rejected_key_prompts_again_and_retries(self):
        proxy.save_token('qtpat_revoked')
        with mock.patch.object(proxy, 'ask_credentials', return_value=('u', 'right')):
            replies = proxy.forward({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call'})
        self.assertEqual(replies[0]['id'], 7)
        self.assertEqual(proxy.read_token(), GOOD)

    def test_wrong_password_retries_with_hint(self):
        answers = iter([('u', 'wrong'), ('u', 'right')])
        hints = []

        def ask(hint, use_terminal):
            hints.append(hint)
            return next(answers)

        with mock.patch.object(proxy, 'ask_credentials', side_effect=ask):
            proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        self.assertIn('密码错误', hints[1])
        self.assertEqual(len(FakeQtou.logins), 2)

    def test_cancel_returns_error_without_saving(self):
        emitted = []
        with mock.patch.object(proxy, 'ask_credentials', side_effect=proxy.LoginCancelled), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
        self.assertEqual(emitted[0]['error']['code'], -32001)
        self.assertEqual(proxy.read_token(), '')

    def test_notifications_get_no_reply(self):
        proxy.save_token(GOOD)
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(emitted, [])


if __name__ == '__main__':
    unittest.main()

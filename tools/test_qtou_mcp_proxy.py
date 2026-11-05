import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import qtou_mcp_proxy as proxy


def key_for(username):
    return 'qtpat_' + username


class FakeQtou(BaseHTTPRequestHandler):
    logins = []
    revoked = []
    valid = set()

    def log_message(self, *args):
        pass

    def do_DELETE(self):
        FakeQtou.revoked.append(self.path.rsplit('/', 1)[1])
        FakeQtou.valid.discard(self.headers.get('Authorization', '')[7:])
        self.send_json(200, {'success': True})

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        if self.path.endswith('/auth/login'):
            form = urllib.parse.parse_qs(body.decode())
            username, password = form['username'][0], form['password'][0]
            FakeQtou.logins.append(username)
            if password != 'right':
                return self.send_json(200, {'msg': '密码错误'})
            FakeQtou.valid.add(key_for(username))
            return self.send_json(200, {'data': {'agentKey': key_for(username), 'agentKeyId': 'id-' + username}})
        message = json.loads(body)
        key = self.headers.get('Authorization', '')[7:]
        if key not in FakeQtou.valid:
            return self.send_json(401, {'jsonrpc': '2.0', 'error': {'code': 10007, 'message': 'bad key'}})
        result = {'tools': [{'name': 'agent_health'}]} if message.get('method') == 'tools/list' else {'as': key}
        self.send_json(200, {'jsonrpc': '2.0', 'id': message.get('id'), 'result': result}, session='s1')

    def send_json(self, status, payload, session=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        if session:
            self.send_header('Mcp-Session-Id', session)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def call(name, **arguments):
    emitted = []
    with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
        proxy.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
    result = emitted[0]['result']
    return json.loads(result['content'][0]['text']), result['isError']


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeQtou)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % cls.server.server_port
        cls.patches = [mock.patch.object(proxy, 'MCP_URL', base + '/mcp'), mock.patch.object(proxy, 'API_BASE', base)]
        for patch in cls.patches:
            patch.start()

    @classmethod
    def tearDownClass(cls):
        for patch in cls.patches:
            patch.stop()
        cls.server.shutdown()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        home = os.path.join(self.dir.name, 'qtou')
        self.path_patches = [mock.patch.object(proxy, 'TOKEN_PATH', os.path.join(home, 'connector-token')),
                             mock.patch.object(proxy, 'ACCOUNTS_PATH', os.path.join(home, 'accounts.json'))]
        for patch in self.path_patches:
            patch.start()
        proxy.session.update(id=None, initialize=None, upstream_ready=False, client_form=False)
        FakeQtou.logins, FakeQtou.revoked, FakeQtou.valid = [], [], set()

    def tearDown(self):
        for patch in self.path_patches:
            patch.stop()
        self.dir.cleanup()

    def login_as(self, *usernames):
        for username in usernames:
            with mock.patch.object(proxy, 'ask_credentials', return_value=(username, 'right')):
                proxy.login()

    def test_first_use_logs_in_and_saves_key(self):
        with mock.patch.object(proxy, 'ask_credentials', return_value=('u1', 'right')) as ask:
            replies = proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        self.assertEqual(replies[0]['result']['as'], key_for('u1'))
        self.assertEqual(proxy.read_token(), key_for('u1'))
        for path in (proxy.TOKEN_PATH, proxy.ACCOUNTS_PATH):
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), '0o600')
        ask.assert_called_once()

    def test_saved_key_is_reused_without_prompt(self):
        self.login_as('u1')
        with mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        ask.assert_not_called()

    def test_rejected_key_prompts_again_and_retries(self):
        self.login_as('u1')
        FakeQtou.valid.clear()
        with mock.patch.object(proxy, 'ask_credentials', return_value=('u1', 'right')):
            replies = proxy.forward({'jsonrpc': '2.0', 'id': 7, 'method': 'ping'})
        self.assertEqual(replies[0]['id'], 7)

    def test_wrong_password_retries_with_hint(self):
        answers = iter([('u1', 'wrong'), ('u1', 'right')])
        hints = []

        def ask(hint, use_terminal):
            hints.append(hint)
            return next(answers)

        with mock.patch.object(proxy, 'ask_credentials', side_effect=ask):
            proxy.forward({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        self.assertIn('密码错误', hints[1])

    def test_cancel_returns_error_without_saving(self):
        emitted = []
        with mock.patch.object(proxy, 'ask_credentials', side_effect=proxy.LoginCancelled), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
        self.assertEqual(emitted[0]['error']['code'], -32001)
        self.assertEqual(proxy.read_token(), '')

    def test_form_login_answer_goes_to_bridge_only(self):
        proxy.session['client_form'] = True
        sent = []

        def client(message):
            sent.append(message)
            if message.get('method') == 'elicitation/create':
                proxy.route({'jsonrpc': '2.0', 'id': message['id'],
                             'result': {'action': 'accept', 'content': {'username': 'u1', 'password': 'right'}}})

        with mock.patch.object(proxy, 'emit', side_effect=client):
            proxy.handle({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/list'})
        self.assertEqual(sent[0]['method'], 'elicitation/create')
        self.assertEqual(set(sent[0]['params']['requestedSchema']['required']), {'username', 'password'})
        self.assertEqual(sent[1]['id'], 5)
        self.assertNotIn('right', json.dumps(sent[1]))

    def test_tools_list_includes_account_tools(self):
        self.login_as('u1')
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        names = [tool['name'] for tool in emitted[0]['result']['tools']]
        self.assertIn('agent_health', names)
        self.assertTrue(proxy.LOCAL_TOOL_NAMES <= set(names))

    def test_add_switch_and_list_accounts(self):
        self.login_as('u1')
        with mock.patch.object(proxy, 'ask_credentials', return_value=('u2', 'right')):
            added, _ = call('qtou_account_add')
        self.assertEqual(added['current'], 'u2')
        switched, _ = call('qtou_account_switch', username='u1')
        self.assertEqual(switched['current'], 'u1')
        with open(proxy.TOKEN_PATH) as handle:
            self.assertEqual(handle.read(), key_for('u1'))
        listed, _ = call('qtou_account_list')
        self.assertEqual(sorted(a['username'] for a in listed['accounts']), ['u1', 'u2'])
        self.assertNotIn('qtpat_', json.dumps(listed))
        replies = proxy.forward({'jsonrpc': '2.0', 'id': 9, 'method': 'ping'})
        self.assertEqual(replies[0]['result']['as'], key_for('u1'))

    def test_switch_to_unknown_account_fails(self):
        self.login_as('u1')
        result, is_error = call('qtou_account_switch', username='nobody')
        self.assertTrue(is_error)
        self.assertEqual(result['error']['code'], 'NOT_FOUND')

    def test_logout_current_revokes_and_falls_back(self):
        self.login_as('u1', 'u2')
        result, _ = call('qtou_account_logout')
        self.assertEqual(FakeQtou.revoked, ['id-u2'])
        self.assertEqual(result['current'], 'u1')
        self.assertEqual(proxy.read_token(), key_for('u1'))

    def test_logout_last_account_removes_key_file(self):
        self.login_as('u1')
        call('qtou_account_logout', username='u1')
        self.assertFalse(os.path.exists(proxy.TOKEN_PATH))
        self.assertEqual(proxy.read_token(), '')

    def test_legacy_single_key_is_migrated(self):
        proxy.write_private(proxy.TOKEN_PATH, key_for('old'))
        self.assertEqual(proxy.read_token(), key_for('old'))
        listed, _ = call('qtou_account_list')
        self.assertEqual(listed['current'], proxy.MIGRATED_ACCOUNT_NAME)

    def test_initialize_without_key_answers_locally(self):
        emitted = []
        message = {'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
                   'params': {'protocolVersion': '2025-06-18', 'capabilities': {'elicitation': {}}}}
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.initialize(message)
        self.assertEqual(emitted[0]['result']['protocolVersion'], '2025-06-18')
        self.assertTrue(proxy.session['client_form'])

    def test_notifications_get_no_reply(self):
        self.login_as('u1')
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(emitted, [])


if __name__ == '__main__':
    unittest.main()

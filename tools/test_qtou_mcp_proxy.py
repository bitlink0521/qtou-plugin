import json
import os
import subprocess
import sys
import tempfile
import threading
import zipfile
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
    calls = []

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
        FakeQtou.calls.append(message)
        tool = (message.get('params') or {}).get('name')
        if message.get('method') == 'tools/list':
            result = {'tools': [{'name': 'agent_health'}]}
        elif tool == 'agent_projects_get':
            result = {'content': [{'type': 'text', 'text': json.dumps({'projectName': '心永科技', 'companyName': '心永（深圳）科技有限公司'})}]}
        else:
            result = {'as': key}
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
        cls.patches = [mock.patch.object(proxy, 'MCP_URL', base + '/mcp'), mock.patch.object(proxy, 'API_BASE', base), mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login')]
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
                             mock.patch.object(proxy, 'ACCOUNTS_PATH', os.path.join(home, 'accounts.json')),
                             mock.patch.dict(os.environ, {
                                 'QTOU_LOGIN_USERNAME': '',
                                 'QTOU_LOGIN_PASSWORD': '',
                             }, clear=False)]
        for patch in self.path_patches:
            patch.start()
        proxy.session.update(id=None, initialize=None, upstream_ready=False, client_form=False)
        FakeQtou.logins, FakeQtou.revoked, FakeQtou.valid, FakeQtou.calls = [], [], set(), []

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
            proxy.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {}}})
        error = emitted[0]['error']
        self.assertEqual(error['code'], -32001)
        self.assertIn('宿主发起安全登录', error['message'])
        self.assertNotIn('弹安全表单就能', error['message'])
        self.assertIn(proxy.DEFAULT_AUTH_LOGIN_URL, error['message'])
        self.assertIn('agent.bitilinks.cn', error['message'])
        self.assertEqual(error['data']['code'], 'AUTH_REQUIRED')
        self.assertEqual(error['data']['action'], 'HostSecureLogin')
        self.assertEqual(error['data']['loginUrl'], proxy.DEFAULT_AUTH_LOGIN_URL)
        self.assertEqual(error['data']['submit'], 'qtou_account_add')
        self.assertEqual(proxy.read_token(), '')

    def test_default_login_url_is_demo_74_not_factory_or_localhost(self):
        self.assertEqual(proxy.DEFAULT_AUTH_LOGIN_URL,
                         'http://82.157.40.213:8133/api/v1/agent/auth/login')
        self.assertNotIn('agent.bitilinks.cn', proxy.DEFAULT_AUTH_LOGIN_URL)
        self.assertNotIn('localhost', proxy.DEFAULT_AUTH_LOGIN_URL)
        self.assertNotIn('127.0.0.1', proxy.DEFAULT_AUTH_LOGIN_URL)

    def test_account_add_accepts_secure_form_credentials(self):
        with mock.patch.object(proxy, 'ask_credentials') as ask:
            added, is_error = call('qtou_account_add', username='u1', password='right')
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'u1')
        self.assertEqual(proxy.read_token(), key_for('u1'))
        ask.assert_not_called()
        self.assertEqual(FakeQtou.logins, ['u1'])
        dumped = json.dumps(added)
        self.assertNotIn('right', dumped)
        self.assertNotIn('qtpat_', dumped)

    def test_account_add_partial_credentials_returns_auth_required(self):
        result, is_error = call('qtou_account_add', username='u1')
        self.assertTrue(is_error)
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(result['login']['loginUrl'], proxy.DEFAULT_AUTH_LOGIN_URL)
        self.assertEqual(result['login']['action'], 'HostSecureLogin')
        self.assertEqual(proxy.read_token(), '')

    def test_account_add_wrong_password_does_not_save_or_echo(self):
        secret = 'wrong-pass-should-not-leak'
        result, is_error = call('qtou_account_add', username='u1', password=secret)
        self.assertTrue(is_error)
        self.assertEqual(result['error']['code'], 'AUTH_FAILED')
        self.assertEqual(result['login']['loginUrl'], proxy.DEFAULT_AUTH_LOGIN_URL)
        self.assertEqual(proxy.read_token(), '')
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_tools_list_account_add_schema_exposes_username_password(self):
        self.login_as('u1')
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 21, 'method': 'tools/list'})
        tools = {tool['name']: tool for tool in emitted[0]['result']['tools']}
        props = tools['qtou_account_add']['inputSchema']['properties']
        self.assertIn('username', props)
        self.assertIn('password', props)
        self.assertEqual(props['username']['type'], 'string')
        self.assertEqual(props['password']['type'], 'string')

    def test_account_add_elicitation_cancel_returns_auth_required(self):
        emitted = []
        with mock.patch.object(proxy, 'ask_credentials', side_effect=proxy.LoginCancelled), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 23, 'method': 'tools/call',
                          'params': {'name': 'qtou_account_add', 'arguments': {}}})
        error = emitted[0]['error']
        self.assertEqual(error['code'], -32001)
        self.assertEqual(error['data']['code'], 'AUTH_REQUIRED')
        self.assertEqual(error['data']['action'], 'HostSecureLogin')
        self.assertIn('宿主发起安全登录', error['message'])
        self.assertIn(proxy.DEFAULT_AUTH_LOGIN_URL, error['message'])
        self.assertEqual(proxy.read_token(), '')

    def test_account_add_with_credentials_posts_to_login_url(self):
        added, is_error = call('qtou_account_add', username='u1', password='right')
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'u1')
        self.assertEqual(FakeQtou.logins, ['u1'])
        self.assertEqual(proxy.LOGIN_URL.rsplit('/', 1)[-1], 'login')
        self.assertTrue(proxy.LOGIN_URL.endswith('/auth/login'))
        self.assertNotIn('right', json.dumps(added))


    def test_account_add_uses_env_credentials_when_args_omitted(self):
        secret = 'right'
        with mock.patch.dict(os.environ, {
            'QTOU_LOGIN_USERNAME': 'env-user',
            'QTOU_LOGIN_PASSWORD': secret,
        }), mock.patch.object(proxy, 'ask_credentials') as ask:
            added, is_error = call('qtou_account_add')
            self.assertEqual(os.environ.get('QTOU_LOGIN_PASSWORD'), secret)
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'env-user')
        self.assertEqual(proxy.read_token(), key_for('env-user'))
        self.assertEqual(FakeQtou.logins, ['env-user'])
        ask.assert_not_called()
        dumped = json.dumps(added, ensure_ascii=False)
        self.assertNotIn(secret, dumped)
        self.assertNotIn('qtpat_', dumped)

    def test_account_add_params_take_priority_over_env(self):
        env_secret = 'env-secret-should-not-be-used'
        with mock.patch.dict(os.environ, {
            'QTOU_LOGIN_USERNAME': 'env-user',
            'QTOU_LOGIN_PASSWORD': env_secret,
        }), mock.patch.object(proxy, 'ask_credentials') as ask:
            added, is_error = call('qtou_account_add', username='u1', password='right')
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'u1')
        self.assertNotEqual(added['current'], 'env-user')
        self.assertEqual(FakeQtou.logins, ['u1'])
        ask.assert_not_called()
        dumped = json.dumps(added, ensure_ascii=False)
        self.assertNotIn(env_secret, dumped)
        self.assertNotIn('right', dumped)
        self.assertNotIn('qtpat_', dumped)

    def test_account_add_param_username_and_env_password(self):
        secret = 'right'
        with mock.patch.dict(os.environ, {'QTOU_LOGIN_PASSWORD': secret}), \
                mock.patch.object(proxy, 'ask_credentials') as ask:
            added, is_error = call('qtou_account_add', username='u1')
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'u1')
        self.assertEqual(FakeQtou.logins, ['u1'])
        ask.assert_not_called()
        self.assertNotIn(secret, json.dumps(added, ensure_ascii=False))

    def test_account_add_without_args_env_or_elicitation_returns_auth_required(self):
        emitted = []
        with mock.patch.object(proxy, 'ask_credentials', side_effect=proxy.LoginCancelled), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 31, 'method': 'tools/call',
                          'params': {'name': 'qtou_account_add', 'arguments': {}}})
        error = emitted[0]['error']
        self.assertEqual(error['code'], -32001)
        self.assertEqual(error['data']['code'], 'AUTH_REQUIRED')
        self.assertEqual(error['data']['action'], 'HostSecureLogin')
        self.assertEqual(error['data']['secretRequest'], 'QTOU_LOGIN_PASSWORD')
        self.assertEqual(error['data']['env']['password'], 'QTOU_LOGIN_PASSWORD')
        self.assertEqual(error['data']['env']['username'], 'QTOU_LOGIN_USERNAME')
        self.assertIn('secret-request', error['message'])
        self.assertIn('QTOU_LOGIN_PASSWORD', error['message'])
        self.assertIn('宿主发起安全登录', error['message'])
        self.assertEqual(proxy.read_token(), '')
        self.assertNotIn('right', json.dumps(emitted, ensure_ascii=False))

    def test_account_add_env_password_absent_from_all_outputs(self):
        secret = 'env-pass-must-never-leak-xyz'
        captured = []

        def capture_emit(message):
            captured.append(message)

        def capture_log(message):
            captured.append({'log': message})

        with mock.patch.dict(os.environ, {
            'QTOU_LOGIN_USERNAME': 'u1',
            'QTOU_LOGIN_PASSWORD': secret,
        }), mock.patch.object(proxy, 'emit', side_effect=capture_emit), \
                mock.patch.object(proxy, 'log', side_effect=capture_log):
            proxy.handle({'jsonrpc': '2.0', 'id': 32, 'method': 'tools/call',
                          'params': {'name': 'qtou_account_add', 'arguments': {}}})
        self.assertTrue(captured)
        result = json.loads(captured[0]['result']['content'][0]['text'])
        self.assertEqual(result.get('error', {}).get('code'), 'AUTH_FAILED')
        blob = json.dumps(captured, ensure_ascii=False)
        self.assertNotIn(secret, blob)
        self.assertEqual(proxy.read_token(), '')

    def test_account_add_ignores_url_and_site_argument_overrides(self):
        login_url = proxy.LOGIN_URL
        added, is_error = call('qtou_account_add', username='u1', password='right',
                               url='http://example.invalid/login', site='evil.example')
        self.assertFalse(is_error)
        self.assertEqual(added['current'], 'u1')
        self.assertEqual(FakeQtou.logins, ['u1'])
        self.assertEqual(proxy.LOGIN_URL, login_url)
        self.assertNotIn('example.invalid', json.dumps(added, ensure_ascii=False))

    def test_form_login_answer_goes_to_bridge_only(self):
        proxy.session['client_form'] = True
        sent = []

        def client(message):
            sent.append(message)
            if message.get('method') == 'elicitation/create':
                proxy.route({'jsonrpc': '2.0', 'id': message['id'],
                             'result': {'action': 'accept', 'content': {'username': 'u1', 'password': 'right'}}})

        with mock.patch.object(proxy, 'emit', side_effect=client):
            proxy.handle({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {}}})
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

    def test_env_token_is_used_when_no_account_saved(self):
        with mock.patch.dict(os.environ, {'QTOU_CONNECTOR_TOKEN': key_for('env')}):
            self.assertEqual(proxy.read_token(), key_for('env'))
        self.login_as('u1')
        with mock.patch.dict(os.environ, {'QTOU_CONNECTOR_TOKEN': key_for('env')}):
            self.assertEqual(proxy.read_token(), key_for('u1'))

    def test_initialize_without_key_answers_locally(self):
        emitted = []
        message = {'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
                   'params': {'protocolVersion': '2025-06-18', 'capabilities': {'elicitation': {}}}}
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.initialize(message)
        self.assertEqual(emitted[0]['result']['protocolVersion'], '2025-06-18')
        self.assertTrue(proxy.session['client_form'])

    def confirm_with_answer(self, action):
        self.login_as('u1')
        proxy.session['client_form'] = True
        sent = []

        def client(message):
            sent.append(message)
            if message.get('method') == 'elicitation/create':
                proxy.route({'jsonrpc': '2.0', 'id': message['id'], 'result': {'action': action}})

        with mock.patch.object(proxy, 'emit', side_effect=client):
            proxy.handle({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                          'params': {'name': 'agent_projects_confirm', 'arguments': {'pendingId': 'p1', 'confirmToken': 't'}}})
        forwarded = [c for c in FakeQtou.calls if (c.get('params') or {}).get('name') == 'agent_projects_confirm']
        return sent, forwarded

    def test_confirm_card_shows_project_and_forwards_on_accept(self):
        sent, forwarded = self.confirm_with_answer('accept')
        card = sent[0]['params']
        self.assertIn('心永科技', card['message'])
        self.assertIn('心永（深圳）科技有限公司', card['message'])
        self.assertEqual(card['requestedSchema']['properties'], {})
        self.assertEqual(len(forwarded), 1)
        self.assertEqual(sent[-1]['id'], 8)

    def test_confirm_card_decline_does_not_write(self):
        sent, forwarded = self.confirm_with_answer('decline')
        self.assertEqual(forwarded, [])
        self.assertIn('USER_DECLINED', sent[-1]['result']['content'][0]['text'])

    def test_client_without_forms_keeps_text_confirmation(self):
        self.login_as('u1')
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call',
                          'params': {'name': 'agent_projects_confirm', 'arguments': {'pendingId': 'p1'}}})
        self.assertEqual(len(emitted), 1)
        self.assertNotIn('elicitation/create', json.dumps(emitted))

    def test_notifications_get_no_reply(self):
        self.login_as('u1')
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(emitted, [])


if __name__ == '__main__':
    unittest.main()


class ImageResultTest(unittest.TestCase):
    def test_image_results_drop_structured_content_so_images_reach_the_model(self):
        image = {'jsonrpc': '2.0', 'id': 1, 'result': {
            'content': [{'type': 'text', 'text': '{}'}, {'type': 'image', 'data': 'AAAA', 'mimeType': 'image/png'}],
            'structuredContent': {'items': []}}}
        plain = {'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': '{}'}], 'structuredContent': {'a': 1}}}
        proxy.keep_images_visible([image, plain])
        self.assertNotIn('structuredContent', image['result'])
        self.assertEqual(plain['result']['structuredContent'], {'a': 1})


class ReportWordTests(unittest.TestCase):
    TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'dd-report-template.docx')

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.markdown = os.path.join(self.work.name, 'r.md')
        with open(self.markdown, 'w', encoding='utf-8') as out:
            out.write('# 摘要\n测试公司。\n\n| 项目 | 内容 |\n| --- | --- |\n| 成立 | 2020年 |\n')
        self.output = os.path.join(self.work.name, 'out.docx')

    def tearDown(self):
        self.work.cleanup()

    def test_tries_site_styles_in_order_then_uses_first_that_downloads(self):
        def fake_download(file_id, directory):
            if file_id == 'missing':
                raise ValueError('本地无实体文件')
            return self.TEMPLATE, '某某投资建议书.docx'
        with mock.patch.object(proxy, 'download_style', side_effect=fake_download):
            result, is_error = call('qtou_report_word', markdownPath=self.markdown, outputPath=self.output,
                                    company='测试科技有限公司', title='投资建议书', styleFileIds=['missing', 'good'])
        self.assertFalse(is_error, result)
        self.assertEqual(result['style'], {'source': 'site', 'fileId': 'good', 'fileName': '某某投资建议书.docx'})
        self.assertEqual(result['stylesSkipped'][0]['fileId'], 'missing')
        self.assertTrue(zipfile.is_zipfile(self.output))
        with zipfile.ZipFile(self.output) as docx:
            self.assertIn('<w:tbl>', docx.read('word/document.xml').decode('utf-8'))

    def test_falls_back_to_plugin_template_when_no_style_downloads(self):
        with mock.patch.object(proxy, 'download_style', side_effect=ValueError('x')):
            result, is_error = call('qtou_report_word', markdownPath=self.markdown, outputPath=self.output,
                                    company='测试科技有限公司', styleFileIds=['a'])
        self.assertFalse(is_error, result)
        self.assertEqual(result['style'], {'source': 'plugin-template'})

    def test_relative_paths_are_rejected(self):
        result, is_error = call('qtou_report_word', markdownPath='r.md', outputPath=self.output, company='测试')
        self.assertTrue(is_error)
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')

    def test_download_url_must_point_at_qtou(self):
        with mock.patch.object(proxy, 'call_upstream_tool', return_value={'url': 'http://evil.example/x', 'headers': {}}):
            with self.assertRaises(ValueError):
                proxy.download_style('f1', self.work.name)


class WindowsConsoleEncodingTests(unittest.TestCase):
    """A Chinese Windows console defaults to GBK; MCP stdio must still be UTF-8 with bare \\n."""

    def test_stdio_is_utf8_even_when_the_console_is_gbk(self):
        proxy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qtou_mcp_proxy.py')
        home = tempfile.TemporaryDirectory()
        env = {'HOME': home.name, 'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'PYTHONIOENCODING': 'gbk'}
        proc = subprocess.Popen([sys.executable, proxy_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env)
        try:
            for message in ({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                             'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': '测试•', 'version': '0'}}},
                            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}):
                proc.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8'))
                proc.stdin.flush()
            lines = [proc.stdout.readline(), proc.stdout.readline()]
        finally:
            proc.stdin.close()
            proc.wait(10)
            proc.stdout.close()
            home.cleanup()
        listed = json.loads(lines[1].decode('utf-8'))
        self.assertTrue(all(not line.endswith(b'\r\n') for line in lines))
        self.assertIn('轻投', ''.join(tool.get('description', '') for tool in listed['result']['tools']))


class UnauthenticatedStdioDiscoveryTests(unittest.TestCase):
    """Spawn the real stdio proxy with a blank HOME and no login env."""

    LOCAL_NAMES = {
        'qtou_account_list', 'qtou_account_add', 'qtou_account_switch', 'qtou_account_logout', 'qtou_report_word',
    }

    def test_tools_list_without_token_returns_local_tools_and_not_32001(self):
        proxy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qtou_mcp_proxy.py')
        home = tempfile.TemporaryDirectory()
        env = {
            'HOME': home.name,
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'PYTHONUNBUFFERED': '1',
            'LC_ALL': os.environ.get('LC_ALL', 'C'),
        }
        self.assertNotIn('QTOU_LOGIN_PASSWORD', env)
        self.assertNotIn('QTOU_LOGIN_USERNAME', env)
        self.assertNotIn('QTOU_CONNECTOR_TOKEN', env)
        proc = subprocess.Popen(
            [sys.executable, proxy_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )

        def send(message):
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            proc.stdin.flush()

        def recv(timeout=15):
            holder = []

            def target():
                holder.append(proc.stdout.readline())

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout)
            if thread.is_alive():
                self.fail('proxy did not reply within %s seconds' % timeout)
            raw = holder[0] if holder else ''
            self.assertTrue(raw, 'proxy closed stdout without a reply')
            return json.loads(raw)

        try:
            send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                             'clientInfo': {'name': 'toolslist-regress', 'version': '0'}}})
            initialized = recv()
            self.assertNotEqual((initialized.get('error') or {}).get('code'), -32001)
            self.assertIn('result', initialized)
            send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
            listed = recv()
            self.assertNotIn('error', listed)
            self.assertNotEqual((listed.get('error') or {}).get('code'), -32001)
            tools = listed['result']['tools']
            names = [tool['name'] for tool in tools]
            self.assertTrue(self.LOCAL_NAMES <= set(names))
            self.assertIn('agent_projects_create_pending', names)  # signed-out listing includes the business tools snapshot
            self.assertGreater(len(tools), 4)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            home.cleanup()

    def test_tools_list_content_length_framed_without_token_returns_local_tools(self):
        """Grok/Cursor speak MCP stdio as Content-Length frames, not NDJSON."""
        proxy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qtou_mcp_proxy.py')
        home = tempfile.TemporaryDirectory()
        env = {
            'HOME': home.name,
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'PYTHONUNBUFFERED': '1',
            'PYTHONIOENCODING': 'utf-8',
            'LC_ALL': os.environ.get('LC_ALL', 'C.UTF-8'),
        }
        self.assertNotIn('QTOU_LOGIN_PASSWORD', env)
        self.assertNotIn('QTOU_LOGIN_USERNAME', env)
        self.assertNotIn('QTOU_CONNECTOR_TOKEN', env)
        proc = subprocess.Popen(
            [sys.executable, '-u', proxy_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        def send(message):
            raw = json.dumps(message, ensure_ascii=False).encode('utf-8')
            proc.stdin.write(('Content-Length: %d\r\n\r\n' % len(raw)).encode('ascii'))
            proc.stdin.write(raw)
            proc.stdin.flush()

        def read_some(n=None, line=False, timeout=15):
            holder = []

            def target():
                if line:
                    buf = bytearray()
                    while True:
                        chunk = proc.stdout.read(1)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        if chunk == b'\n':
                            break
                    holder.append(bytes(buf))
                else:
                    holder.append(proc.stdout.read(n))

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout)
            if thread.is_alive():
                self.fail('proxy did not reply within %s seconds' % timeout)
            return holder[0] if holder else b''

        def recv(timeout=15):
            length = None
            while True:
                header = read_some(line=True, timeout=timeout)
                if header == b'':
                    self.fail('proxy closed stdout without a framed reply')
                if header in (b'\n', b'\r\n'):
                    break
                if header.lower().startswith(b'content-length:'):
                    length = int(header.split(b':', 1)[1].strip())
            self.assertIsNotNone(length, 'proxy reply was not Content-Length framed')
            raw = read_some(n=length, timeout=timeout)
            self.assertEqual(len(raw), length, 'framed body shorter than Content-Length')
            return json.loads(raw.decode('utf-8'))

        try:
            send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                             'clientInfo': {'name': 'toolslist-framing', 'version': '0'}}})
            send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
            initialized = recv()
            self.assertEqual(initialized.get('id'), 1)
            self.assertNotEqual((initialized.get('error') or {}).get('code'), -32001)
            self.assertIn('result', initialized)
            listed = recv()
            self.assertEqual(listed.get('id'), 2)
            self.assertNotIn('error', listed)
            self.assertNotEqual((listed.get('error') or {}).get('code'), -32001)
            tools = listed['result']['tools']
            names = [tool['name'] for tool in tools]
            self.assertTrue(self.LOCAL_NAMES <= set(names))
            self.assertIn('agent_projects_create_pending', names)  # signed-out listing includes the business tools snapshot
            self.assertGreater(len(tools), 4)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            home.cleanup()

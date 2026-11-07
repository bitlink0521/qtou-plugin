#!/usr/bin/env python3
"""Shipped tool catalog: local tools/list, no business call without a key."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import qtou_mcp_proxy as proxy
import qtou_shared

ROOT = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(ROOT, 'qtou_tool_catalog.json')
GENERATOR = os.path.join(ROOT, 'generate_qtou_tool_catalog.py')
LOCAL_NAMES = ['qtou_account_list', 'qtou_account_add', 'qtou_account_switch', 'qtou_account_logout']


def load_catalog():
    return json.load(open(CATALOG, encoding='utf-8'))


class FakeQtou(BaseHTTPRequestHandler):
    logins = []
    calls = []
    valid = set()

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path.endswith('/auth/login'):
            form = urllib.parse.parse_qs(body.decode())
            username, password = form['username'][0], form['password'][0]
            FakeQtou.logins.append(username)
            if password != 'right':
                return self.send_json(200, {'success': False, 'errorCode': 10001, 'msg': '密码错误', 'data': {}})
            FakeQtou.valid.add('qtpat_' + username)
            return self.send_json(200, {'success': True, 'data': {'agentKey': 'qtpat_' + username, 'agentKeyId': 'id-' + username}})
        message = json.loads(body)
        key = self.headers.get('Authorization', '')[7:]
        if key not in FakeQtou.valid:
            return self.send_json(401, {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': 10007, 'message': 'bad key'}})
        FakeQtou.calls.append(message.get('method'))
        name = (message.get('params') or {}).get('name')
        if name == 'agent_health':
            result = {'ok': True, 'service': 'fake'}
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


class CatalogSourceTests(unittest.TestCase):
    def test_generator_reproduces_the_shipped_catalog(self):
        out = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        out.close()
        try:
            result = subprocess.run([sys.executable, GENERATOR, '--output=' + out.name],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(open(out.name, 'rb').read(), open(CATALOG, 'rb').read())
        finally:
            os.remove(out.name)

    def test_catalog_pins_source_commit_and_file_hashes(self):
        document = load_catalog()
        self.assertEqual(document['sourceCommit'], proxy.CATALOG_SOURCE_COMMIT)
        self.assertEqual([(item['path'], item['sha256']) for item in document['sourceFiles']], list(proxy.CATALOG_SOURCE_FILES))
        for filename, _path, digest in __import__('generate_qtou_tool_catalog').PINNED_FILES:
            raw = open(os.path.join(ROOT, 'qtou_schema_src', filename), 'rb').read()
            self.assertEqual(__import__('hashlib').sha256(raw).hexdigest(), digest)
        tools, code = proxy.load_tool_catalog(CATALOG)
        self.assertIsNone(code)
        self.assertEqual(tools, document['tools'])
        self.assertEqual(proxy.catalog_tools_digest(tools), document['schemaSha256'])
        self.assertEqual([item['name'] for item in tools][:1], ['agent_health'])
        self.assertEqual([item['name'] for item in tools][-8:], [
            'create_risk_draft', 'list_risk_drafts', 'dismiss_risk_draft', 'risk_drafts_summary',
            'risk_run_record', 'risk_tyc_news', 'risk_config_get', 'risk_config_update'])
        portfolio = next(item for item in tools if item['name'] == 'agent_portfolio_list')
        self.assertEqual(portfolio['inputSchema']['properties']['strictAfterInvest']['type'], 'boolean')
        self.assertNotIn('strictAfterInvest', portfolio['inputSchema'].get('required', []))
        created = next(item for item in tools if item['name'] == 'agent_risk_alerts_create')
        field = created['inputSchema']['properties']['sources']['items']['properties']['field']['description']
        self.assertIn('正例：business_income', field)
        evidence = next(item for item in tools if item['name'] == 'agent_projects_bp_fill')['inputSchema']['properties']['evidence']
        self.assertEqual(evidence['properties']['schemaVersion']['enum'], [1])
        self.assertEqual(len(evidence['properties']['fields']['items']['properties']['field']['enum']), 97)
        for item in tools:
            self.assertIsInstance(item['name'], str)
            self.assertIsInstance(item['description'], str)
            self.assertIsInstance(item['inputSchema'], dict)


class CatalogRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeQtou)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % cls.server.server_port
        cls.patches = [
            mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
            mock.patch.object(proxy, 'API_BASE', base),
            mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login'),
        ]
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
        self.path_patches = [
            mock.patch.object(proxy, 'TOKEN_PATH', os.path.join(home, 'connector-token')),
            mock.patch.object(proxy, 'ACCOUNTS_PATH', os.path.join(home, 'accounts.json')),
            mock.patch.dict(os.environ, {'QTOU_LOGIN_USERNAME': '', 'QTOU_LOGIN_PASSWORD': '', 'QTOU_CONNECTOR_TOKEN': ''}, clear=False),
        ]
        for patch in self.path_patches:
            patch.start()
        proxy.session.update(id=None, initialize=None, upstream_ready=False, client_form=False)
        FakeQtou.logins, FakeQtou.calls, FakeQtou.valid = [], [], set()

    def tearDown(self):
        for patch in self.path_patches:
            patch.stop()
        self.dir.cleanup()

    def listed(self):
        emitted = []
        def refuse(*args, **kwargs):
            raise AssertionError('tools/list must not open a network connection')
        with mock.patch('urllib.request.urlopen', refuse), mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        return emitted[0]

    def test_tools_list_is_local_without_token_with_token_and_offline(self):
        expected = [item['name'] for item in load_catalog()['tools']] + LOCAL_NAMES
        first = self.listed()
        self.assertEqual([item['name'] for item in first['result']['tools']], expected)
        self.assertEqual(FakeQtou.calls, [])
        with mock.patch.dict(os.environ, {'QTOU_CONNECTOR_TOKEN': 'qtpat_offline'}):
            second = self.listed()
        self.assertEqual(second['result']['tools'], first['result']['tools'])
        self.assertEqual(FakeQtou.calls, [])
        with mock.patch('urllib.request.urlopen', side_effect=OSError('offline')):
            third = self.listed()
        self.assertEqual([item['name'] for item in third['result']['tools']], expected)

    def test_business_call_without_token_does_not_post(self):
        emitted = []
        with mock.patch('urllib.request.urlopen', side_effect=AssertionError('business call posted')), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append), \
                mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {}}})
        ask.assert_not_called()
        error = emitted[0]['error']
        self.assertEqual(error['code'], -32001)
        self.assertEqual(error['data']['code'], 'AUTH_REQUIRED')
        self.assertEqual(error['data']['action'], 'HostSecureLogin')
        self.assertEqual(error['data']['secretRequest'], 'QTOU_LOGIN_PASSWORD')
        self.assertEqual(FakeQtou.logins, [])
        self.assertEqual(FakeQtou.calls, [])

    def test_fake_login_then_readonly_call_in_same_process(self):
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                          'params': {'name': 'qtou_account_add', 'arguments': {'username': 'u1', 'password': 'right'}}})
            proxy.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
            proxy.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {}}})
        self.assertEqual(FakeQtou.logins, ['u1'])
        self.assertEqual(FakeQtou.calls, ['tools/call'])
        self.assertEqual(proxy.read_token(), 'qtpat_u1')
        self.assertIn('agent_health', [item['name'] for item in emitted[1]['result']['tools']])
        self.assertEqual(emitted[2]['result'], {'ok': True, 'service': 'fake'})

    def test_new_process_reuses_saved_account_and_local_catalog(self):
        home = tempfile.mkdtemp(prefix='qtou-home-')
        store = os.path.join(home, '.qtou')
        os.makedirs(store)
        qtou_shared.store_accounts({
            'current': 'u1',
            'accounts': {'u1': {'key': 'qtpat_u1', 'keyId': 'id-u1', 'savedAt': '2026-01-01 00:00:00'}},
        }, os.path.join(store, 'accounts.json'), os.path.join(store, 'connector-token'))
        FakeQtou.valid.add('qtpat_u1')
        env = {
            'HOME': home,
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'PYTHONPATH': ROOT,
            'PYTHONUNBUFFERED': '1',
            'QTOU_MCP_URL': proxy.MCP_URL,
            'QTOU_LOGIN_URL': proxy.LOGIN_URL,
        }
        proc = subprocess.Popen([sys.executable, '-u', os.path.join(ROOT, 'qtou_mcp_proxy.py')],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, text=True, bufsize=1)

        def send(message):
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            proc.stdin.flush()

        def recv():
            raw = proc.stdout.readline()
            self.assertTrue(raw)
            return json.loads(raw)

        try:
            before = list(FakeQtou.calls)
            send({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            listed = recv()
            self.assertEqual(FakeQtou.calls, before)
            self.assertEqual([item['name'] for item in listed['result']['tools']][-4:], LOCAL_NAMES)
            send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'agent_health', 'arguments': {}}})
            called = recv()
            self.assertEqual(called['result'], {'ok': True, 'service': 'fake'})
            self.assertEqual(FakeQtou.logins, [])
            self.assertEqual(FakeQtou.calls, ['tools/call'])
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_bad_catalog_is_a_fixed_error_without_http(self):
        cases = []
        missing = os.path.join(self.dir.name, 'missing.json')
        cases.append((missing, 'CATALOG_MISSING'))
        invalid = os.path.join(self.dir.name, 'invalid.json')
        open(invalid, 'w', encoding='utf-8').write('{')
        cases.append((invalid, 'CATALOG_INVALID'))
        document = load_catalog()
        mismatch = os.path.join(self.dir.name, 'mismatch.json')
        changed = dict(document)
        changed['sourceCommit'] = '0' * 40
        json.dump(changed, open(mismatch, 'w', encoding='utf-8'), ensure_ascii=False)
        cases.append((mismatch, 'CATALOG_VERSION_MISMATCH'))
        digest = os.path.join(self.dir.name, 'digest.json')
        changed = json.loads(json.dumps(document))
        changed['schemaSha256'] = '0' * 64
        json.dump(changed, open(digest, 'w', encoding='utf-8'), ensure_ascii=False)
        cases.append((digest, 'CATALOG_INVALID'))
        for path, code in cases:
            emitted = []
            with mock.patch.dict(os.environ, {'QTOU_TOOL_CATALOG': path}), \
                    mock.patch('urllib.request.urlopen', side_effect=AssertionError('catalog error used the network')), \
                    mock.patch.object(proxy, 'emit', side_effect=emitted.append):
                proxy.handle({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list'})
            error = emitted[0]['error']
            self.assertEqual(error['data']['code'], code)
            self.assertEqual(error['code'], -32002)
            self.assertNotIn('tools', emitted[0])
            self.assertEqual(FakeQtou.calls, [])


class UpstreamFailureTests(unittest.TestCase):
    """Fake upstream errors stay errors. tools/list never opens that upstream."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), ModeQtou)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % cls.server.server_port
        cls.patches = [
            mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
            mock.patch.object(proxy, 'API_BASE', base),
            mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login'),
        ]
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
        self.accounts = os.path.join(home, 'accounts.json')
        self.token_path = os.path.join(home, 'connector-token')
        self.sentinel = 'pw-sentinel-not-real-xyz'
        self.key = 'qtpat_storedkey'
        self.path_patches = [
            mock.patch.object(proxy, 'TOKEN_PATH', self.token_path),
            mock.patch.object(proxy, 'ACCOUNTS_PATH', self.accounts),
            mock.patch.dict(os.environ, {
                'QTOU_LOGIN_USERNAME': '',
                'QTOU_LOGIN_PASSWORD': self.sentinel,
                'QTOU_CONNECTOR_TOKEN': '',
            }, clear=False),
        ]
        for patch in self.path_patches:
            patch.start()
        qtou_shared.store_accounts({
            'current': 'u1',
            'accounts': {'u1': {'key': self.key, 'keyId': 'id-u1', 'savedAt': '2026-01-01 00:00:00'}},
        }, self.accounts, self.token_path)
        self.saved = open(self.accounts, 'rb').read()
        proxy.session.update(id=None, initialize=None, upstream_ready=False, client_form=False)
        ModeQtou.hits = []
        ModeQtou.methods = []

    def tearDown(self):
        for patch in self.path_patches:
            patch.stop()
        self.dir.cleanup()

    def listed(self):
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
            proxy.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        return emitted[0]

    def test_old_discovery_helper_is_gone(self):
        self.assertFalse(hasattr(proxy, 'with_local_tools'))

    def test_tools_list_stays_local_when_upstream_would_fail(self):
        expected = [item['name'] for item in load_catalog()['tools']] + LOCAL_NAMES
        self.assertEqual(len(expected), 36)
        for mode in ('500-empty-tools', '500-empty', '401', '403', 'rpc-error'):
            ModeQtou.mode = mode
            ModeQtou.hits = []
            reply = self.listed()
            self.assertEqual(ModeQtou.hits, [], mode)
            tools = reply['result']['tools']
            self.assertEqual([item['name'] for item in tools], expected)
            self.assertTrue(all(isinstance(item['description'], str) and isinstance(item['inputSchema'], dict) for item in tools))

    def test_business_upstream_errors_are_explicit_and_do_not_login(self):
        cases = (
            ('500-empty-tools', -32002, 500),
            ('500-empty', -32002, 500),
            ('401', 10007, None),
            ('403', -32003, None),
            ('rpc-error', -32603, None),
        )
        for mode, code, http_status in cases:
            ModeQtou.mode = mode
            ModeQtou.hits = []
            emitted, logs = [], []
            with mock.patch.object(proxy, 'emit', side_effect=emitted.append), \
                    mock.patch.object(proxy, 'log', side_effect=logs.append), \
                    mock.patch.object(proxy, 'ask_credentials') as ask:
                proxy.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                              'params': {'name': 'agent_health', 'arguments': {}}})
            ask.assert_not_called()
            self.assertEqual(ModeQtou.hits, ['/api/v1/agent/mcp'], mode)
            reply = emitted[0]
            self.assertNotIn('result', reply, mode)
            self.assertEqual(reply['error']['code'], code, mode)
            if http_status is not None:
                self.assertEqual(reply['error']['data']['httpStatus'], http_status)
                self.assertNotIn('tools', reply['error'])
            blob = json.dumps(emitted, ensure_ascii=False) + '\n' + '\n'.join(logs)
            self.assertNotIn(self.sentinel, blob, mode)
            self.assertNotIn(self.key, blob, mode)
            self.assertNotIn('qtpat_', blob, mode)
            self.assertEqual(open(self.accounts, 'rb').read(), self.saved)
            self.assertEqual(proxy.read_token(), self.key)
            self.assertNotEqual(reply['error'].get('data', {}).get('code'), 'AUTH_REQUIRED')

    def test_saved_key_blocking_urlopen_keeps_initialize_and_tools_list_local(self):
        called = []

        def block(*args, **kwargs):
            called.append(1)
            time.sleep(5)
            raise OSError('upstream blocked')

        emitted = []
        started = time.monotonic()
        with mock.patch('urllib.request.urlopen', side_effect=block), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append), \
                mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.initialize({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                              'params': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}}})
            proxy.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            proxy.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        self.assertLess(time.monotonic() - started, 1)
        ask.assert_not_called()
        self.assertEqual(called, [])
        self.assertFalse(proxy.session['upstream_ready'])
        self.assertEqual(emitted[0]['id'], 1)
        self.assertEqual(emitted[0]['result']['serverInfo']['name'], 'qtou-agent-mcp')
        self.assertNotIn('tools', emitted[0]['result'])
        tools = emitted[1]['result']['tools']
        self.assertEqual(len(tools), 36)
        self.assertEqual([item['name'] for item in tools], [item['name'] for item in load_catalog()['tools']] + LOCAL_NAMES)
        self.assertEqual(len(emitted), 2)

    def test_first_business_call_sends_initialize_before_the_call(self):
        ModeQtou.mode = 'ok'
        emitted = []
        with mock.patch.object(proxy, 'emit', side_effect=emitted.append), \
                mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.initialize({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                              'params': {'protocolVersion': '2024-11-05', 'capabilities': {}}})
            self.assertFalse(proxy.session['upstream_ready'])
            proxy.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            proxy.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {}}})
        ask.assert_not_called()
        self.assertEqual(ModeQtou.methods, ['initialize', 'notifications/initialized', 'tools/call'])
        self.assertTrue(proxy.session['upstream_ready'])
        self.assertEqual(emitted[-1]['result'], {'ok': True, 'service': 'fake'})

    def test_short_password_and_nested_secrets_are_not_returned_or_logged(self):
        ModeQtou.mode = 'leak'
        short = 'abc123'
        nested = 'qtpat_nestedtok'
        emitted, logs = [], []
        with mock.patch.dict(os.environ, {'QTOU_LOGIN_PASSWORD': short}), \
                mock.patch.object(proxy, 'emit', side_effect=emitted.append), \
                mock.patch.object(proxy, 'log', side_effect=logs.append), \
                mock.patch.object(proxy, 'ask_credentials') as ask:
            proxy.handle({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                          'params': {'name': 'agent_health', 'arguments': {
                              'nested': {'token': nested, 'password': short}}}})
        ask.assert_not_called()
        reply = emitted[0]
        self.assertEqual(reply['error']['code'], -32603)
        self.assertEqual(reply['error']['message'], proxy.UPSTREAM_ERROR_MESSAGE)
        self.assertEqual(set(reply['error']['data']), {'code', 'httpStatus'})
        blob = json.dumps(emitted, ensure_ascii=False) + '\n' + '\n'.join(str(item) for item in logs)
        for secret in (short, nested, self.key, 'Bearer ' + self.key, self.sentinel):
            self.assertNotIn(secret, blob)


class ModeQtou(BaseHTTPRequestHandler):
    mode = '500-empty-tools'
    hits = []
    methods = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length) if length else b''
        ModeQtou.hits.append(self.path)
        if self.path.endswith('/auth/login'):
            self.send_json(500, {'msg': 'login must not run'})
            return
        message = json.loads(body.decode() or '{}')
        ModeQtou.methods.append(message.get('method'))
        echo = (self.headers.get('Authorization') or '') + ' pw-sentinel-not-real-xyz'
        mode = ModeQtou.mode
        if mode == 'ok':
            self.send_json(200, {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {'ok': True, 'service': 'fake'}})
        elif mode == 'leak':
            self.send_json(200, {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {
                'code': -32603,
                'message': echo + ' abc123',
                'data': {
                    'password': 'abc123',
                    'nested': {'token': 'qtpat_nestedtok', 'authorization': self.headers.get('Authorization') or ''},
                },
            }})
        elif mode == '500-empty-tools':
            self.send_json(500, {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {'tools': []}, 'echo': echo})
        elif mode == '500-empty':
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif mode == '401':
            self.send_json(401, {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': 10007, 'message': echo}})
        elif mode == '403':
            self.send_json(403, {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': -32003, 'message': echo}})
        elif mode == 'rpc-error':
            self.send_json(200, {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': -32603, 'message': echo}})
        else:
            self.send_json(500, {'echo': echo})

    def send_json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Regressions for error scrubbing, account identity, and private credential files."""
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import qtou_mcp_proxy as proxy
import qtou_shared


class Record(BaseHTTPRequestHandler):
    methods = []
    calls = []
    paths = []
    hold_initialize = None
    mode = ''

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length) if length else b''
        Record.paths.append(self.path)
        if self.path.endswith('/secret'):
            self.send_response(200)
            self.end_headers()
            return
        message = json.loads(body.decode() or '{}')
        name = (message.get('params') or {}).get('name')
        Record.methods.append(message.get('method'))
        Record.calls.append(name or message.get('method'))
        if message.get('method') == 'initialize' and Record.hold_initialize is not None:
            Record.hold_initialize.wait(2)
        if name == 'agent_health' and Record.mode == 'is-error':
            result = {'content': [{'type': 'text', 'text': '失败 abc123 qtpat_ZZZZZZZZ'}],
                      'structuredContent': {'password': 'abc123'}, 'isError': True}
        elif name == 'agent_projects_get':
            result = {'content': [{'type': 'text', 'text': '{}'}], 'isError': False}
        elif name == 'agent_projects_confirm':
            result = {'content': [{'type': 'text', 'text': '确认缺少 pendingId'}], 'isError': True}
        else:
            result = {'ok': True}
        data = json.dumps({'jsonrpc': '2.0', 'id': message.get('id'), 'result': result}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        home = os.path.join(self.dir.name, 'qtou')
        self.paths = [
            mock.patch.object(proxy, 'TOKEN_PATH', os.path.join(home, 'connector-token')),
            mock.patch.object(proxy, 'ACCOUNTS_PATH', os.path.join(home, 'accounts.json')),
            mock.patch.object(qtou_shared, 'TOKEN_PATH', os.path.join(home, 'connector-token')),
            mock.patch.object(qtou_shared, 'ACCOUNTS_PATH', os.path.join(home, 'accounts.json')),
        ]
        for item in self.paths:
            item.start()
        proxy.session.update(id=None, initialize=None, upstream_ready=False, client_form=False, ignore_env_token=False)
        Record.methods, Record.calls, Record.paths = [], [], []
        Record.mode, Record.hold_initialize = '', None

    def tearDown(self):
        for item in self.paths:
            item.stop()
        self.dir.cleanup()

    def test_private_write_repairs_mode_and_refuses_symlink(self):
        path = os.path.join(self.dir.name, 'secret')
        with open(path, 'w') as handle:
            handle.write('old')
        os.chmod(path, 0o644)
        qtou_shared.write_private(path, 'qtpat_notreal')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(open(path).read(), 'qtpat_notreal')
        link = os.path.join(self.dir.name, 'link')
        os.symlink(path, link)
        with self.assertRaises(PermissionError):
            qtou_shared.write_private(link, 'qtpat_other')
        self.assertEqual(open(path).read(), 'qtpat_notreal')

    def test_redirect_is_not_followed(self):
        class Redirect(BaseHTTPRequestHandler):
            seen = []

            def log_message(self, *args):
                pass

            def do_POST(self):
                Redirect.seen.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/secret')
                self.end_headers()

        server = HTTPServer(('127.0.0.1', 0), Redirect)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = __import__('urllib.request', fromlist=['request']).Request(
                'http://127.0.0.1:%d/login' % server.server_port, data=b'a=b', method='POST')
            with self.assertRaises(Exception):
                proxy.open_url(request, 5)
        finally:
            server.shutdown()
        self.assertEqual(Redirect.seen, ['/login'])

    def test_tool_error_and_login_failure_drop_secrets_but_keep_safe_diagnosis(self):
        self.assertIn('pendingId', proxy.scrub_diagnostic('确认缺少 pendingId abc123 qtpat_ZZZZZZZZ', ['abc123']))
        self.assertNotIn('abc123', proxy.scrub_diagnostic('确认缺少 pendingId abc123 qtpat_ZZZZZZZZ', ['abc123']))
        self.assertNotIn('qtpat_', proxy.scrub_diagnostic('确认缺少 pendingId abc123 qtpat_ZZZZZZZZ', ['abc123']))
        text = proxy.scrub_diagnostic('登录失败 qtpat_AAAAAAAB 和 abc123', ['abc123'])
        self.assertNotIn('qtpat_', text)
        self.assertNotIn('abc123', text)

    def test_mismatched_env_password_is_not_reused(self):
        with mock.patch.dict(os.environ, {'QTOU_LOGIN_USERNAME': 'env-user', 'QTOU_LOGIN_PASSWORD': 'env-secret-value'}), \
                mock.patch.object(proxy, 'sign_key') as sign:
            username, password = proxy.resolve_account_add_credentials({'username': 'other-user'})
        self.assertEqual(username, 'other-user')
        self.assertEqual(password, '')
        sign.assert_not_called()

    def test_logout_stops_using_env_token_without_a_saved_account(self):
        with mock.patch.dict(os.environ, {'QTOU_CONNECTOR_TOKEN': 'qtpat_envtoken1'}):
            self.assertEqual(proxy.read_token(), 'qtpat_envtoken1')
            emitted = []
            with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
                proxy.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                              'params': {'name': 'qtou_account_logout', 'arguments': {}}})
            self.assertEqual(proxy.read_token(), '')
        body = json.loads(emitted[0]['result']['content'][0]['text'])
        self.assertIn('QTOU_CONNECTOR_TOKEN', body['message'])
        self.assertNotIn('qtpat_', body['message'])

    def test_is_error_result_drops_secret_text(self):
        server = HTTPServer(('127.0.0.1', 0), Record)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % server.server_port
        Record.mode = 'is-error'
        qtou_shared.store_accounts({
            'current': 'u1',
            'accounts': {'u1': {'key': 'qtpat_userone', 'keyId': 'id', 'savedAt': '2026-01-01'}},
        }, proxy.ACCOUNTS_PATH, proxy.TOKEN_PATH)
        patches = [
            mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
            mock.patch.object(proxy, 'API_BASE', base),
            mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login'),
        ]
        for item in patches:
            item.start()
        emitted = []
        try:
            with mock.patch.object(proxy, 'emit', side_effect=emitted.append):
                proxy.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                              'params': {'name': 'agent_health', 'arguments': {}}})
        finally:
            for item in patches:
                item.stop()
            server.shutdown()
        blob = json.dumps(emitted, ensure_ascii=False)
        self.assertNotIn('abc123', blob)
        self.assertNotIn('qtpat_', blob)
        self.assertNotIn('structuredContent', blob)
        self.assertTrue(emitted[0]['result']['isError'])

    def test_concurrent_first_calls_initialize_once(self):
        server = HTTPServer(('127.0.0.1', 0), Record)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % server.server_port
        Record.hold_initialize = threading.Event()
        qtou_shared.store_accounts({
            'current': 'u1',
            'accounts': {'u1': {'key': 'qtpat_userone', 'keyId': 'id', 'savedAt': '2026-01-01'}},
        }, proxy.ACCOUNTS_PATH, proxy.TOKEN_PATH)
        proxy.session['initialize'] = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}
        patches = [
            mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
            mock.patch.object(proxy, 'API_BASE', base),
            mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login'),
        ]
        for item in patches:
            item.start()
        try:
            threads = [threading.Thread(target=proxy.handle, args=({
                'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                'params': {'name': 'agent_health', 'arguments': {}},
            },)) for index in (1, 2)]
            for thread in threads:
                thread.start()
            Record.hold_initialize.set()
            for thread in threads:
                thread.join(5)
            self.assertEqual(Record.methods.count('initialize'), 1)
        finally:
            for item in patches:
                item.stop()
            server.shutdown()

    def test_confirm_does_not_write_after_account_switch(self):
        server = HTTPServer(('127.0.0.1', 0), Record)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % server.server_port
        qtou_shared.store_accounts({
            'current': 'u1',
            'accounts': {
                'u1': {'key': 'qtpat_userone', 'keyId': 'id1', 'savedAt': '2026-01-01'},
                'u2': {'key': 'qtpat_usertwo', 'keyId': 'id2', 'savedAt': '2026-01-01'},
            },
        }, proxy.ACCOUNTS_PATH, proxy.TOKEN_PATH)
        proxy.session['client_form'] = True
        patches = [
            mock.patch.object(proxy, 'MCP_URL', base + '/mcp'),
            mock.patch.object(proxy, 'API_BASE', base),
            mock.patch.object(proxy, 'LOGIN_URL', base + '/auth/login'),
        ]
        for item in patches:
            item.start()
        emitted = []

        def client(message):
            emitted.append(message)
            if message.get('method') == 'elicitation/create':
                proxy.handle({'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call',
                              'params': {'name': 'qtou_account_switch', 'arguments': {'username': 'u2'}}})
                proxy.route({'jsonrpc': '2.0', 'id': message['id'], 'result': {'action': 'accept'}})

        try:
            with mock.patch.object(proxy, 'emit', side_effect=client):
                proxy.handle({'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call',
                              'params': {'name': 'agent_projects_confirm', 'arguments': {'pendingId': 'p1'}}})
        finally:
            for item in patches:
                item.stop()
            server.shutdown()
        self.assertNotIn('agent_projects_confirm', Record.calls)
        blob = json.dumps(emitted, ensure_ascii=False)
        self.assertIn('ACCOUNT_CHANGED', blob)
        self.assertNotIn('qtpat_', blob)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""stdio MCP bridge to the qtou server with built-in login and multiple accounts.

The client (e.g. Codex) launches this as a stdio MCP server. Every JSON-RPC message is forwarded to
QTOU_MCP_URL with the current account's connector key. When there is no account or the key is rejected,
the user is asked for the qtou username/password, a key is signed and saved, and the request is retried,
so the first use logs in and later uses just work.

Credentials are collected with an MCP form (elicitation/create) when the client supports it; the answer
goes back to this bridge only, never to the model or the chat. Otherwise a macOS dialog is used. A client that
signs the key itself (e.g. Grok Bot's secure form) can pass it in QTOU_CONNECTOR_TOKEN instead.

Accounts live in ~/.qtou/accounts.json (mode 600); the current account's key is mirrored to
~/.qtou/connector-token for the other plugin tools. Four local tools manage them:
qtou_account_list / qtou_account_add / qtou_account_switch / qtou_account_logout.

`--login` adds an account by hand (terminal prompts when available, dialogs otherwise).
"""
import getpass
import itertools
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import qtou_shared
from qtou_shared import MIGRATED_ACCOUNT_NAME, parse_mcp_body, write_private

MCP_URL = qtou_shared.DEFAULT_MCP_URL
API_BASE = MCP_URL.rsplit('/mcp', 1)[0]
TOKEN_PATH = qtou_shared.TOKEN_PATH
ACCOUNTS_PATH = qtou_shared.ACCOUNTS_PATH
AUTH_ERROR_CODE = 10007
MAX_LOGIN_ATTEMPTS = 3
FORM_TIMEOUT_SECONDS = 600

write_lock = threading.Lock()
login_lock = threading.Lock()
session = {'id': None, 'initialize': None, 'upstream_ready': False, 'client_form': False}
pending_requests = {}
request_ids = itertools.count(1)

LOCAL_TOOLS = [
    {'name': 'qtou_account_list',
     'description': '列出本机已登录的轻投账号，并标出当前使用的账号。不返回 key。',
     'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'qtou_account_add',
     'description': '弹出登录表单添加一个轻投账号，登录成功后切换为当前账号。账号密码只填在表单里，不要在聊天里索要。',
     'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'qtou_account_switch',
     'description': '切换当前轻投账号，之后的轻投操作都以该账号身份进行。',
     'inputSchema': {'type': 'object', 'properties': {'username': {'type': 'string', 'description': '要切换到的账号用户名'}},
                     'required': ['username']}},
    {'name': 'qtou_account_logout',
     'description': '退出一个轻投账号并在服务端吊销它的 key；不传 username 则退出当前账号。',
     'inputSchema': {'type': 'object', 'properties': {'username': {'type': 'string', 'description': '要退出的账号用户名'}}}},
]
LOCAL_TOOL_NAMES = {tool['name'] for tool in LOCAL_TOOLS}


class LoginCancelled(Exception):
    pass


def log(message):
    sys.stderr.write('[qtou-mcp] %s\n' % message)
    sys.stderr.flush()


def load_accounts():
    return qtou_shared.load_accounts(ACCOUNTS_PATH, TOKEN_PATH)


def store_accounts(data):
    qtou_shared.store_accounts(data, ACCOUNTS_PATH, TOKEN_PATH)


def read_token():
    return qtou_shared.current_token(ACCOUNTS_PATH, TOKEN_PATH)


def save_account(username, key, key_id):
    data = load_accounts()
    data['accounts'][username] = {'key': key, 'keyId': key_id, 'savedAt': time.strftime('%Y-%m-%d %H:%M:%S')}
    data['current'] = username
    store_accounts(data)
    reset_upstream()


def reset_upstream():
    session['id'] = None
    session['upstream_ready'] = False


def emit(message):
    with write_lock:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + '\n')
        sys.stdout.flush()


def request_client(method, params):
    request_id = 'qtou-%d' % next(request_ids)
    waiter = {'event': threading.Event(), 'reply': None}
    pending_requests[request_id] = waiter
    emit({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
    answered = waiter['event'].wait(FORM_TIMEOUT_SECONDS)
    pending_requests.pop(request_id, None)
    return waiter['reply'] if answered else None


def ask_form(hint):
    reply = request_client('elicitation/create', {
        'message': (hint + '\n' if hint else '') + '登录轻投后会自动保存，以后不用再输入。',
        'requestedSchema': {
            'type': 'object',
            'properties': {
                'username': {'type': 'string', 'title': '轻投用户名'},
                'password': {'type': 'string', 'title': '轻投密码'},
            },
            'required': ['username', 'password'],
        },
    })
    result = (reply or {}).get('result') or {}
    content = result.get('content') or {}
    if result.get('action') != 'accept' or not content.get('username') or not content.get('password'):
        raise LoginCancelled()
    return content['username'].strip(), content['password']


def applescript_quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def ask_dialog(prompt, hidden=False):
    script = ('text returned of (display dialog %s default answer "" %s with title "连接轻投" '
              'buttons {"取消", "登录"} default button "登录" cancel button "取消")'
              % (applescript_quote(prompt), 'with hidden answer' if hidden else ''))
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    except OSError:
        raise LoginCancelled()
    if result.returncode != 0:
        raise LoginCancelled()
    return result.stdout.rstrip('\n')


def ask_credentials(hint, use_terminal):
    if use_terminal:
        if hint:
            print(hint)
        return input('轻投用户名: ').strip(), getpass.getpass('轻投密码（不显示）: ')
    if session['client_form']:
        return ask_form(hint)
    prompt = (hint + '\n\n' if hint else '') + '请输入轻投用户名'
    username = ask_dialog(prompt).strip()
    return username, ask_dialog('请输入轻投密码', hidden=True)


def sign_key(username, password):
    body = urllib.parse.urlencode({'username': username, 'password': password, 'client': 'qtou-mcp-proxy'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(API_BASE + '/auth/login', data=body, method='POST'), timeout=20) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            data = json.load(error)
        except ValueError:
            return None, None, '登录失败（HTTP %s）' % error.code
    except (urllib.error.URLError, OSError):
        return None, None, '连不上轻投服务，请检查网络'
    payload = data.get('data') or data
    key = payload.get('agentKey') or ''
    if key.startswith('qtpat_'):
        return key, payload.get('agentKeyId'), None
    return None, None, str(data.get('msg') or payload.get('message') or '用户名或密码不对')


def login(use_terminal=False, reason=''):
    hint = reason
    for _ in range(MAX_LOGIN_ATTEMPTS):
        username, password = ask_credentials(hint, use_terminal)
        key, key_id, error = sign_key(username, password)
        if key:
            save_account(username, key, key_id)
            return key
        hint = error + '，请重新输入。'
    raise LoginCancelled()


def ensure_token(rejected=''):
    with login_lock:
        token = read_token()
        if token and token != rejected:
            return token
        reason = '轻投登录已失效，请重新登录。' if rejected else '首次使用轻投，请登录。'
        return login(reason=reason)


def revoke_key(key, key_id):
    if not key_id:
        return False
    request = urllib.request.Request(API_BASE + '/tokens/' + urllib.parse.quote(key_id), method='DELETE',
                                     headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def post(message, token):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
               'Authorization': 'Bearer ' + token}
    if session['id']:
        headers['Mcp-Session-Id'] = session['id']
    request = urllib.request.Request(MCP_URL, data=json.dumps(message).encode(), headers=headers, method='POST')
    try:
        response = urllib.request.urlopen(request, timeout=600)
        status = response.status
    except urllib.error.HTTPError as error:
        response, status = error, error.code
    with response:
        session_id = response.headers.get('Mcp-Session-Id')
        if session_id:
            session['id'] = session_id
        content_type = response.headers.get('Content-Type', '')
        raw = response.read().decode('utf-8', 'replace')
    return status, parse_mcp_body(raw, content_type)


def is_auth_failure(status, replies):
    if status == 401:
        return True
    return any(isinstance(reply, dict) and (reply.get('error') or {}).get('code') == AUTH_ERROR_CODE for reply in replies)


def initialize_upstream(token):
    session['id'] = None
    post(session['initialize'], token)
    post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, token)
    session['upstream_ready'] = True


def forward(message):
    token = ensure_token()
    if session['initialize'] and not session['upstream_ready']:
        initialize_upstream(token)
    status, replies = post(message, token)
    if is_auth_failure(status, replies):
        token = ensure_token(rejected=token)
        if session['initialize']:
            initialize_upstream(token)
        status, replies = post(message, token)
    return replies


def tool_result(payload, is_error=False):
    return {'content': [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)}], 'isError': is_error}


def account_summary():
    data = load_accounts()
    return {'current': data['current'],
            'accounts': [{'username': name, 'current': name == data['current'], 'savedAt': info.get('savedAt')}
                         for name, info in data['accounts'].items()]}


def call_local_tool(name, arguments):
    if name == 'qtou_account_list':
        return tool_result(account_summary())
    if name == 'qtou_account_add':
        with login_lock:
            login(reason='添加轻投账号。')
        return tool_result(dict(account_summary(), message='已登录并切换到新账号'))
    data = load_accounts()
    username = (arguments.get('username') or '').strip()
    if name == 'qtou_account_switch':
        if username not in data['accounts']:
            return tool_result({'error': {'code': 'NOT_FOUND', 'message': '本机没有这个账号，可先用 qtou_account_add 添加',
                                          'tool': name}}, is_error=True)
        data['current'] = username
        store_accounts(data)
        reset_upstream()
        return tool_result(dict(account_summary(), message='已切换到 %s' % username))
    if name == 'qtou_account_logout':
        username = username or data['current']
        account = data['accounts'].pop(username, None)
        if not account:
            return tool_result({'error': {'code': 'NOT_FOUND', 'message': '本机没有这个账号', 'tool': name}}, is_error=True)
        revoked = revoke_key(account['key'], account.get('keyId'))
        if data['current'] == username:
            data['current'] = next(iter(data['accounts']), None)
            reset_upstream()
        store_accounts(data)
        note = '服务端 key 已吊销' if revoked else '本机已删除；服务端 key 未能吊销（可能已失效），可在轻投网页管理'
        return tool_result(dict(account_summary(), message='已退出 %s，%s' % (username, note)))
    return tool_result({'error': {'code': 'NOT_FOUND', 'message': '未知工具', 'tool': name}}, is_error=True)


def with_local_tools(replies):
    for reply in replies:
        tools = (reply.get('result') or {}).get('tools') if isinstance(reply, dict) else None
        if isinstance(tools, list):
            tools.extend(LOCAL_TOOLS)
    return replies


def local_initialize(message):
    params = message.get('params') or {}
    return {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {
        'protocolVersion': params.get('protocolVersion') or '2024-11-05',
        'capabilities': {'tools': {}},
        'serverInfo': {'name': 'qtou-agent-mcp', 'version': 'proxy'},
    }}


def initialize(message):
    """Answer initialize without logging in: forms can only be shown after the handshake completes."""
    session['initialize'] = message
    session['client_form'] = 'elicitation' in ((message.get('params') or {}).get('capabilities') or {})
    token = read_token()
    if token:
        status, replies = post(message, token)
        if not is_auth_failure(status, replies):
            session['upstream_ready'] = True
            for reply in replies:
                emit(reply)
            return
    emit(local_initialize(message))


def error_reply(message, code, text):
    return {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': code, 'message': text}}


def handle(message):
    method = message.get('method')
    params = message.get('params') or {}
    try:
        if method == 'notifications/initialized' and not session['upstream_ready']:
            return
        if method == 'tools/call' and params.get('name') in LOCAL_TOOL_NAMES:
            replies = [{'jsonrpc': '2.0', 'id': message.get('id'),
                        'result': call_local_tool(params['name'], params.get('arguments') or {})}]
        elif method == 'tools/list':
            replies = with_local_tools(forward(message))
        else:
            replies = forward(message)
    except LoginCancelled:
        replies = [error_reply(message, -32001, '未登录轻投：已取消登录。再次使用轻投时会重新请你登录。')]
    except Exception as error:
        log('forward failed: %s' % type(error).__name__)
        replies = [error_reply(message, -32002, '轻投服务暂时不可用，请稍后重试')]
    if 'id' not in message:
        return
    for reply in replies:
        emit(reply)


def route(message):
    if 'method' not in message:
        waiter = pending_requests.get(message.get('id'))
        if waiter:
            waiter['reply'] = message
            waiter['event'].set()
        return
    if message['method'] == 'initialize':
        initialize(message)
        return
    threading.Thread(target=handle, args=(message,), daemon=True).start()


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            log('ignored a non-JSON line')
            continue
        if isinstance(message, dict):
            route(message)


def main():
    if sys.argv[1:] == ['--login']:
        try:
            login(use_terminal=sys.stdin.isatty())
        except LoginCancelled:
            sys.exit('已取消登录。')
        print('已登录轻投并设为当前账号（key 本身未显示）。')
        return
    serve()


if __name__ == '__main__':
    main()

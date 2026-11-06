#!/usr/bin/env python3
"""stdio MCP bridge to the qtou server with built-in login and multiple accounts.

The client (e.g. Codex) launches this as a stdio MCP server. Every JSON-RPC message is forwarded to
QTOU_MCP_URL with the current account's connector key. When there is no account or the key is rejected,
the user is asked for the qtou username/password, a key is signed and saved, and the request is retried,
so the first use logs in and later uses just work.

Host bots such as Grok Bot must pop RequestUserForm (kind=login, site=qtou.cn) before any login tool
call. This process cannot show that form. The form site is the hostname qtou.cn — not an IP, not
localhost, and not agent.bitilinks.cn. DEFAULT_AUTH_LOGIN_URL is only the proxy's login POST.

Platform limit: RequestUserForm secrets are delivered only to BrowserSecureFill. They are not returned
to the model and must not be copied into qtou_account_add arguments, chat, or any other channel. Do not
work around that by opening a bot-box desktop, copying ~/.qtou, or asking for a plaintext password.
On clients that actually show MCP elicitation, an empty qtou_account_add may still collect credentials
inside this bridge (never to the model). That path is optional. If it is cancelled or returns -32001,
the bridge returns AUTH_REQUIRED so the host pops RequestUserForm immediately instead of retrying.

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
DEFAULT_AUTH_LOGIN_URL = qtou_shared.DEFAULT_AUTH_LOGIN_URL
LOGIN_URL = qtou_shared.auth_login_url()
TOKEN_PATH = qtou_shared.TOKEN_PATH
ACCOUNTS_PATH = qtou_shared.ACCOUNTS_PATH
AUTH_ERROR_CODE = 10007
MAX_LOGIN_ATTEMPTS = 3
FORM_TIMEOUT_SECONDS = 600
FORM_SITE = 'qtou.cn'
AUTH_REQUIRED_MESSAGE = (
    '未登录轻投。第一步立刻弹出 RequestUserForm(kind=login, site=qtou.cn)，'
    '不要先无参数调用 qtou_account_add，也不要重试 MCP elicitation'
    '（Grok Bot 不展示 elicitation，会得到 -32001 cancelled）。'
    '表单 site 必须是 qtou.cn，禁止写成 IP、localhost、127.0.0.1 或 agent.bitilinks.cn。'
    '代签 POST（不是表单 site，禁止当成 site）：' + DEFAULT_AUTH_LOGIN_URL + '。'
    '平台限制：RequestUserForm 的密码只进入 BrowserSecureFill，不会作为 MCP 参数返回；'
    '不要把密码写入 qtou_account_add、聊天或其他工具。'
    '不要打开 bot 的 box 桌面代签，不要拷贝 ~/.qtou 或 qtpat_ key，不要在聊天里要明文密码。'
)

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
     'description': (
         '添加一个轻投账号并切换为当前账号。'
         'Grok Bot / Cursor bot 未登录时不要调用本工具：第一步是宿主弹出 '
         'RequestUserForm(kind=login, site=qtou.cn)。site 必须是 qtou.cn，'
         '不要写成 IP、localhost、127.0.0.1 或 agent.bitilinks.cn。'
         '代签 POST 是 ' + DEFAULT_AUTH_LOGIN_URL + '，那是代理的 POST 地址，不是表单 site。'
         '平台限制：RequestUserForm 的密码只进入 BrowserSecureFill，不会作为 MCP 参数返回；'
         '不要把密码写入本工具、聊天或其他通道，不要打开 bot box 桌面代签，不要拷贝 ~/.qtou。'
         'inputSchema 始终包含 username 与 password。宿主若把参数缓存成 properties:{}，'
         '那是旧缓存，不要据此无参数调用。无参数只留给确实会展示 MCP elicitation 的客户端'
         '（可选回退，凭据只进代理、不进模型）。Grok Bot 上 elicitation 不出现，调用以 -32001 结束。'
         '收到 -32001 或 AUTH_REQUIRED 时立刻改弹 RequestUserForm，不要重试 elicitation。'
     ),
     'inputSchema': {
         'type': 'object',
         'description': (
             'properties 始终包含 username 与 password。缓存成 properties:{} 时也不要无参数调用。'
             'Grok Bot 不要填写 password：RequestUserForm 的密钥只到 BrowserSecureFill，模型没有这份值。'
             '只有会展示 MCP elicitation 的客户端可以不传参数，由代理自己收凭据。'
         ),
         'properties': {
             'username': {'type': 'string', 'description': '轻投用户名。不要从聊天正文收集。'},
             'password': {
                 'type': 'string',
                 'description': (
                     '轻投密码。模型拿不到 RequestUserForm 的密钥（只到 BrowserSecureFill），'
                     '不要从聊天或表单结果抄进这个参数。'
                 ),
             },
         },
     }},
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


def auth_required_data():
    return {
        'code': 'AUTH_REQUIRED',
        'action': 'RequestUserForm',
        'kind': 'login',
        'site': FORM_SITE,
        'loginUrl': DEFAULT_AUTH_LOGIN_URL,
        'fields': [
            {'name': 'username', 'title': '轻投用户名', 'secret': False},
            {'name': 'password', 'title': '轻投密码', 'secret': True},
        ],
        'secretDelivery': 'BrowserSecureFill',
        'gap': (
            'RequestUserForm 的密码只进入 BrowserSecureFill，不会作为 MCP 参数返回，'
            '因此不能把表单密钥写入 qtou_account_add。不要改要聊天明文、打开 bot box 桌面或拷贝 ~/.qtou。'
        ),
        'doNot': [
            '不要先无参数调用 qtou_account_add；那会走 MCP elicitation，Grok Bot 不展示并返回 -32001',
            '收到 -32001 或 AUTH_REQUIRED 时立刻弹 RequestUserForm，不要重试 elicitation',
            'RequestUserForm 的 site 必须是 qtou.cn，不要写成 IP、localhost、127.0.0.1 或 agent.bitilinks.cn',
            'loginUrl 只是代签 POST，不是表单 site',
            '不要把 RequestUserForm 的密码抄进 MCP 参数或聊天（密钥只到 BrowserSecureFill）',
            '不要拷贝他人 ~/.qtou 或 qtpat_ key',
            '不要打开 bot 的 box 桌面代签页',
            '不要在聊天里索要明文密码或 key',
        ],
    }


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
        'message': (hint + '\n' if hint else '') + '登录轻投（演示站 %s）后会自动保存，以后不用再输入。' % DEFAULT_AUTH_LOGIN_URL,
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
        with urllib.request.urlopen(urllib.request.Request(LOGIN_URL, data=body, method='POST'), timeout=20) as response:
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


def keep_images_visible(replies):
    """Codex feeds the model structuredContent when present and drops image content, so page images
    (agent_documents_pages / agent_projects_bp_pages) never reach the model. Image results keep only content."""
    for reply in replies:
        result = reply.get('result') if isinstance(reply, dict) else None
        if isinstance(result, dict) and any(isinstance(item, dict) and item.get('type') == 'image'
                                            for item in result.get('content') or []):
            result.pop('structuredContent', None)
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
        username = (arguments.get('username') or '').strip()
        password = arguments.get('password') if isinstance(arguments.get('password'), str) else ''
        with login_lock:
            if username or password:
                if not username or not password:
                    return tool_result({'error': {'code': 'INVALID_ARGUMENT',
                                                  'message': '请通过安全表单同时提供 username 和 password',
                                                  'tool': name},
                                       'login': auth_required_data()}, is_error=True)
                key, key_id, error = sign_key(username, password)
                if not key:
                    return tool_result({'error': {'code': 'AUTH_FAILED',
                                                  'message': error or '登录失败', 'tool': name},
                                       'login': auth_required_data()}, is_error=True)
                save_account(username, key, key_id)
            else:
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


CONFIRM_TOOLS = {'agent_projects_confirm', 'agent_risk_alerts_create'}
internal_ids = itertools.count(1)


def call_upstream_tool(name, arguments):
    """Tool call made by the bridge itself; returns the parsed JSON payload or {}."""
    message = {'jsonrpc': '2.0', 'id': 'qtou-internal-%d' % next(internal_ids), 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments}}
    for reply in forward(message):
        content = ((reply.get('result') or {}).get('content') or []) if isinstance(reply, dict) else []
        for item in content:
            if item.get('type') == 'text':
                try:
                    return json.loads(item['text'])
                except ValueError:
                    return {}
    return {}


def first_value(data, *keys):
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        if value not in (None, ''):
            return str(value)
    return ''


def confirm_message(name, arguments):
    if name == 'agent_projects_confirm':
        pending = call_upstream_tool('agent_projects_get', {'pendingId': arguments.get('pendingId')})
        lines = ['确认把这个项目入正式池？',
                 '项目：' + (first_value(pending, 'projectName', 'project_name') or '（未取到）'),
                 '公司：' + (first_value(pending, 'companyName', 'company_name') or '（未取到）')]
        round_label = first_value(pending, 'roundLabel', 'round_label')
        industry = first_value(pending, 'industryLabel', 'industry_label')
        if round_label or industry:
            lines.append('轮次 / 行业：%s / %s' % (round_label or '-', industry or '-'))
        lines.append('待确认编号：' + str(arguments.get('pendingId') or ''))
        return '\n'.join(lines)
    grade = {'high': '高（网页显示「重大」）', 'medium': '中（网页显示「警告」）', 'low': '低（网页显示「警告」）'}
    return '\n'.join(['确认把这条风险预警写入轻投？',
                      '项目：' + str(arguments.get('projectId') or ''),
                      '等级：' + grade.get(str(arguments.get('grade')), str(arguments.get('grade') or '')),
                      '事件：' + str(arguments.get('matters') or arguments.get('theme') or ''),
                      '结论：' + str(arguments.get('conclusion') or arguments.get('evidence') or '')[:300]])


def confirmed_by_user(name, arguments):
    """Shows a confirm card (MCP form without fields); True only when the person accepts."""
    reply = request_client('elicitation/create', {'message': confirm_message(name, arguments),
                                                  'requestedSchema': {'type': 'object', 'properties': {}}})
    return ((reply or {}).get('result') or {}).get('action') == 'accept'


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


def error_reply(message, code, text, data=None):
    error = {'code': code, 'message': text}
    if data is not None:
        error['data'] = data
    return {'jsonrpc': '2.0', 'id': message.get('id'), 'error': error}


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
        elif (method == 'tools/call' and params.get('name') in CONFIRM_TOOLS and session['client_form']
              and not confirmed_by_user(params['name'], params.get('arguments') or {})):
            replies = [{'jsonrpc': '2.0', 'id': message.get('id'), 'result': tool_result(
                {'error': {'code': 'USER_DECLINED', 'message': '用户在确认卡上没有同意，本次未写入', 'tool': params['name']}},
                is_error=True)}]
        elif method == 'tools/call':
            replies = keep_images_visible(forward(message))
        else:
            replies = forward(message)
    except LoginCancelled:
        replies = [error_reply(message, -32001, AUTH_REQUIRED_MESSAGE, auth_required_data())]
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

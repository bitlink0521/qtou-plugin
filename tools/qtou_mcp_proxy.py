#!/usr/bin/env python3
"""stdio MCP bridge to the qtou server with built-in login and multiple accounts.

The client (e.g. Codex) launches this as a stdio MCP server. Every JSON-RPC message is forwarded to
QTOU_MCP_URL with the current account's connector key. When there is no account or the key is rejected,
the user is asked for the qtou username/password, a key is signed and saved, and the request is retried,
so the first use logs in and later uses just work.

Host bots should collect credentials with a chat secret-request (mask box) and/or
RequestUserForm, then call qtou_account_add. Args win over env QTOU_LOGIN_PASSWORD
(and optional QTOU_LOGIN_USERNAME); if both are missing, clients that advertise
elicitation (e.g. Codex) may still use elicitation/create. If none of the three are
available, the bridge returns AUTH_REQUIRED (action=HostSecureLogin) and tells the
host to issue secret-request for QTOU_LOGIN_PASSWORD. Do not clear those env vars
after a successful login. A webpage secure form alone does not hand the password
to this tool. This process cannot show the host's secure form itself. Site and
login URL arguments are ignored; POST always goes to the configured login URL
(default DEFAULT_AUTH_LOGIN_URL).

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
ENV_LOGIN_USERNAME = 'QTOU_LOGIN_USERNAME'
ENV_LOGIN_PASSWORD = 'QTOU_LOGIN_PASSWORD'
AUTH_REQUIRED_MESSAGE = (
    '未登录轻投。请由宿主发起安全登录采集账密；不要赌 MCP elicitation，不要在聊天里索要明文密码。'
    '首选：用聊天里的 secret-request 掩码框把密码写入环境变量 QTOU_LOGIN_PASSWORD'
    '（可选同时写入 QTOU_LOGIN_USERNAME），再调用 qtou_account_add（可不传 password）。'
    '每个 bot 必须使用自己发起的 secret-request，不能沿用其他 bot 写入的变量。'
    '也可以把 username 与 password 作为参数传入 qtou_account_add（不要回显）；'
    '或由宿主把账密 POST 到代签地址后，将返回的 agentKey 写入插件变量 QTOU_CONNECTOR_TOKEN（key 永不进聊天）。'
    '代签地址（轻投演示站 74，代理/宿主 POST 用，写死，禁止写成 agent.bitilinks.cn、localhost 或 127.0.0.1）：'
    + DEFAULT_AUTH_LOGIN_URL
    + '。字段：username=轻投用户名，password=轻投密码。'
    '优先级：工具参数 > 环境变量 > elicitation；三者都没有才返回本错误。'
    '登录成功后不必清除环境变量。禁止：拷贝他人 ~/.qtou 或 qtpat_ key；打开 bot 的 box 桌面代签页；在聊天里要明文密码；'
    '不要假设仅弹出网页安全表单就能把密码交给本工具；不要用工具参数覆盖代签站点或 URL。'
    '写入后调用 agent_health 冒烟。'
)

def plugin_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugin-meta.json')) as handle:
            return json.load(handle).get('version') or 'unknown'
    except (OSError, ValueError):
        return 'unknown'


# The server's audit marks generic script user agents (Python-urllib, curl…) as direct HTTP; name the proxy instead.
USER_AGENT = 'qtou-mcp-proxy/' + plugin_version()
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
     'description': ('添加一个轻投账号并切换为当前账号。宿主应先用 secret-request 写入 QTOU_LOGIN_PASSWORD'
                     '（可选 QTOU_LOGIN_USERNAME），或传入 username、password；参数优先于环境变量。'
                     '每个 bot 必须使用自己发起的 secret-request。不要在聊天里索要明文密码，也不要空参去赌 MCP elicitation。'
                     '三者都没有、elicitation 取消或返回 -32001 时，错误 data 为 AUTH_REQUIRED，提示宿主发 secret-request。'
                     '代签地址为 ' + DEFAULT_AUTH_LOGIN_URL + '（禁止写成 agent.bitilinks.cn 或 localhost，不可用参数覆盖）。'),
     'inputSchema': {'type': 'object', 'properties': {
         'username': {'type': 'string', 'description': '轻投用户名（来自宿主安全登录或环境变量 QTOU_LOGIN_USERNAME，不要从聊天正文收集）'},
         'password': {'type': 'string', 'description': '轻投密码（来自宿主安全登录或环境变量 QTOU_LOGIN_PASSWORD，不要回显）'},
     }}},
    {'name': 'qtou_account_switch',
     'description': '切换当前轻投账号，之后的轻投操作都以该账号身份进行。',
     'inputSchema': {'type': 'object', 'properties': {'username': {'type': 'string', 'description': '要切换到的账号用户名'}},
                     'required': ['username']}},
    {'name': 'qtou_account_logout',
     'description': '退出一个轻投账号并在服务端吊销它的 key；不传 username 则退出当前账号。',
     'inputSchema': {'type': 'object', 'properties': {'username': {'type': 'string', 'description': '要退出的账号用户名'}}}},
]
LOCAL_TOOL_NAMES = {tool['name'] for tool in LOCAL_TOOLS}
TOOLS_CACHE_PATH = os.path.expanduser('~/.qtou/tools-cache.json')
TOOLS_SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qtou_tools_snapshot.json')


def known_upstream_tools():
    """Business tools from the last signed-in tools/list, else the snapshot shipped with the plugin."""
    for path in (TOOLS_CACHE_PATH, TOOLS_SNAPSHOT_PATH):
        try:
            with open(path) as handle:
                tools = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(tools, list) and tools:
            return tools
    return []


def remember_upstream_tools(tools):
    upstream = [tool for tool in tools if isinstance(tool, dict) and tool.get('name') not in LOCAL_TOOL_NAMES]
    if upstream:
        write_private(TOOLS_CACHE_PATH, json.dumps(upstream, ensure_ascii=False))


class LoginCancelled(Exception):
    pass


def log(message):
    sys.stderr.write('[qtou-mcp] %s\n' % message)
    sys.stderr.flush()


def auth_required_data():
    return {
        'code': 'AUTH_REQUIRED',
        'action': 'HostSecureLogin',
        'loginUrl': DEFAULT_AUTH_LOGIN_URL,
        'fields': [
            {'name': 'username', 'title': '轻投用户名', 'secret': False},
            {'name': 'password', 'title': '轻投密码', 'secret': True},
        ],
        'submit': 'qtou_account_add',
        'env': {
            'password': ENV_LOGIN_PASSWORD,
            'username': ENV_LOGIN_USERNAME,
        },
        'secretRequest': ENV_LOGIN_PASSWORD,
        'doNot': [
            '不要依赖 MCP elicitation；取消或报 -32001 时由宿主发起安全登录，不要再试 elicitation',
            '不要把代签地址写成 agent.bitilinks.cn（工场）或 localhost / 127.0.0.1',
            '不要用工具参数覆盖代签站点或 URL',
            '不要拷贝他人 ~/.qtou 或 qtpat_ key',
            '不要打开 bot 的 box 桌面代签页',
            '不要在聊天里索要明文密码或 key',
            '不要假设仅弹出网页安全表单就能把密码交给本工具',
            '不要沿用其他 bot 发起的 secret-request；每个 bot 必须自己发',
        ],
    }


def _string_arg(arguments, name):
    value = arguments.get(name) if isinstance(arguments, dict) else None
    return value if isinstance(value, str) else ''


def env_login_username():
    value = os.environ.get(ENV_LOGIN_USERNAME)
    return value.strip() if isinstance(value, str) else ''


def env_login_password():
    value = os.environ.get(ENV_LOGIN_PASSWORD)
    return value if isinstance(value, str) else ''


def resolve_account_add_credentials(arguments):
    """Prefer tool arguments, then process env. Does not read elicitation or clear env."""
    username = _string_arg(arguments, 'username').strip() or env_login_username()
    password = _string_arg(arguments, 'password') or env_login_password()
    return username, password


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
    """Account changed: drop the upstream session and tell the client its tool list changed."""
    session['id'] = None
    session['upstream_ready'] = False
    if session['initialize']:
        emit({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed'})


def emit(message):
    """Reply using the same stdio framing the client used on its last request."""
    body = json.dumps(message, ensure_ascii=False)
    with write_lock:
        if session.get('stdio_framed'):
            raw = body.encode('utf-8')
            sys.stdout.write('Content-Length: %d\r\n\r\n' % len(raw))
            sys.stdout.write(body)
        else:
            sys.stdout.write(body + '\n')
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
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'User-Agent': USER_AGENT,
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
        username, password = resolve_account_add_credentials(arguments)
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
    project = call_upstream_tool('agent_portfolio_quarterly', {'projectId': arguments.get('projectId')})
    return '\n'.join(['确认把这条风险预警写入轻投？',
                      '项目：' + (first_value(project, 'projectName', 'project_name') or str(arguments.get('projectId') or '')),
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
            remember_upstream_tools(tools)
            tools.extend(LOCAL_TOOLS)
    return replies


def local_initialize(message):
    params = message.get('params') or {}
    return {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {
        'protocolVersion': params.get('protocolVersion') or '2024-11-05',
        'capabilities': {'tools': {'listChanged': True}},
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
                capabilities = (reply.get('result') or {}).get('capabilities') if isinstance(reply, dict) else None
                if isinstance(capabilities, dict):
                    tools = capabilities.get('tools')
                    capabilities['tools'] = dict(tools if isinstance(tools, dict) else {}, listChanged=True)
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
            # Discovery must not block on login, and many hosts never refetch after list_changed:
            # list the known business tools up front; calling one before login returns AUTH_REQUIRED.
            if not read_token():
                replies = [{'jsonrpc': '2.0', 'id': message.get('id'),
                            'result': {'tools': known_upstream_tools() + LOCAL_TOOLS}}]
            else:
                replies = with_local_tools(forward(message))
        elif method in ('resources/list', 'prompts/list') and not read_token():
            collection = 'resources' if method == 'resources/list' else 'prompts'
            replies = [{'jsonrpc': '2.0', 'id': message.get('id'), 'result': {collection: []}}]
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


def read_stdio_message():
    """Read one JSON-RPC message from stdin: Content-Length framed or NDJSON."""
    while True:
        header = sys.stdin.readline()
        if header == '':
            return None
        if header in ('\n', '\r\n'):
            continue
        if header.lower().startswith('content-length:'):
            session['stdio_framed'] = True
            try:
                length = int(header.split(':', 1)[1].strip())
            except ValueError:
                log('bad Content-Length header')
                continue
            while True:
                line = sys.stdin.readline()
                if line in ('', '\n', '\r\n'):
                    break
            raw = sys.stdin.read(length)
            if not raw:
                return None
            try:
                message = json.loads(raw)
            except ValueError:
                log('ignored a non-JSON framed body')
                continue
            return message if isinstance(message, dict) else None
        session['stdio_framed'] = False
        line = header.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            log('ignored a non-JSON line')
            continue
        return message if isinstance(message, dict) else None


def serve():
    while True:
        message = read_stdio_message()
        if message is None:
            break
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

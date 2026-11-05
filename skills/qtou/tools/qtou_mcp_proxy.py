#!/usr/bin/env python3
"""stdio MCP bridge to the qtou server with built-in login.

The client (e.g. Codex) launches this as a stdio MCP server. Every JSON-RPC message is forwarded to
QTOU_MCP_URL with the connector key from ~/.qtou/connector-token. When the key is missing or rejected,
a macOS dialog asks for the qtou username/password, a key is signed and saved, and the request is
retried, so the first use logs in and later uses just work. The password never passes through the chat.

`--login` runs the same login flow by hand (terminal prompts when available, dialogs otherwise).
"""
import getpass
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

MCP_URL = os.environ.get('QTOU_MCP_URL') or 'http://113.250.189.74:18081/api/v1/agent/mcp'
LOGIN_URL = MCP_URL.rsplit('/mcp', 1)[0] + '/auth/login'
TOKEN_PATH = os.path.expanduser('~/.qtou/connector-token')
AUTH_ERROR_CODE = 10007
MAX_LOGIN_ATTEMPTS = 3

write_lock = threading.Lock()
login_lock = threading.Lock()
session = {'id': None, 'initialize': None}


class LoginCancelled(Exception):
    pass


def log(message):
    sys.stderr.write('[qtou-mcp] %s\n' % message)
    sys.stderr.flush()


def read_token():
    try:
        with open(TOKEN_PATH) as handle:
            token = handle.read().strip()
    except OSError:
        return ''
    return token if token.startswith('qtpat_') else ''


def save_token(token):
    os.makedirs(os.path.dirname(TOKEN_PATH), mode=0o700, exist_ok=True)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(token)


def applescript_quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def ask_dialog(prompt, hidden=False):
    script = ('text returned of (display dialog %s default answer "" %s with title "连接轻投" '
              'buttons {"取消", "登录"} default button "登录" cancel button "取消")'
              % (applescript_quote(prompt), 'with hidden answer' if hidden else ''))
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if result.returncode != 0:
        raise LoginCancelled()
    return result.stdout.rstrip('\n')


def show_dialog(message):
    script = 'display dialog %s with title "连接轻投" buttons {"好"} default button "好"' % applescript_quote(message)
    subprocess.run(['osascript', '-e', script], capture_output=True)


def ask_credentials(hint, use_terminal):
    if use_terminal:
        if hint:
            print(hint)
        return input('轻投用户名: ').strip(), getpass.getpass('轻投密码（不显示）: ')
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
            return None, '登录失败（HTTP %s）' % error.code
    except (urllib.error.URLError, OSError):
        return None, '连不上轻投服务，请检查网络'
    payload = data.get('data') or data
    key = payload.get('agentKey') or ''
    if key.startswith('qtpat_'):
        return key, None
    return None, str(data.get('msg') or payload.get('message') or '用户名或密码不对')


def login(use_terminal=False, reason=''):
    hint = reason
    for _ in range(MAX_LOGIN_ATTEMPTS):
        username, password = ask_credentials(hint, use_terminal)
        key, error = sign_key(username, password)
        if key:
            save_token(key)
            return key
        hint = error + '，请重新输入。'
    if not use_terminal:
        show_dialog('多次登录失败，请确认账号后在 Codex 里重试。')
    raise LoginCancelled()


def ensure_token(rejected=''):
    with login_lock:
        token = read_token()
        if token and token != rejected:
            return token
        reason = '轻投登录已失效，请重新登录。' if rejected else '首次使用轻投，请登录。'
        return login(reason=reason)


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
    return status, parse_body(raw, content_type)


def parse_body(raw, content_type):
    if not raw.strip():
        return []
    if 'event-stream' in content_type:
        return [json.loads(line[5:]) for line in raw.splitlines() if line.startswith('data:') and line[5:].strip()]
    body = json.loads(raw)
    return body if isinstance(body, list) else [body]


def is_auth_failure(status, replies):
    if status == 401:
        return True
    return any(isinstance(reply, dict) and (reply.get('error') or {}).get('code') == AUTH_ERROR_CODE for reply in replies)


def forward(message):
    token = ensure_token()
    status, replies = post(message, token)
    if is_auth_failure(status, replies):
        token = ensure_token(rejected=token)
        if session['initialize'] and message.get('method') != 'initialize':
            session['id'] = None
            post(session['initialize'], token)
            post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, token)
        status, replies = post(message, token)
    return replies


def emit(reply):
    with write_lock:
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + '\n')
        sys.stdout.flush()


def error_reply(message, code, text):
    return {'jsonrpc': '2.0', 'id': message.get('id'), 'error': {'code': code, 'message': text}}


def handle(message):
    if message.get('method') == 'initialize':
        session['initialize'] = message
    try:
        replies = forward(message)
    except LoginCancelled:
        replies = [error_reply(message, -32001, '未登录轻投：已取消登录。再次使用轻投时会重新弹出登录框。')]
    except Exception as error:
        log('forward failed: %s' % type(error).__name__)
        replies = [error_reply(message, -32002, '轻投服务暂时不可用，请稍后重试')]
    if 'id' not in message:
        return
    for reply in replies:
        emit(reply)


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
        if message.get('method') == 'initialize':
            handle(message)
        else:
            threading.Thread(target=handle, args=(message,), daemon=True).start()


def main():
    if sys.argv[1:] == ['--login']:
        try:
            login(use_terminal=sys.stdin.isatty())
        except LoginCancelled:
            sys.exit('已取消登录。')
        print('已登录轻投，连接 key 已保存（key 本身未显示）。')
        return
    serve()


if __name__ == '__main__':
    main()

"""Helpers shared by every plugin tool: no-redirect JSON HTTP, Tavily, Grok structured output and the
local qtou account store. Standard library only. Callers keep their own error types and map HttpFailure."""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_MCP_URL = os.environ.get('QTOU_MCP_URL') or 'http://113.250.189.74:18081/api/v1/agent/mcp'
DEFAULT_AUTH_LOGIN_URL = 'http://113.250.189.74:18081/api/v1/agent/auth/login'


def auth_login_url():
    """Where to POST username/password for an agent key. QTOU_LOGIN_URL overrides; default is demo 74."""
    return (os.environ.get('QTOU_LOGIN_URL') or '').strip() or DEFAULT_AUTH_LOGIN_URL


TOKEN_PATH = os.path.expanduser('~/.qtou/connector-token')
ACCOUNTS_PATH = os.path.expanduser('~/.qtou/accounts.json')
MIGRATED_ACCOUNT_NAME = '已保存账号'
GROK_CREDENTIALS_PATH = os.path.expanduser('~/.qtou/grok-credentials')
TAVILY_KEY_PATH = os.path.expanduser('~/.qtou/tavily-key')
TAVILY_API = 'https://api.tavily.com'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def no_redirect_opener():
    return urllib.request.build_opener(NoRedirect()).open


class HttpFailure(RuntimeError):
    """Request failed; carries only the HTTP status (None when there was no HTTP response), never bodies or keys."""

    def __init__(self, status=None):
        super().__init__('HTTP %s' % status if status else 'request failed')
        self.status = status


def post_json(url, payload, bearer, opener=None, timeout=90):
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + bearer})
    try:
        with (opener or no_redirect_opener())(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise HttpFailure(status) from None
    except Exception:
        raise HttpFailure() from None


def public_url(url):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return parts.scheme in ('http', 'https') and bool(parts.hostname) and not parts.username and not parts.password


# Tavily. `request(url, payload)` returns parsed JSON; each caller supplies its own key and error mapping.

def tavily_key(key_path=None):
    """TAVILY_API_KEY, else the key saved in ~/.qtou/tavily-key, else ''."""
    key = os.environ.get('TAVILY_API_KEY', '').strip()
    if key:
        return key
    try:
        return Path(key_path or TAVILY_KEY_PATH).read_text().strip()
    except OSError:
        return ''


def tavily_search(request, query, include_domains=None, max_results=5):
    """Returns (rows, raw_hit_count); rows keep only public URLs: url, title, content, publishedDate."""
    payload = {'query': query, 'search_depth': 'advanced', 'max_results': max_results}
    if include_domains:
        payload['include_domains'] = include_domains
    data = request(TAVILY_API + '/search', payload)
    results = data.get('results') if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise ValueError('Tavily search response has no results list')
    rows = [{'url': row['url'], 'title': row.get('title') or '', 'content': row.get('content') or '',
             'publishedDate': row.get('published_date')}
            for row in results if isinstance(row, dict) and public_url(row.get('url'))]
    return rows, len(results)


def tavily_extract(request, urls):
    """Returns {url: row} for URLs whose full text was extracted (row has title, raw_content, published_date)."""
    data = request(TAVILY_API + '/extract', {'urls': list(urls), 'extract_depth': 'advanced', 'format': 'text'})
    wanted = set(urls)
    return {row['url']: row for row in (data.get('results') or [])
            if isinstance(row, dict) and row.get('url') in wanted and row.get('raw_content')}


# Grok structured output.

class GrokConfigError(ValueError):
    pass


def grok_config(credentials_file=None, default_file=None):
    """Explicit file, else GROK_API_KEY_FILE, else env keys, else ~/.qtou/grok-credentials when present."""
    key = os.environ.get('GROK_API_KEY') or os.environ.get('XAI_API_KEY')
    base = os.environ.get('GROK_BASE_URL') or os.environ.get('XAI_BASE_URL')
    file_path = credentials_file or os.environ.get('GROK_API_KEY_FILE')
    default_file = default_file or GROK_CREDENTIALS_PATH
    if not file_path and not key and os.path.exists(default_file):
        file_path = default_file
    if file_path:
        try:
            text = Path(file_path).read_text()
            urls = re.findall(r'https?://[^\s\"\']+', text)
            if not base and urls:
                base = urls[0].rstrip('/')
            if not key:
                candidates = [line.strip() for line in text.splitlines()
                              if line.strip() and not line.lstrip().startswith('#') and not re.search(r'https?://', line)]
                if len(candidates) != 1:
                    raise ValueError()
                key = re.split(r'[:=：]', candidates[0], maxsplit=1)[-1].strip().strip('\"\'')
        except Exception:
            raise GrokConfigError('Grok凭据文件不可用或格式不明确') from None
    base = (base or 'https://api.x.ai/v1').rstrip('/')
    parts = urlsplit(base)
    if not key or len(key) < 8 or '\n' in key:
        raise GrokConfigError('未配置Grok API凭据')
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise GrokConfigError('Grok地址须为无凭据、无查询参数的HTTPS API地址')
    model = os.environ.get('GROK_MODEL', 'grok-4.7')
    if not model.startswith('grok-'):
        raise GrokConfigError('补全模型须为Grok模型')
    return key, base, model


def grok_structured(request, base, model, instructions, user_payload, schema_name, schema, max_tokens):
    """Returns (parsed JSON object, raw response). `request(url, payload)` performs the call."""
    response = request(base + '/chat/completions', {
        'model': model,
        'messages': [{'role': 'system', 'content': instructions},
                     {'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': schema_name, 'strict': True, 'schema': schema}},
        'max_tokens': max_tokens})
    value = json.loads(response['choices'][0]['message']['content'])
    if not isinstance(value, dict):
        raise ValueError('Grok response is not a JSON object')
    return value, response


# Local qtou account store (~/.qtou, mode 600). The current account's key is mirrored to TOKEN_PATH.

def write_private(path, text):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(text)


def read_legacy_token(token_path=None):
    try:
        with open(token_path or TOKEN_PATH) as handle:
            token = handle.read().strip()
    except OSError:
        return ''
    return token if token.startswith('qtpat_') else ''


def load_accounts(accounts_path=None, token_path=None):
    accounts_path = accounts_path or ACCOUNTS_PATH
    try:
        with open(accounts_path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        legacy = read_legacy_token(token_path)
        if not legacy:
            return {'current': None, 'accounts': {}}
        data = {'current': MIGRATED_ACCOUNT_NAME,
                'accounts': {MIGRATED_ACCOUNT_NAME: {'key': legacy, 'keyId': None, 'savedAt': None}}}
        store_accounts(data, accounts_path, token_path)
    data.setdefault('accounts', {})
    if data.get('current') not in data['accounts']:
        data['current'] = next(iter(data['accounts']), None)
    return data


def store_accounts(data, accounts_path=None, token_path=None):
    token_path = token_path or TOKEN_PATH
    write_private(accounts_path or ACCOUNTS_PATH, json.dumps(data, ensure_ascii=False, indent=2))
    current = data['accounts'].get(data.get('current') or '')
    if current:
        write_private(token_path, current['key'])
    elif os.path.exists(token_path):
        os.remove(token_path)


def current_token(accounts_path=None, token_path=None):
    """Key of the current account, else QTOU_CONNECTOR_TOKEN, else ''."""
    data = load_accounts(accounts_path, token_path)
    account = data['accounts'].get(data.get('current') or '')
    if account:
        return account['key']
    env_token = os.environ.get('QTOU_CONNECTOR_TOKEN', '').strip()
    return env_token if env_token.startswith('qtpat_') else ''


def parse_mcp_body(raw, content_type):
    """JSON-RPC messages from a streamable-HTTP MCP response (plain JSON or SSE `data:` lines)."""
    if not raw.strip():
        return []
    if 'event-stream' in content_type:
        return [json.loads(line[5:]) for line in raw.splitlines() if line.startswith('data:') and line[5:].strip()]
    body = json.loads(raw)
    return body if isinstance(body, list) else [body]

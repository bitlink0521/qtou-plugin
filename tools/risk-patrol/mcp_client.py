"""qtou MCP JSON-RPC client. Credentials remain in process memory."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qtou_shared  # noqa: E402

DEFAULT_URL = qtou_shared.DEFAULT_MCP_URL


class McpError(RuntimeError):
    def __init__(self, code, message='轻投工具调用失败'):
        self.code = code
        super().__init__(message)


def local_token():
    """QTOU_CONNECTOR_TOKEN overrides for this process; otherwise the account currently logged in via the plugin."""
    env_token = os.environ.get('QTOU_CONNECTOR_TOKEN', '').strip()
    if env_token:
        if not env_token.startswith('qtpat_') or '\n' in env_token:
            raise McpError('AUTH_UNAVAILABLE', 'QTOU_CONNECTOR_TOKEN 格式不对')
        return env_token
    token = qtou_shared.current_token()
    if not token:
        raise McpError('AUTH_UNAVAILABLE', '未登录轻投：请先在客户端里登录，或设置 QTOU_CONNECTOR_TOKEN')
    return token


MAX_PAGES = 200


def all_items(client, tool, arguments=None):
    """Every item of a list tool, following page/hasMore; also accepts unpaged list or {items} replies."""
    items, page = [], 1
    while page <= MAX_PAGES:
        reply = client.call(tool, dict(arguments or {}, page=page, pageSize=50))
        if isinstance(reply, list):
            return reply
        if not isinstance(reply, dict) or not isinstance(reply.get('items'), list):
            raise McpError('INVALID_RESPONSE')
        items.extend(reply['items'])
        if not reply.get('hasMore'):
            return items
        page += 1
    raise McpError('INVALID_RESPONSE', '列表页数超出上限')


class LocalMcpClient:
    def __init__(self, url=DEFAULT_URL, token_provider=local_token, opener=None):
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username or parsed.password
                or parsed.path != '/api/v1/agent/mcp' or parsed.query or parsed.fragment):
            raise McpError('INVALID_ENDPOINT', '只允许轻投 MCP 入口 /api/v1/agent/mcp')
        self.url, self._token_provider = url, token_provider
        self._open = opener or qtou_shared.no_redirect_opener()
        self._id = 0

    def call(self, tool, arguments=None):
        self._id += 1
        body = {'jsonrpc': '2.0', 'id': self._id, 'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments or {}}}
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                        headers={'Authorization': 'Bearer ' + self._token_provider(),
                                                 'Content-Type': 'application/json',
                                                 'Accept': 'application/json, text/event-stream'})
        try:
            with self._open(request, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            error.close()
            raise McpError('UPSTREAM_UNAVAILABLE', '轻投服务不可用或响应无效') from None
        except Exception:
            raise McpError('UPSTREAM_UNAVAILABLE', '轻投服务不可用或响应无效') from None
        if not isinstance(payload, dict) or payload.get('id') != self._id:
            raise McpError('INVALID_RESPONSE')
        if 'error' in payload:
            raise McpError('RPC_ERROR')
        result = payload.get('result', {})
        try:
            value = result.get('structuredContent')
            if value is None:
                value = json.loads(''.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text'))
        except Exception:
            raise McpError('INVALID_RESPONSE') from None
        if result.get('isError'):
            raw = value.get('error', {}).get('code', '') if isinstance(value, dict) else ''
            allowed = {'NOT_FOUND', 'FORBIDDEN', 'INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'UPSTREAM_UNAVAILABLE'}
            raise McpError(raw if raw in allowed else 'TOOL_ERROR')
        return value

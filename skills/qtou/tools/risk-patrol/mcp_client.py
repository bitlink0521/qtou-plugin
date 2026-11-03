"""Local-only qtou JSON-RPC client. Credentials remain in process memory."""
import json
import os
import subprocess
import urllib.request
import urllib.error
from urllib.parse import urlsplit

# The plugin installer writes the real connector address to QTOU_MCP_URL.
DEFAULT_URL = os.environ.get('QTOU_MCP_URL') or 'http://127.0.0.1:8081/api/v1/agent/mcp'
LIB = '/Users/hesong/Desktop/qtou-deploy-2026-10-28/lib.sh'


class McpError(RuntimeError):
    def __init__(self, code, message='轻投工具调用失败'):
        self.code = code
        super().__init__(message)


def local_token():
    try:
        result = subprocess.run(['bash', '-c', 'source "$1" >/dev/null 2>&1; agentkey', '_', LIB],
                                capture_output=True, text=True, timeout=15)
    except Exception:
        raise McpError('AUTH_UNAVAILABLE', '本机凭据获取失败') from None
    value = result.stdout.strip()
    if result.returncode or not value.startswith('qtpat_') or '\n' in value:
        raise McpError('AUTH_UNAVAILABLE', '本机凭据不可用')
    return value


class LocalMcpClient:
    def __init__(self, url=DEFAULT_URL, token_provider=local_token, opener=None):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
                or parsed.port != 8081 or parsed.username or parsed.password
                or parsed.path != '/api/v1/agent/mcp' or parsed.query or parsed.fragment):
            raise McpError('INVALID_ENDPOINT', '只允许本机 8081 MCP 入口')
        self.url, self._token_provider = url, token_provider
        self._open = opener or urllib.request.build_opener(NoRedirect()).open
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
            raise McpError('UPSTREAM_UNAVAILABLE', '本机轻投服务不可用或响应无效') from None
        except Exception:
            raise McpError('UPSTREAM_UNAVAILABLE', '本机轻投服务不可用或响应无效') from None
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

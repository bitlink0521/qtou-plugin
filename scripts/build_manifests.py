#!/usr/bin/env python3
"""Generate every client's plugin manifest and MCP config from plugin-meta.json (the single source).

Usage: python3 scripts/build_manifests.py          # rewrite the files
       python3 scripts/build_manifests.py --check  # exit 1 if any file is out of date
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Only path placeholders allowed in the Grok/Cursor-plugin stdio MCP chain.
# CURSOR_PLUGIN_ROOT is expanded by Cursor/Grok hosts to the plugin install dir
# (see cursor.com/docs/reference/plugins). No connector tokens here.
ALLOWED_STDIO_PLACEHOLDERS = frozenset({'CURSOR_PLUGIN_ROOT'})

PLACEHOLDER_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


def build(meta):
    common = {key: meta[key] for key in ('name', 'version', 'description', 'author', 'homepage', 'repository', 'license', 'keywords')}
    logo = meta['logo']
    iface = dict(meta['interface'], websiteURL=meta['homepage'], logo='./' + logo, composerIcon='./' + logo)
    marketplace_entry = {'name': meta['name'], 'source': './', 'description': meta['description'],
                         'version': meta['version'], 'category': meta['interface']['category'].lower(), 'homepage': meta['homepage']}
    return {
        '.codex-plugin/plugin.json': dict(common, skills='./skills/', mcpServers='./.codex-mcp.json', interface=iface),
        '.agents/plugins/marketplace.json': {
            'name': meta['marketplace'], 'interface': {'displayName': meta['interface']['displayName']},
            'plugins': [{'name': meta['name'], 'source': {'source': 'local', 'path': './'},
                         'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                         'category': meta['interface']['category']}]},
        # Codex connects straight to the HTTPS endpoint and signs in with OAuth in the browser: no local Python.
        '.codex-mcp.json': {'mcpServers': {meta['name']: {'type': 'http', 'url': meta['mcpOAuthUrl']}}},
        '.claude-plugin/plugin.json': dict(common, logo=logo),
        '.claude-plugin/marketplace.json': {'name': meta['marketplace'], 'owner': meta['author'],
                                            'metadata': {'description': '轻投插件市场'}, 'plugins': [marketplace_entry]},
        '.grok-mcp.json': {'mcpServers': {meta['name']: {
            'command': 'python3',
            'args': ['${CURSOR_PLUGIN_ROOT}/' + meta['proxy']],
            'cwd': '${CURSOR_PLUGIN_ROOT}',
            'env': {'PYTHONPATH': '${CURSOR_PLUGIN_ROOT}/tools'},
        }}},
        '.grok-plugin/plugin.json': dict(common, logo=logo, mcpServers='./.grok-mcp.json'),
        '.mcp.json': {'mcpServers': {meta['name']: {'command': 'python3', 'args': ['${CLAUDE_PLUGIN_ROOT}/' + meta['proxy']]}}},
        # Grok Bot marketplace reads .cursor-plugin (empiric); point it at stdio proxy.
        # Root mcp.json stays HTTP for Cursor 直连 / 手动 HTTP. variables dropped: InstallPlugin
        # values do not populate QTOU_CONNECTOR_TOKEN on Grok; the host should pop
        # HostSecureLogin then call qtou_account_add with username/password (see skills/qtou-connect).
        # Codex may still use elicitation as a fallback; host bots must not gamble on it.
        '.cursor-plugin/plugin.json': dict(common, logo=logo, mcpServers='./.grok-mcp.json'),
        '.cursor-plugin/marketplace.json': {'name': meta['marketplace'], 'owner': meta['author'],
                                            'metadata': {'description': '轻投插件市场'}, 'plugins': [marketplace_entry]},
        'mcp.json': {'mcpServers': {meta['name']: {'type': 'http', 'url': meta['mcpUrl'],
                                                  'headers': {'Authorization': 'Bearer ${QTOU_CONNECTOR_TOKEN}'}}}},
    }


def render(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def _resolve_mcp_servers(cursor_plugin, root):
    """Return (label, mcpServers_dict) for whatever .cursor-plugin points at."""
    ref = cursor_plugin.get('mcpServers')
    if ref is None:
        raise ValueError('.cursor-plugin/plugin.json missing mcpServers')
    if isinstance(ref, dict):
        return ('inline', ref)
    if isinstance(ref, str):
        path = root / ref
        if not path.is_file():
            raise ValueError('.cursor-plugin mcpServers path not found: %s' % ref)
        data = json.loads(path.read_text())
        servers = data.get('mcpServers')
        if not isinstance(servers, dict):
            raise ValueError('%s missing mcpServers object' % ref)
        return (ref, servers)
    raise ValueError('.cursor-plugin mcpServers must be a path string or inline object')


def validate_cursor_plugin_stdio(root=ROOT, cursor_plugin=None):
    """Ensure Grok marketplace path (.cursor-plugin) wires stdio only, no HTTP, no stray ${VARS}.

    Allowed placeholders: CURSOR_PLUGIN_ROOT only (plugin install root).
    """
    if cursor_plugin is None:
        cursor_plugin = json.loads((root / '.cursor-plugin' / 'plugin.json').read_text())
    label, servers = _resolve_mcp_servers(cursor_plugin, root)
    if not servers:
        raise ValueError('%s has empty mcpServers' % label)
    blob = json.dumps(servers, ensure_ascii=False)
    found = set(PLACEHOLDER_RE.findall(blob))
    extra = found - ALLOWED_STDIO_PLACEHOLDERS
    if extra:
        raise ValueError('stdio MCP chain has non-whitelisted placeholders: %s' % ', '.join(sorted(extra)))
    for name, server in servers.items():
        if not isinstance(server, dict):
            raise ValueError('server %s must be an object' % name)
        if 'command' not in server:
            raise ValueError('server %s must be stdio (command), got keys %s' % (name, sorted(server)))
        if 'url' in server:
            raise ValueError('server %s must not have url (HTTP not allowed on .cursor-plugin chain)' % name)
        stype = server.get('type')
        if isinstance(stype, str) and stype.lower() in ('http', 'streamable-http', 'sse'):
            raise ValueError('server %s must not use type %s' % (name, stype))
    return label, sorted(servers)


def main():
    meta = json.loads((ROOT / 'plugin-meta.json').read_text())
    built = build(meta)
    stale = []
    for relative, value in built.items():
        path = ROOT / relative
        text = render(value)
        if '--check' in sys.argv:
            if not path.exists() or path.read_text() != text:
                stale.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    # Always validate the on-disk (.check) or just-written (.cursor-plugin) stdio chain.
    try:
        cursor_plugin = built['.cursor-plugin/plugin.json'] if '--check' not in sys.argv else None
        # On --check, read from disk (must match built when not stale); still validate disk/built content.
        if '--check' in sys.argv:
            # Validate the built intent even if disk is stale, and also disk if present.
            validate_cursor_plugin_stdio(ROOT, cursor_plugin=built['.cursor-plugin/plugin.json'])
            if (ROOT / '.cursor-plugin' / 'plugin.json').is_file():
                validate_cursor_plugin_stdio(ROOT)
        else:
            validate_cursor_plugin_stdio(ROOT)
    except ValueError as err:
        print('cursor-plugin stdio validation failed: %s' % err)
        return 1
    if stale:
        print('out of date, run scripts/build_manifests.py: ' + ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

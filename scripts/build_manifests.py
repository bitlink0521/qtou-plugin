#!/usr/bin/env python3
"""Generate every client's plugin manifest and MCP config from plugin-meta.json (the single source).

Usage: python3 scripts/build_manifests.py          # rewrite the files
       python3 scripts/build_manifests.py --check  # exit 1 if any file is out of date
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(meta):
    common = {key: meta[key] for key in ('name', 'version', 'description', 'author', 'homepage', 'repository', 'license', 'keywords')}
    logo = meta['logo']
    iface = dict(meta['interface'], websiteURL=meta['homepage'], logo='./' + logo, composerIcon='./' + logo)
    proxy_relative = './' + meta['proxy']
    marketplace_entry = {'name': meta['name'], 'source': './', 'description': meta['description'],
                         'version': meta['version'], 'category': meta['interface']['category'].lower(), 'homepage': meta['homepage']}
    return {
        '.codex-plugin/plugin.json': dict(common, skills='./skills/', mcpServers='./.codex-mcp.json', interface=iface),
        '.agents/plugins/marketplace.json': {
            'name': meta['marketplace'], 'interface': {'displayName': meta['interface']['displayName']},
            'plugins': [{'name': meta['name'], 'source': {'source': 'local', 'path': './'},
                         'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                         'category': meta['interface']['category']}]},
        '.codex-mcp.json': {'mcpServers': {meta['name']: {'command': 'python3', 'args': [proxy_relative], 'cwd': '.',
                                                         'startup_timeout_sec': 300, 'tool_timeout_sec': 600}}},
        '.claude-plugin/plugin.json': dict(common, logo=logo),
        '.claude-plugin/marketplace.json': {'name': meta['marketplace'], 'owner': meta['author'],
                                            'metadata': {'description': '轻投插件市场'}, 'plugins': [marketplace_entry]},
        '.grok-plugin/plugin.json': dict(common, logo=logo),
        '.mcp.json': {'mcpServers': {meta['name']: {'command': 'python3', 'args': ['${CLAUDE_PLUGIN_ROOT}/' + meta['proxy']]}}},
        '.cursor-plugin/plugin.json': dict(common, logo=logo, variables={
            'type': 'object', 'required': ['QTOU_CONNECTOR_TOKEN'],
            'properties': {'QTOU_CONNECTOR_TOKEN': {'type': 'string', 'title': '轻投 Agent Key',
                                                    'description': 'Bearer qtpat_…（bot 代登录签发后写入；勿手抄到聊天）'}}}),
        '.cursor-plugin/marketplace.json': {'name': meta['marketplace'], 'owner': meta['author'],
                                            'metadata': {'description': '轻投插件市场'}, 'plugins': [marketplace_entry]},
        'mcp.json': {'mcpServers': {meta['name']: {'type': 'http', 'url': meta['mcpUrl'],
                                                  'headers': {'Authorization': 'Bearer ${QTOU_CONNECTOR_TOKEN}'}}}},
    }


def render(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def main():
    meta = json.loads((ROOT / 'plugin-meta.json').read_text())
    stale = []
    for relative, value in build(meta).items():
        path = ROOT / relative
        text = render(value)
        if '--check' in sys.argv:
            if not path.exists() or path.read_text() != text:
                stale.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print('out of date, run scripts/build_manifests.py: ' + ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

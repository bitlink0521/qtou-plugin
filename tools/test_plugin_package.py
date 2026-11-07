#!/usr/bin/env python3
"""Installable tree: stdio proxy from a copied package, not the dev import."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ('qtou-bp-intake', 'qtou-connect', 'qtou-dd-report', 'qtou-risk-alert')
FORBIDDEN_CALLS = (
    'agent_projects_company_choose(',
    'agent_projects_bp_upload_url(',
    'agent_risk_threshold_get(',
)


class HitServer(BaseHTTPRequestHandler):
    hits = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0') or '0')
        if length:
            self.rfile.read(length)
        HitServer.hits.append(self.path)
        body = b'{"jsonrpc":"2.0","result":{"tools":[]}}'
        self.send_response(500)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def copy_package(destination):
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'), dirs_exist_ok=True)


class PackageTests(unittest.TestCase):
    def test_skill_names_paths_and_missing_tools_are_explicit(self):
        skills_root = os.path.join(ROOT, 'skills')
        found = sorted(name for name in os.listdir(skills_root) if os.path.isdir(os.path.join(skills_root, name)))
        self.assertEqual(found, sorted(SKILLS))
        for name in SKILLS:
            path = os.path.join(skills_root, name, 'SKILL.md')
            text = open(path, encoding='utf-8').read()
            front = text.split('---', 2)[1]
            declared = [line.split(':', 1)[1].strip() for line in front.splitlines() if line.startswith('name:')]
            self.assertEqual(declared, [name])
        corpus = []
        for dirpath, _, filenames in os.walk(skills_root):
            for filename in filenames:
                if filename.endswith('.md'):
                    corpus.append(open(os.path.join(dirpath, filename), encoding='utf-8').read())
        joined = '\n'.join(corpus)
        for call in FORBIDDEN_CALLS:
            self.assertNotIn(call, joined)
        self.assertIn('risk_config_get()', joined)
        self.assertIn('agent_projects_bp_attach(', joined)
        self.assertIn('随包目录没有 `agent_projects_company_choose`', joined)

    def test_manifests_point_at_stdio_and_shipped_skills(self):
        codex = json.load(open(os.path.join(ROOT, '.codex-plugin', 'plugin.json'), encoding='utf-8'))
        cursor = json.load(open(os.path.join(ROOT, '.cursor-plugin', 'plugin.json'), encoding='utf-8'))
        self.assertEqual(codex.get('skills'), './skills/')
        self.assertEqual(cursor.get('skills'), './skills/')
        for relative in ('.grok-plugin/plugin.json', '.claude-plugin/plugin.json'):
            manifest = json.load(open(os.path.join(ROOT, relative), encoding='utf-8'))
            self.assertNotIn('skills', manifest, relative)
        for relative, arg in (
            ('mcp.json', './tools/qtou_mcp_proxy.py'),
            ('.codex-mcp.json', './tools/qtou_mcp_proxy.py'),
            ('.grok-mcp.json', '${CURSOR_PLUGIN_ROOT}/tools/qtou_mcp_proxy.py'),
            ('.mcp.json', '${CLAUDE_PLUGIN_ROOT}/tools/qtou_mcp_proxy.py'),
        ):
            server = json.load(open(os.path.join(ROOT, relative), encoding='utf-8'))['mcpServers']['qtou']
            self.assertEqual(server['command'], 'python3', relative)
            self.assertIn(arg, server['args'], relative)
            self.assertNotIn('url', server, relative)
            self.assertNotEqual(server.get('type'), 'http', relative)
        example_path = os.path.join(ROOT, 'examples', 'http-mcp.example.json')
        example = json.load(open(example_path, encoding='utf-8'))['mcpServers']['qtou']
        self.assertEqual(example['type'], 'http')
        referenced = []
        for dirpath, _, filenames in os.walk(ROOT):
            if '.git' in dirpath.split(os.sep):
                continue
            for filename in filenames:
                if not filename.endswith('.json'):
                    continue
                full = os.path.join(dirpath, filename)
                if os.path.abspath(full) == os.path.abspath(example_path):
                    continue
                text = open(full, encoding='utf-8').read()
                if 'http-mcp.example.json' in text or '"type": "http"' in text:
                    referenced.append(os.path.relpath(full, ROOT))
        self.assertEqual(referenced, [])

    def test_skill_links_and_named_resources_exist(self):
        skills_root = os.path.join(ROOT, 'skills')
        for dirpath, _, filenames in os.walk(skills_root):
            for filename in filenames:
                if not filename.endswith('.md'):
                    continue
                full = os.path.join(dirpath, filename)
                text = open(full, encoding='utf-8').read()
                for match in __import__('re').findall(r'\[[^\]]+\]\(([^)]+)\)', text):
                    target = match.split('#', 1)[0].strip()
                    if not target or target.startswith(('http://', 'https://', 'mailto:')):
                        continue
                    self.assertTrue(os.path.isfile(os.path.join(dirpath, target)), '%s -> %s' % (full, target))
        workflow = os.path.join(ROOT, 'tools', 'project-enrichment', 'workflow.py')
        self.assertTrue(os.path.isfile(workflow))
        enrichment = open(os.path.join(skills_root, 'qtou-bp-intake', 'ENRICHMENT.md'), encoding='utf-8').read()
        self.assertIn('tools/project-enrichment/workflow.py', enrichment)

    def test_copied_package_stdio_lists_36_tools_without_hitting_upstream(self):
        server = HTTPServer(('127.0.0.1', 0), HitServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/api/v1/agent' % server.server_port
        packed = tempfile.mkdtemp(prefix='qtou-pack-')
        home = tempfile.mkdtemp(prefix='qtou-home-')
        copy_package(packed)
        catalog = json.load(open(os.path.join(packed, 'tools', 'qtou_tool_catalog.json'), encoding='utf-8'))
        expected = [item['name'] for item in catalog['tools']] + [
            'qtou_account_list', 'qtou_account_add', 'qtou_account_switch', 'qtou_account_logout']
        self.assertEqual(len(expected), 36)
        env = {
            'HOME': home,
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'PYTHONUNBUFFERED': '1',
            'PYTHONIOENCODING': 'utf-8',
            'QTOU_MCP_URL': base + '/mcp',
            'QTOU_LOGIN_URL': base + '/auth/login',
        }
        proc = subprocess.Popen(
            [sys.executable, os.path.join(packed, 'tools', 'qtou_mcp_proxy.py')],
            cwd=packed,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}) + '\n')
            proc.stdin.flush()
            listed = json.loads(proc.stdout.readline())
            proc.stdin.write(json.dumps({
                'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                'params': {'name': 'agent_health', 'arguments': {}},
            }) + '\n')
            proc.stdin.flush()
            denied = json.loads(proc.stdout.readline())
        finally:
            proc.kill()
            proc.wait(timeout=5)
            server.shutdown()
            shutil.rmtree(packed, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
        self.assertEqual(HitServer.hits, [])
        self.assertEqual([item['name'] for item in listed['result']['tools']], expected)
        self.assertTrue(all(item.get('description') and isinstance(item.get('inputSchema'), dict)
                            for item in listed['result']['tools']))
        self.assertEqual(denied['error']['code'], -32001)
        self.assertEqual(denied['error']['data']['code'], 'AUTH_REQUIRED')


if __name__ == '__main__':
    unittest.main()

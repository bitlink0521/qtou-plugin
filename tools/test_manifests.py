import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_manifests as bm  # noqa: E402


class ManifestTests(unittest.TestCase):
    def test_generated_manifests_are_in_sync_with_plugin_meta(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_manifests.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cursor_plugin_stdio_validation_passes_on_generated_tree(self):
        label, names = bm.validate_cursor_plugin_stdio(ROOT)
        self.assertEqual(label, './.grok-mcp.json')
        self.assertEqual(names, ['qtou'])

    def test_cursor_plugin_stdio_rejects_http_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.cursor-plugin').mkdir()
            mcp = {'mcpServers': {'qtou': {'type': 'http', 'url': 'http://example.test/mcp'}}}
            (root / '.grok-mcp.json').write_text(json.dumps(mcp))
            (root / '.cursor-plugin' / 'plugin.json').write_text(json.dumps({
                'name': 'qtou', 'mcpServers': './.grok-mcp.json',
            }))
            with self.assertRaises(ValueError) as ctx:
                bm.validate_cursor_plugin_stdio(root)
            msg = str(ctx.exception)
            self.assertTrue('command' in msg or 'url' in msg or 'http' in msg.lower(), msg)

    def test_cursor_plugin_stdio_rejects_connector_token_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.cursor-plugin').mkdir()
            mcp = {'mcpServers': {'qtou': {
                'command': 'python3',
                'args': ['${CURSOR_PLUGIN_ROOT}/tools/qtou_mcp_proxy.py'],
                'env': {'QTOU_CONNECTOR_TOKEN': '${QTOU_CONNECTOR_TOKEN}'},
            }}}
            (root / '.grok-mcp.json').write_text(json.dumps(mcp))
            (root / '.cursor-plugin' / 'plugin.json').write_text(json.dumps({
                'name': 'qtou', 'mcpServers': './.grok-mcp.json',
            }))
            with self.assertRaises(ValueError) as ctx:
                bm.validate_cursor_plugin_stdio(root)
            self.assertIn('QTOU_CONNECTOR_TOKEN', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()

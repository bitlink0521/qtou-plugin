import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qtou_shared

CLEAN_ENV = {name: '' for name in ('GROK_API_KEY', 'XAI_API_KEY', 'GROK_BASE_URL', 'XAI_BASE_URL',
                                   'GROK_API_KEY_FILE', 'TAVILY_API_KEY')}


class LocalCredentialTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, CLEAN_ENV)
        environment.start()
        self.addCleanup(environment.stop)

    def path(self, name, text=None):
        path = Path(self.directory.name) / name
        if text is not None:
            path.write_text(text)
        return str(path)

    def test_grok_uses_saved_file_when_nothing_else_is_configured(self):
        saved = self.path('grok', 'key：test-key-123456\n\nurl：https://gateway.example.com/v1\n')
        self.assertEqual(qtou_shared.grok_config(default_file=saved),
                         ('test-key-123456', 'https://gateway.example.com/v1', 'grok-4.7'))

    def test_grok_explicit_file_wins_over_saved_file(self):
        saved = self.path('saved', 'saved-key-123456\n')
        explicit = self.path('explicit', 'explicit-key-123456\n')
        self.assertEqual(qtou_shared.grok_config(explicit, default_file=saved)[0], 'explicit-key-123456')

    def test_grok_env_key_wins_over_saved_file(self):
        saved = self.path('saved', 'saved-key-123456\n')
        with patch.dict(os.environ, {'GROK_API_KEY': 'env-key-123456'}):
            self.assertEqual(qtou_shared.grok_config(default_file=saved)[0], 'env-key-123456')

    def test_grok_without_any_credentials_fails(self):
        with self.assertRaises(qtou_shared.GrokConfigError):
            qtou_shared.grok_config(default_file=self.path('missing'))

    def test_tavily_key_prefers_env_then_saved_file(self):
        saved = self.path('tavily', 'tvly-saved\n')
        self.assertEqual(qtou_shared.tavily_key(saved), 'tvly-saved')
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'tvly-env'}):
            self.assertEqual(qtou_shared.tavily_key(saved), 'tvly-env')
        self.assertEqual(qtou_shared.tavily_key(self.path('missing')), '')


if __name__ == '__main__':
    unittest.main()

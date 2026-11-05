import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_generated_manifests_are_in_sync_with_plugin_meta(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_manifests.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()

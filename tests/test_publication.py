"""Publication guards tested with deliberately fake credentials in disposable Git."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_secrets


class PublicationTests(unittest.TestCase):
    def test_sensitive_paths_are_blocked(self):
        for path in ['.env', '.env.local', 'data/personal.sqlite3', '.conda-env/python.exe',
                     'exports/notes.json', '.qa/data/demo.sqlite3', 'keys/private.pem', 'ProjectFlow-personal-me-export.json']:
            self.assertTrue(check_secrets.blocked_path(path), path)
        for path in ['.env.example', 'projectflow/llm.py', 'docs/DEVELOPMENT_REPORT.md']:
            self.assertFalse(check_secrets.blocked_path(path), path)

    def test_credentials_detected_without_printing_values(self):
        fake = 'sk-' + 'A' * 40
        self.assertTrue(check_secrets.inspect(fake.encode(), 'example.py'))
        literal = 'LLM_API_KEY=' + 'B' * 25
        self.assertTrue(check_secrets.inspect(literal.encode(), '.env.example'))
        self.assertEqual(check_secrets.inspect(b'LLM_API_KEY=\n', '.env.example'), [])
        self.assertEqual(check_secrets.inspect(b"key = 'PRIVATE_KEY'", 'tests/test_core.py'), [])

    def test_deleted_credentials_remain_detectable_in_history(self):
        temp_root = Path(__file__).parent / '.tmp'
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            root = Path(folder)
            def git(*args):
                subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            git('init', '-b', 'main')
            git('config', 'user.name', 'ProjectFlow Test')
            git('config', 'user.email', 'test@example.invalid')
            (root / 'example.txt').write_text('sk-' + 'A' * 40, 'utf-8')
            git('add', 'example.txt')
            git('commit', '-m', 'Synthetic fixture')
            (root / 'example.txt').write_text('Removed fixture', 'utf-8')
            git('add', 'example.txt')
            git('commit', '-m', 'Remove fixture')
            git('commit', '--allow-empty', '-m', 'Synthetic commit-message fixture: ' + 'sk-' + 'C' * 40)
            with patch.object(check_secrets, 'ROOT', root):
                counts, findings = check_secrets.scan()
            self.assertGreater(counts['historical_objects'], 0)
            self.assertTrue(any(scope == 'history' and label == 'provider-api-key' for scope, _, label, _ in findings))
            self.assertTrue(any(scope == 'history' and path.startswith('.history/commit-') and label == 'provider-api-key' for scope, path, label, _ in findings))


if __name__ == '__main__':
    unittest.main()

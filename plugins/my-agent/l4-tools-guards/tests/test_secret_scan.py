"""scripts/secret-scan.py: the check before a result leaves the task folder (architecture 4.12 "바깥으로 나가기 전 점검")."""
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script

SCRIPT = L4 / 'scripts' / 'secret-scan.py'
FAKE = {   # built at run time so this file itself holds no secret-shaped text
    'aws-key': 'AKIA' + 'ABCDEFGHIJKLMNOP',
    'private-key': '-----BEGIN RSA ' + 'PRIVATE KEY-----',
    'env-line': 'API_' + 'TOKEN=abc123',
    'github-token': 'ghp_' + 'a' * 36,
    'anthropic-key': 'sk-ant-' + 'api03-' + 'x' * 24,
}


class SecretScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_hits_each_kind(self):
        for kind, text in FAKE.items():
            with self.subTest(kind=kind):
                f = self.root / f'{kind}.md'
                f.write_text(f'# note\n\nsome text {text} more\n', encoding='utf-8')
                r = run_script(SCRIPT, str(f))
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stdout, f'{f}:3: {kind}\n')

    def test_scan_clean_exit0(self):
        f = self.root / 'clean.md'
        f.write_text('# note\n\nAKIA is a prefix. TOKEN is a word. sk-ant is short.\n', encoding='utf-8')
        r = run_script(SCRIPT, str(f))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_scan_walks_dir(self):
        (self.root / 'sub').mkdir()
        (self.root / 'sub' / 'a.html').write_text(FAKE['github-token'], encoding='utf-8')
        (self.root / 'b.bin').write_bytes(b'\xff\xfe\x00binary')
        r = run_script(SCRIPT, str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, f"{self.root / 'sub' / 'a.html'}:1: github-token\n")

    def test_missing_path_is_an_error(self):
        r = run_script(SCRIPT, str(Path(self.tmp.name) / 'nope.md'))
        self.assertEqual(r.returncode, 2)
        self.assertIn('nope.md', r.stderr)

    def test_no_args_is_usage_error(self):
        self.assertEqual(run_script(SCRIPT).returncode, 2)


if __name__ == '__main__':
    unittest.main()

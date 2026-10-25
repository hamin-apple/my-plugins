"""scripts/feedback.py: retro improvement points in the plugin's feedback.md (architecture 4.11)."""
import datetime
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script

SCRIPT = L4 / 'scripts' / 'feedback.py'
EMPTY = '# my-agent feedback\n\n형식: …\n\n## Open\n\n## Done\n\n- [done] L1 2026-10-01 t: x → y\n'


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'feedback.md'
        self.file.write_text(EMPTY, encoding='utf-8')
        self.env = {'MA_FEEDBACK_FILE': str(self.file)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_fb(self, *args):
        return run_script(SCRIPT, *args, env=self.env)

    def test_add_and_count(self):
        r = self.run_fb('add', 'L2', '261025-a', 'verifier가 인용을 3개만 확인함')
        self.assertEqual(r.returncode, 0, r.stderr)
        today = datetime.date.today().isoformat()
        text = self.file.read_text(encoding='utf-8')
        line = f'- [open] L2 {today} 261025-a: verifier가 인용을 3개만 확인함'
        self.assertIn(line, text)
        self.assertLess(text.index(line), text.index('## Done'))
        self.assertIn('- [done] L1 2026-10-01 t: x → y', text)
        r = self.run_fb('count')
        self.assertEqual(r.stdout, 'L1 0 · L2 1 · L3 0 · L4 0\n')

    def test_count_review_line_at_four(self):
        for i in range(4):
            self.run_fb('add', 'L4', f'261025-{i}', f'point {i}')
        r = self.run_fb('count')
        self.assertEqual(r.stdout, 'L1 0 · L2 0 · L3 0 · L4 4\nREVIEW: L4 has 4 open items\n')

    def test_missing_file_counts_zero(self):
        self.file.unlink()
        self.assertEqual(self.run_fb('count').stdout, 'L1 0 · L2 0 · L3 0 · L4 0\n')

    def test_bad_args(self):
        for args in ([], ['add', 'L5', 't', 'x'], ['add', 'L1', 't'], ['add', 'L1', 't', ' '], ['drop']):
            self.assertEqual(self.run_fb(*args).returncode, 2, args)


if __name__ == '__main__':
    unittest.main()

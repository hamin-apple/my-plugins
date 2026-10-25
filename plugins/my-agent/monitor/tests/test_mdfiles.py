import unittest
from pathlib import Path

from monitor.mdfiles import read_criteria, read_intake, read_plan, read_verify

FX = Path(__file__).resolve().parent / 'fixtures' / 'projects'
HOOKS = FX / 'obsidian-notes/docs/agent/261023-hooks-notify-note'
CLI = FX / 'claude-sessions/docs/agent/261024-cli-json-output'
FLIGHT = FX / 'flight-search/docs/agent/261021-flight-watch'
WEEKLY = FX / 'work-notes/docs/agent/261022-weekly-report'


class MdFilesTest(unittest.TestCase):
    def test_intake_fields(self):
        i = read_intake(HOOKS / 'intake.md')
        self.assertEqual(i['status'], 'done')
        self.assertEqual(i['profile'], 'research')
        self.assertEqual(i['delivered'], ['docs/notes/claude-hooks-notify.md'])
        self.assertEqual(i['title'], 'hooks로 승인 알림 보내는 방법 조사 → 노트')

    def test_intake_aborted(self):
        self.assertEqual(read_intake(FLIGHT / 'intake.md')['status'], 'aborted')

    def test_criteria_and_verify(self):
        self.assertEqual(read_criteria(HOOKS / 'scope.md'), 5)
        self.assertEqual(read_verify(HOOKS / 'verify.md'), ['p'] * 5)
        self.assertEqual(read_criteria(WEEKLY / 'plan.md'), 3)

    def test_plan_estimate_and_approval(self):
        p = read_plan(CLI / 'plan.md')
        self.assertEqual(p['estimate_k'], 600)
        self.assertEqual(p['approved_at'], '2026-10-24 15:55')
        self.assertTrue(p['mockup'].startswith('Kind: CLI 입출력'))

    def test_missing_files(self):
        self.assertIsNone(read_intake(Path('/nonexistent/intake.md')))
        self.assertEqual(read_criteria(Path('/nonexistent/scope.md')), 0)
        self.assertEqual(read_verify(Path('/nonexistent/verify.md')), [])
        self.assertIsNone(read_plan(Path('/nonexistent/plan.md'))['estimate_k'])


if __name__ == '__main__':
    unittest.main()

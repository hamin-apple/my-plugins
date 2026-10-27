"""scripts/check-run.py: the pass condition of a scenario run (architecture 4.13 scenarios)."""
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script
import ma_logline

SCRIPT = L4 / 'scripts' / 'check-run.py'


def L(kind, **f):
    return ma_logline.format_line(kind, f.items())


def steps(*ns):
    names = {1: 'Intake', 2: 'Explore-Scope', 3: 'Plan', 4: 'Plan-Review', 5: 'Execute', 6: 'Merge', 7: 'Verify',
             8: 'Review-Deliver'}
    return [L('step', n=n, name=names[n], rev=0, session='s', model='claude-opus-5-5') for n in ns]


class CheckRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.T = Path(self.tmp.name) / 'docs' / 'agent' / '261025-scn-general'
        self.T.mkdir(parents=True)
        (self.T / 'intake.md').write_text('Status: done\nProfile: general\nTask: 261025-scn-general\n')
        (self.T / 'plan.md').write_text('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        (self.T / 'plan-review.md').write_text('READY FOR APPROVAL\n')
        (self.T / 'verify.md').write_text('Verdict: ALL PASS\nRun: 1\n- 1. PASS x\n')
        (self.T / 'review.md').write_text('BLOCKER 0\n')
        self.lines = (steps(1, 2, 3)
                      + [L('call', agent='my-agent:architect'), L('start', agent='my-agent:architect', id='a1'),
                         L('stop', id='a1', result='DONE', end='ok')]
                      + steps(4) + [L('ask', gate='G1b', q='Plan approval'), L('answer', gate='G1b', choice='Approve')]
                      + steps(5, 6, 7, 8)
                      + [L('ask', gate='G2', agent='main', tool='Bash', q='rm -rf x'),
                         L('ask', gate='G3', q='Final acceptance'), L('answer', gate='G3', choice='Accept'),
                         L('deliver', path='/x/out.md')])

    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        (self.T / 'run-log.md').write_text('\n'.join(self.lines) + '\n', encoding='utf-8')
        return run_script(SCRIPT, str(self.T))

    def test_complete_run_passes(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('info popups: 2 (general normal path: 2)', r.stdout)
        self.assertNotIn('FAIL', r.stdout)

    def test_missing_answer_fails(self):
        self.lines = [ln for ln in self.lines if 'answer: gate=G3' not in ln]
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL gates', r.stdout)

    def test_open_agent_fails(self):
        self.lines = [ln for ln in self.lines if not ln.split(' ', 2)[2].startswith('stop:')]
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL agents', r.stdout)

    def test_execute_before_approval_fails(self):
        i = next(i for i, ln in enumerate(self.lines) if 'answer: gate=G1b' in ln)
        moved = self.lines.pop(i)
        self.lines.append(moved)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL approval-order', r.stdout)

    def test_missing_step_fails_unless_skipped(self):
        self.lines = [ln for ln in self.lines if 'name=Plan-Review' not in ln]
        self.assertIn('FAIL steps', self.check().stdout)
        (self.T / 'plan-review.md').write_text('SKIPPED small task\n')
        self.assertEqual(self.check().returncode, 0)

    def test_units_must_end_done(self):
        """D3/C4: every `### u<n>` unit ends `done` (or `stale` after a revision)."""
        units = '## Work units\n\n### u1 parser\n- Status: done\n\n### u2 cli\n- Status: running\n\n### u3 old\n- Status: stale\n\n'
        (self.T / 'plan.md').write_text(f'# Plan\n\n{units}## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        out = self.check().stdout
        self.assertIn('FAIL units: unit Status not done: u2 running', out)
        (self.T / 'plan.md').write_text((self.T / 'plan.md').read_text().replace('running', 'done'))
        self.assertEqual(self.check().returncode, 0)

    def test_unreadable_line_fails(self):
        """C9: a record line no reader can parse is named, not dropped silently."""
        self.lines.insert(3, '2026-10-25 10:00:00 ask: gate=Q q="open quote')
        self.assertIn('FAIL log-format: unreadable run-log line(s) 4', self.check().stdout)

    def test_revision_needs_done(self):
        """B4: a revision line without its `state=done` line is an unfinished invalidation."""
        rev = L('revision', rev=1, why='x', archive='archive/a-rev1/', invalidated='verify.md', keep='-', state='pending')
        draft = L('revision', rev=0, before='G1b', why='Request changes', archive='archive/b-rev0/')
        self.lines[6:6] = [draft, rev]
        self.assertIn('FAIL revisions: no state=done for rev 1', self.check().stdout)
        self.lines.insert(8, L('revision', rev=1, state='done'))
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_verdict_files(self):
        (self.T / 'verify.md').write_text('Verdict: FAIL\n')
        (self.T / 'review.md').write_text('BLOCKER 2\n')
        out = self.check().stdout
        self.assertIn('FAIL verify', out)
        self.assertIn('FAIL review', out)

    def test_not_done_and_not_approved(self):
        (self.T / 'intake.md').write_text('Status: active\nProfile: general\n')
        (self.T / 'plan.md').write_text('# Plan\n\n## Approval\n')
        out = self.check().stdout
        self.assertIn('FAIL status', out)
        self.assertIn('FAIL approved', out)

    def test_usage(self):
        self.assertEqual(run_script(SCRIPT).returncode, 2)
        self.assertEqual(run_script(SCRIPT, str(self.T / 'nope')).returncode, 2)


if __name__ == '__main__':
    unittest.main()

"""verdict-fresh-check.py: commit / deliver only on fresh ALL PASS + BLOCKER 0 (architecture 4.4 G3, P11)."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import make_task, run_hook

TASK = '261025-probe-task'


class VerdictFreshCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.L = self.root / 'proj'
        self.L.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.L)], check=True)
        self.T = make_task(self.L, task=TASK, git=False)
        (self.L / 'src').mkdir()
        self.t0 = time.time() - 1000
        self.env = {'MA_TASKS_DIR': str(self.root / 'agent-tasks')}

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, path, text, at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        os.utime(path, (self.t0 + at, self.t0 + at))

    def verdicts(self, verify_at=10, review_at=10, verify='Verdict: ALL PASS\nRun: 1\n', review='BLOCKER 0\n'):
        self.file(self.T / 'verify.md', verify, verify_at)
        self.file(self.T / 'review.md', review, review_at)

    def bash(self, command, cwd=None, **extra):
        payload = dict({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': command},
                        'session_id': 's-test'}, **extra)
        return run_hook('verdict-fresh-check.py', None, payload, cwd or self.L, env=self.env)

    def assertDenied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertIn('G3', out['permissionDecisionReason'])

    PREFIX = 'my-agent verdict gate: '
    TAIL = '; allow the commit only if it is your own change, not the task\'s'

    def assertAsked(self, r, reason=None):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'ask'))
        if reason is not None:
            self.assertEqual(out['permissionDecisionReason'], reason)
        return out['permissionDecisionReason']

    def assertPassed(self, r):
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_not_applicable_is_silent(self):
        self.assertPassed(self.bash('git status && git diff'))
        (self.L / 'docs' / 'agent' / '.active').unlink()
        self.assertPassed(self.bash('git commit -m x'))

    def test_other_session_and_subagent_pass(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertAsked(self.bash('git commit -m x'))
        self.assertPassed(self.bash('git commit -m x', session_id='s-other'))
        self.assertPassed(self.bash('git commit -m x', agent_id='ag1'))

    def test_commit_without_verdicts_denied(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertAsked(self.bash('git add -A && git commit -m "feat: x"'),
                         self.PREFIX + 'verify.md does not start with Verdict: ALL PASS' + self.TAIL)

    def test_commit_with_fresh_verdicts_passes(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.verdicts()
        self.assertPassed(self.bash('git commit -m "feat: x (criteria 1, 2)"'))

    def test_wrong_verdict_word_denied(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.verdicts(verify='Verdict: FAIL\n')
        self.assertAsked(self.bash('git commit -m x'), self.PREFIX + 'verify.md does not start with Verdict: ALL PASS' + self.TAIL)
        self.verdicts(review='BLOCKER 1\n')
        self.assertAsked(self.bash('git commit -m x'), self.PREFIX + 'review.md does not start with BLOCKER 0' + self.TAIL)

    def test_change_after_verify_denied(self):
        self.verdicts()
        self.file(self.L / 'src/a.py', 'x', 20)
        self.assertAsked(self.bash('git commit -m x'), self.PREFIX + 'review.md is older than src/a.py' + self.TAIL)

    def test_verify_older_names_verify(self):
        self.file(self.L / 'src/a.py', 'x', 20)
        self.verdicts(verify_at=10, review_at=30)
        self.assertAsked(self.bash('git commit -m x'), self.PREFIX + 'verify.md is older than src/a.py' + self.TAIL)

    def test_task_folder_changes_do_not_count_for_commit(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.verdicts()
        self.file(self.T / 'run-log.md', 'later', 30)
        self.assertPassed(self.bash('git commit -m x'))

    def test_applied_after_review_exception(self):
        self.file(self.L / 'src/a.py', 'x', 20)
        self.verdicts(verify_at=10, review_at=30, review='BLOCKER 0\n\n## Applied after review\n\n- a.py: rename\n')
        self.assertPassed(self.bash('git commit -m x'))
        self.verdicts(verify_at=10, review_at=30)
        self.assertAsked(self.bash('git commit -m x'))

    def test_deliver_copy_checked(self):
        self.file(self.T / 'work' / 'note.md', 'n', 0)
        self.assertDenied(self.bash(f'cp -p docs/agent/{TASK}/work/note.md ~/notes/'))
        self.verdicts()
        self.assertPassed(self.bash(f'cp -p docs/agent/{TASK}/work/note.md ~/notes/'))
        self.file(self.T / 'work' / 'note.md', 'edited', 20)
        self.assertDenied(self.bash(f'cp -p docs/agent/{TASK}/work/note.md ~/notes/'))

    def test_copy_inside_work_ignored(self):
        self.assertPassed(self.bash(f'cp docs/agent/{TASK}/work/a.md docs/agent/{TASK}/work/b.md'))
        self.assertPassed(self.bash('cp src/a.py src/b.py'))

    def tool(self, name, tool_input):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': name, 'tool_input': tool_input, 'session_id': 's-test'}
        return run_hook('verdict-fresh-check.py', None, payload, self.L, env=self.env)

    def test_deliver_into_deliverable_checked(self):
        self.file(self.T / 'work' / 'final.md', 'f', 0)
        self.verdicts(verify='Verdict: FAIL\n', review='BLOCKER 3\n')
        work, out = f'docs/agent/{TASK}/work/final.md', f'docs/agent/{TASK}/deliverable/final.md'
        self.assertDenied(self.bash(f'cp {work} {out}'))
        self.assertDenied(self.tool('Write', {'file_path': str(self.L / out), 'content': 'f'}))
        self.assertDenied(self.bash(f'cp DOCS/agent/{TASK}/work/final.md ~/notes/'))
        self.verdicts()
        self.assertPassed(self.tool('Write', {'file_path': str(self.L / out), 'content': 'f'}))
        self.assertPassed(self.tool('Write', {'file_path': str(self.L / 'src/a.py'), 'content': 'x'}))

    def test_read_only_forms_are_not_a_deliver(self):
        self.file(self.T / 'work' / 'x.md', 'x', 0)
        T = f'docs/agent/{TASK}'
        self.assertPassed(self.bash(f'cat {T}/work/x.md > {self.root}/out/y.md'))
        self.assertPassed(self.bash(f'cat {T}/work/x.md | tee {self.root}/out/y.md'))

    def test_copy_forms_are_a_deliver(self):
        self.file(self.T / 'work' / 'f', 'f', 0)
        T = f'docs/agent/{TASK}'
        self.assertDenied(self.bash(f'cp {T}/work/f ~/out'))
        self.assertDenied(self.bash(f'cd {T} && cp work/f ~/out'))
        self.assertDenied(self.bash(f'mv {T}/work/f {self.root}/out'))
        self.verdicts()
        self.assertPassed(self.bash(f'cd {T} && cp work/f ~/out'))

    def test_write_into_deliverable_is_a_deliver(self):
        self.assertDenied(self.bash(f'echo x > docs/agent/{TASK}/deliverable/a.md'))
        self.verdicts()
        self.assertPassed(self.bash(f'echo x > docs/agent/{TASK}/deliverable/a.md'))

    def test_copy_of_task_records_is_not_a_deliver(self):
        T, out = f'docs/agent/{TASK}', self.root / 'out'
        self.file(self.T / 'review.md', 'BLOCKER 3\n', 0)
        self.file(self.T / 'run-log.md', 'log', 0)
        self.file(self.T / 'verify.md', 'Verdict: FAIL\n', 0)
        self.file(self.T / 'work' / 'a.md', 'a', 20)
        self.assertPassed(self.bash(f'cp {T}/review.md {out}/backup.md'))
        self.assertPassed(self.bash(f'cp {T}/run-log.md {out}/'))
        self.assertPassed(self.bash(f'rsync {T}/verify.md {out}/'))

    def test_copy_from_work_still_denied_with_stale_verdicts(self):
        T, out = f'docs/agent/{TASK}', self.root / 'out'
        self.file(self.T / 'review.md', 'BLOCKER 3\n', 0)
        self.file(self.T / 'work' / 'a.md', 'a', 20)
        self.assertDenied(self.bash(f'cp {T}/work/a.md {out}/'))
        self.assertDenied(self.bash(f'cp {T}/work/a.md {T}/review.md {out}/'))
        self.assertDenied(self.bash(f'cd {T} && cp work/a.md {out}/'))

    def test_compound_commit_and_stale_deliver_is_denied(self):
        T, out = f'docs/agent/{TASK}', self.root / 'out'
        self.file(self.T / 'review.md', 'BLOCKER 3\n', 0)
        self.file(self.T / 'work' / 'a.md', 'a', 20)
        self.assertDenied(self.bash(f'git commit -m x && cp {T}/work/a.md {out}/'))
        why = self.assertAsked(self.bash(f'git commit -m x && cp {T}/review.md {out}/'))
        self.assertIn('verify.md does not start with', why)
        self.assertAsked(self.bash('git commit -m x'))

    def test_ask_reason_survives_case_different_location(self):
        self.verdicts(verify_at=10, review_at=10)
        self.file(self.L / 'src/a.py', 'x', 30)
        r = self.bash('git commit -m x')
        self.assertAsked(r)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'vfc', str(Path(__file__).resolve().parents[1] / 'l4-tools-guards/hooks/verdict-fresh-check.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        class A:
            location = Path('/Tmp/Proj')
        file = Path('/tmp/proj/src/a.py')
        mod.under = lambda p, q: True          # a case-folding volume: under() says yes, relative_to would raise
        why = mod.ask_reason(A, ('older', 'verify.md', file), False)
        self.assertIn('verify.md is older than', why)

    def test_git_mv_work_to_deliverable_checked(self):
        T = f'docs/agent/{TASK}'
        self.file(self.T / 'work' / 'a.md', 'a', 0)
        self.assertDenied(self.bash(f'git mv {T}/work/a.md {T}/deliverable/a.md'))
        self.verdicts()
        self.assertPassed(self.bash(f'git mv {T}/work/a.md {T}/deliverable/a.md'))

    def test_commit_still_produces_output(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertNotEqual(self.bash('git commit -m x').stdout, '')

    def test_second_deliver_copy_not_blocked_by_first(self):
        self.file(self.T / 'work' / 'a.md', 'a', 0)
        self.file(self.T / 'work' / 'b.md', 'b', 0)
        self.verdicts()
        self.file(self.T / 'deliverable' / 'a.md', 'a', 40)     # the first copy, made just now
        self.assertPassed(self.bash(f'cp docs/agent/{TASK}/work/b.md docs/agent/{TASK}/deliverable/b.md'))

    def test_substitution_without_git_is_not_a_commit(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertPassed(self.bash('echo "$(date +%F)"'))
        self.assertAsked(self.bash('git commit -m "$(cat <<\'EOF\'\nfeat: x\nEOF\n)"'),
                         'my-agent verdict gate: cannot parse the command; allow it only if it is your own commit, not the task\'s')
        self.verdicts()
        self.assertPassed(self.bash('git commit -m "$(cat <<\'EOF\'\nfeat: x\nEOF\n)"'))

    def test_unparsed_git_says_why(self):
        # live run: L1 logged HEAD with "$(git rev-parse HEAD)" during Execute and got the verify.md message
        self.file(self.L / 'src/a.py', 'x', 0)
        # no `git ... commit` shape in it: not a possible commit any more (2026-10-30, criterion 3)
        self.assertPassed(self.bash('echo "HEAD=$(git rev-parse HEAD)" && git status --porcelain'))
        r = self.bash('echo "HEAD=$(git rev-parse HEAD)" && git commit -m "$(cat <<\'EOF\'\nfeat: x\nEOF\n)"')
        why = self.assertAsked(r)
        self.assertIn('cannot parse the command', why)
        self.assertNotIn('verify.md', why)

    def test_commit_inside_shell_keywords_checked(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertAsked(self.bash('if true; then git commit -m m; fi'))

    def test_non_git_location(self):
        loc = self.root / 'agent-tasks'
        T = make_task(loc, task=TASK, git=False)
        self.T = T
        self.file(T / 'deliverable' / 'out.md', 'o', 20)
        self.verdicts()
        self.assertDenied(self.bash(f'cp {T}/deliverable/out.md {self.root}/out.md', cwd=loc))
        self.verdicts(verify_at=30, review_at=30)
        self.assertPassed(self.bash(f'cp {T}/deliverable/out.md {self.root}/out.md', cwd=loc))

    def test_script_error_exits_nonzero(self):
        r = run_hook('verdict-fresh-check.py', None, 'not json', self.L, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()

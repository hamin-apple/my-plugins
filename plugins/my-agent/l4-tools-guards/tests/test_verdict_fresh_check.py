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

    def bash(self, command, cwd=None):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': command}}
        return run_hook('verdict-fresh-check.py', None, payload, cwd or self.L, env=self.env)

    def assertDenied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertIn('G3', out['permissionDecisionReason'])

    def assertPassed(self, r):
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_not_applicable_is_silent(self):
        self.assertPassed(self.bash('git status && git diff'))
        (self.L / 'docs' / 'agent' / '.active').unlink()
        self.assertPassed(self.bash('git commit -m x'))

    def test_commit_without_verdicts_denied(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertDenied(self.bash('git add -A && git commit -m "feat: x"'))

    def test_commit_with_fresh_verdicts_passes(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.verdicts()
        self.assertPassed(self.bash('git commit -m "feat: x (criteria 1, 2)"'))

    def test_wrong_verdict_word_denied(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.verdicts(verify='Verdict: FAIL\n')
        self.assertDenied(self.bash('git commit -m x'))
        self.verdicts(review='BLOCKER 1\n')
        self.assertDenied(self.bash('git commit -m x'))

    def test_change_after_verify_denied(self):
        self.verdicts()
        self.file(self.L / 'src/a.py', 'x', 20)
        self.assertDenied(self.bash('git commit -m x'))

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
        self.assertDenied(self.bash('git commit -m x'))

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
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': name, 'tool_input': tool_input}
        return run_hook('verdict-fresh-check.py', None, payload, self.L, env=self.env)

    def test_deliver_into_deliverable_checked(self):
        self.file(self.T / 'work' / 'final.md', 'f', 0)
        self.verdicts(verify='Verdict: FAIL\n', review='BLOCKER 3\n')
        work, out = f'docs/agent/{TASK}/work/final.md', f'docs/agent/{TASK}/deliverable/final.md'
        self.assertDenied(self.bash(f'cp {work} {out}'))
        self.assertDenied(self.bash(f'cat {work} > notes/final.md'))
        self.assertDenied(self.tool('Write', {'file_path': str(self.L / out), 'content': 'f'}))
        self.assertDenied(self.bash(f'cp DOCS/agent/{TASK}/work/final.md ~/notes/'))
        self.verdicts()
        self.assertPassed(self.tool('Write', {'file_path': str(self.L / out), 'content': 'f'}))
        self.assertPassed(self.tool('Write', {'file_path': str(self.L / 'src/a.py'), 'content': 'x'}))

    def test_second_deliver_copy_not_blocked_by_first(self):
        self.file(self.T / 'work' / 'a.md', 'a', 0)
        self.file(self.T / 'work' / 'b.md', 'b', 0)
        self.verdicts()
        self.file(self.T / 'deliverable' / 'a.md', 'a', 40)     # the first copy, made just now
        self.assertPassed(self.bash(f'cp docs/agent/{TASK}/work/b.md docs/agent/{TASK}/deliverable/b.md'))

    def test_substitution_without_git_is_not_a_commit(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertPassed(self.bash('echo "$(date +%F)"'))
        self.assertDenied(self.bash('git commit -m "$(cat <<\'EOF\'\nfeat: x\nEOF\n)"'))

    def test_unparsed_git_says_why(self):
        # live run: L1 logged HEAD with "$(git rev-parse HEAD)" during Execute and got the verify.md message
        self.file(self.L / 'src/a.py', 'x', 0)
        r = self.bash('echo "HEAD=$(git rev-parse HEAD)" && git status --porcelain')
        self.assertDenied(r)
        why = json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('git commit인지 판단할 수 없', why)
        self.assertNotIn('verify.md', why)

    def test_commit_inside_shell_keywords_checked(self):
        self.file(self.L / 'src/a.py', 'x', 0)
        self.assertDenied(self.bash('if true; then git commit -m m; fi'))

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

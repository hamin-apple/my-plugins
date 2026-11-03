"""Hook-health check on Codex: every my-agent hook leaves a mark; data-dir.py checks them (criterion 5)."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from helpers import L4, REPO, make_task, run_hook, run_script

FIX = REPO / 'tests' / 'fixtures' / 'codex'
SESSION = '019a0000-0000-7000-8000-000000000001'
GATES = ('plan-approved-check', 'verdict-fresh-check')


class HookHealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.tmpdir = self.root / 'tmp'
        self.tmpdir.mkdir()
        self.marks = self.tmpdir / 'my-agent-codex' / 'marks' / SESSION
        self.env = {'MA_HOST': 'codex', 'CODEX_THREAD_ID': SESSION, 'TMPDIR': str(self.tmpdir),
                    'CLAUDE_PLUGIN_OPTION_DATA_DIR': str(self.root / 'data')}

    def tearDown(self):
        self.tmp.cleanup()

    def mark(self, *hooks, age=0):
        self.marks.mkdir(parents=True, exist_ok=True)
        for h in hooks:
            p = self.marks / h
            p.write_text('x')
            t = time.time() - age
            os.utime(p, (t, t))

    def check(self, env=None, drop=('MA_TASKS_DIR', 'CLAUDE_CODE_SESSION_ID', 'CLAUDECODE')):
        return run_script(L4 / 'scripts' / 'data-dir.py', env=dict(self.env, **(env or {})), cwd=self.root,
                          drop=drop)

    def test_trusted(self):
        self.mark(*GATES, 'session-notice')
        r = self.check()
        self.assertEqual((r.returncode, r.stdout.strip()), (0, str(self.root / 'data')))

    def test_missing(self):
        r = self.check()
        self.assertEqual(r.returncode, 1)
        for h in GATES + ('session-notice',):
            self.assertIn(h, r.stderr)
        self.assertIn('trust', r.stderr)
        self.assertEqual(r.stdout, '')

    def test_one_hook_missing(self):
        self.mark('verdict-fresh-check', 'session-notice')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('plan-approved-check', r.stderr)
        self.assertNotIn('verdict-fresh-check', r.stderr)

    def test_stale(self):
        self.mark(*GATES, age=3600)
        self.mark('session-notice', age=3600)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('plan-approved-check', r.stderr)
        self.assertNotIn('session-notice', r.stderr)   # the notice runs once per session start, no age limit

    def test_other_session_marks_do_not_count(self):
        other = self.tmpdir / 'my-agent-codex' / 'marks' / 'other-session'
        other.mkdir(parents=True)
        for h in GATES + ('session-notice',):
            (other / h).write_text('x')
        self.assertEqual(self.check().returncode, 1)

    def test_guard_hooks_mark_on_codex_input(self):
        make_task(self.root / 'proj', session=SESSION)
        inp = json.loads((FIX / 'hook-pre-tool-use-bash.json').read_text())
        for script in ('plan-approved-check.py', 'verdict-fresh-check.py'):
            run_hook(script, None, inp, self.root / 'proj', env=self.env)
        self.assertEqual(sorted(p.name for p in self.marks.iterdir()), sorted(GATES))

    def test_claude_untouched(self):
        env = {'MA_HOST': 'claude', 'CLAUDE_CODE_SESSION_ID': 's-1'}
        r = self.check(env=env, drop=('MA_TASKS_DIR',))
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr), (0, str(self.root / 'data'), ''))
        run_hook('plan-approved-check.py', None, json.loads((FIX / 'hook-pre-tool-use-bash.json').read_text()),
                 self.root, env=dict(self.env, **env))
        self.assertFalse((self.tmpdir / 'my-agent-codex').exists())


if __name__ == '__main__':
    unittest.main()

"""session-notice.py: SessionStart reminder of an unfinished task (architecture 4.8.2 "new-session notice")."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_task, run_hook

NOTICE = ('Unfinished my-agent task `261025-probe-task`, phase `2`. Run `/my-agent continue` before doing anything else. '
          'If `plan.md` has no approval line, do not delegate or write.')
FORK = 'The original session is running this task. To take it over in this session, run `/my-agent continue`'


class SessionNoticeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = {'MA_TASKS_DIR': str(self.root / 'none')}

    def tearDown(self):
        self.tmp.cleanup()

    def notice(self, source, session='s-test', cwd=None):
        r = run_hook('session-notice.py', None, {'hook_event_name': 'SessionStart', 'source': source,
                                                 'session_id': session}, cwd or self.root, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def context(self, out):
        data = json.loads(out)
        self.assertEqual(data['hookSpecificOutput']['hookEventName'], 'SessionStart')
        return data['hookSpecificOutput']['additionalContext']

    def test_notice_text(self):
        make_task(self.root, phase='2')
        for source in ('startup', 'resume', 'clear', 'compact'):
            with self.subTest(source=source):
                self.assertEqual(self.context(self.notice(source)), NOTICE)

    def test_notice_fork_other_session(self):
        make_task(self.root, phase='2', session='s-original')
        self.assertEqual(self.context(self.notice('fork', session='s-fork')), FORK)
        self.assertEqual(self.context(self.notice('fork', session='s-original')), NOTICE)

    def test_no_active_notice(self):
        self.assertEqual(self.notice('startup'), '')

    def test_bad_stdin(self):
        r = run_hook('session-notice.py', None, 'nope', self.root, env=self.env)
        self.assertEqual((r.returncode, r.stdout), (0, ''))


if __name__ == '__main__':
    unittest.main()

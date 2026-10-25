"""session-notice.py: SessionStart reminder of an unfinished task (architecture 4.8.2 "새 세션 알림")."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_task, run_hook

NOTICE = ('미완료 my-agent 작업 `261025-probe-task`, phase `2`. 다른 일을 하기 전에 `/my-agent continue`를 실행할 것. '
          '`plan.md`에 승인 줄이 없으면 위임과 쓰기를 하지 말 것.')
FORK = '원래 세션이 이 작업을 진행 중. 이 세션에서 이어받으려면 `/my-agent continue`'


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

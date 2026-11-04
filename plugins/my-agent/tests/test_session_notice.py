"""session-notice.py: SessionStart reminder of an unfinished task (architecture 4.8.2 "new-session notice")."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_task, run_hook

NOTICE = ('Unfinished my-agent task `261025-probe-task`, phase `2`. Run `/my-agent continue` before doing anything else. '
          'If `plan.md` has no approval line, do not delegate or write.')
OTHER = ('The original session is running my-agent task 261025-probe-task (phase 2). '
         'To take it over in this session, run /my-agent continue; otherwise work as usual.')


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

    def test_other_session_every_source(self):
        make_task(self.root, phase='2', session='s-original')
        for source in ('startup', 'resume', 'clear', 'compact', 'fork'):
            with self.subTest(source=source):
                ctx = self.context(self.notice(source, session='s-other'))
                self.assertEqual(ctx, OTHER)
                self.assertNotIn('before doing anything else', ctx)

    def test_owner_gets_notice(self):
        make_task(self.root, phase='2', session='s-original')
        for source in ('startup', 'fork'):
            with self.subTest(source=source):
                self.assertEqual(self.context(self.notice(source, session='s-original')), NOTICE)

    def test_no_marker_session_gets_notice(self):
        make_task(self.root, phase='2', session='')
        self.assertEqual(self.context(self.notice('startup', session='s-other')), NOTICE)

    def test_no_input_session_gets_notice(self):
        make_task(self.root, phase='2', session='s-original')
        for source in ('startup', 'fork'):
            with self.subTest(source=source):
                r = run_hook('session-notice.py', None, {'hook_event_name': 'SessionStart', 'source': source},
                             self.root, env=self.env)
                self.assertEqual(self.context(r.stdout), NOTICE)

    def test_no_active_notice(self):
        self.assertEqual(self.notice('startup'), '')

    def test_bad_stdin(self):
        r = run_hook('session-notice.py', None, 'nope', self.root, env=self.env)
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    # Codex: one plain-text line, folder part first
    def codex(self, payload=None, env=None, cwd=None, stdin=None):
        e = dict(self.env, MA_HOST='codex', CLAUDE_PLUGIN_ROOT=str(self.root / 'plug'))
        e.update(env or {})
        payload = payload if payload is not None else {'hook_event_name': 'SessionStart', 'source': 'startup',
                                                       'session_id': 's-test', 'turn_id': None}
        r = run_hook('session-notice.py', None, stdin if stdin is not None else payload, cwd or self.root, env=e,
                     drop=tuple(k for k in ('MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_DATA_DIR')
                                if k not in e))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def folders(self, task='.my-agent'):
        return (f'my-agent on Codex: plugin folder {self.root / "plug"} (read ${{CLAUDE_PLUGIN_ROOT}} in the skill '
                f'text as this folder), data folder {self.root / "none"} (${{user_config.data_dir}}), '
                f'task folder {task} (${{user_config.task_dir}}).')

    def test_codex_line_without_task(self):
        out = self.codex()
        self.assertEqual(out, self.folders() + '\n')

    def test_codex_line_is_plain_one_line(self):
        make_task(self.root, phase='2')
        out = self.codex()
        self.assertEqual(out.count('\n'), 1)
        self.assertTrue(out.endswith('\n'))
        with self.assertRaises(ValueError):
            json.loads(out)

    def test_codex_owner_and_other_session(self):
        make_task(self.root, phase='2', session='s-original')
        owner = self.codex({'hook_event_name': 'SessionStart', 'session_id': 's-original'})
        self.assertEqual(owner, self.folders() + ' ' + NOTICE + '\n')
        other = self.codex({'hook_event_name': 'SessionStart', 'session_id': 's-other'})
        self.assertEqual(other, self.folders() + ' ' + OTHER + '\n')

    def test_codex_task_dir_option(self):
        out = self.codex(env={'MA_TASK_DIR': 'records/x'})
        self.assertEqual(out, self.folders('records/x') + '\n')

    def test_codex_unexpanded_option_counts_as_empty(self):
        e = {'MA_TASKS_DIR': '', 'CLAUDE_PLUGIN_OPTION_DATA_DIR': '${user_config.data_dir}'}
        out = self.codex(env=e)
        self.assertIn('data folder ' + str(Path.home() / 'dev' / 'log' / 'my-agent') + ' (', out)

    def test_codex_failure_prints_nothing(self):
        for stdin in ('nope', '[1]'):
            with self.subTest(stdin=stdin):
                self.assertEqual(self.codex(stdin=stdin), '')

    def test_claude_without_ma_host(self):
        e = {'CLAUDE_PLUGIN_ROOT': str(self.root / 'plug'), 'CLAUDE_CODE_SESSION_ID': 's-test'}
        r = run_hook('session-notice.py', None, {'hook_event_name': 'SessionStart', 'source': 'startup'},
                     self.root, env=dict(self.env, **e), drop=('MA_HOST',))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_claude_forced_with_task_keeps_json(self):
        make_task(self.root, phase='2')
        e = dict(self.env, MA_HOST='claude')
        r = run_hook('session-notice.py', None, {'hook_event_name': 'SessionStart', 'source': 'startup',
                                                 'session_id': 's-test'}, self.root, env=e)
        self.assertEqual(self.context(r.stdout), NOTICE)


if __name__ == '__main__':
    unittest.main()

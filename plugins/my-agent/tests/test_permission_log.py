"""permission-log.py ask/answer: G2 records (architecture 4.7.2 "G2 records")."""
import tempfile
import unittest
from pathlib import Path

from helpers import events, log_lines, make_task, parse, run_hook

CMD = 'echo "a\\b" > x'


class PermissionLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root)
        self.env = {'MA_TASKS_DIR': str(self.root / 'none')}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, mode, payload, cwd=None):
        r = run_hook('permission-log.py', mode, payload, cwd or self.root, env=self.env)
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def ask(self, command=CMD, **kw):
        self.hook('ask', dict({'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                               'tool_input': {'command': command}}, **kw))

    def answer(self, command=CMD):
        self.hook('answer', {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
                             'tool_input': {'command': command}, 'tool_response': {}})

    def write_log(self, text):
        (self.task / 'run-log.md').write_text(text)

    def test_ask_bash_with_quotes(self):
        self.ask()
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['gate'], f['tool'], f['q'], f['agent'], f['id']), ('G2', 'Bash', CMD, 'main', '-'))
        self.assertEqual(events(self.task).waiting, {'gate': 'G2', 'q': CMD})

    def test_ask_uses_input_agent(self):
        self.ask(agent_type='my-agent:coder', agent_id='a7')
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['agent'], f['id']), ('my-agent:coder', 'a7'))

    def test_ask_guesses_running_agent(self):
        self.write_log('2026-10-25 09:00:01 start: agent=my-agent:coder id=c1 configured=sonnet effort=medium\n')
        self.ask()
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['agent'], f['id']), ('my-agent:coder', 'c1'))
        self.write_log('2026-10-25 09:00:01 start: agent=my-agent:coder id=c1 configured=sonnet effort=medium\n'
                       '2026-10-25 09:00:02 start: agent=my-agent:writer id=w1 configured=sonnet effort=medium\n')
        self.ask()
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['agent'], f['id']), ('main', '-'))

    def test_ask_summary_for_other_tools(self):
        self.hook('ask', {'tool_name': 'Write', 'tool_input': {'file_path': '/tmp/x.md', 'content': 'long'}})
        self.assertEqual(parse(log_lines(self.task)[-1])['q'], '/tmp/x.md')
        self.hook('ask', {'tool_name': 'mcp__slack__send', 'tool_input': {'text': 'hi ' * 200}})
        q = parse(log_lines(self.task)[-1])['q']
        self.assertTrue(q.startswith('{"text":') and len(q) <= 200, q)

    def test_answer_matches_only_same_call(self):
        self.ask()
        self.answer('ls')
        self.assertEqual(len(log_lines(self.task)), 1)
        self.answer()
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['gate'], f['id'], f['result']), ('G2', '-', 'allowed'))
        self.assertEqual(events(self.task).answered['G2'], 'allowed')

    def test_answer_once(self):
        self.ask()
        self.answer()
        self.answer()
        self.assertEqual(len(log_lines(self.task)), 2)

    def test_no_active_ask_and_answer(self):
        empty = self.root / 'empty'
        empty.mkdir()
        (empty / '.git').mkdir()
        self.hook('ask', {'tool_name': 'Bash', 'tool_input': {'command': 'x'}}, cwd=empty)
        self.hook('answer', {'tool_name': 'Bash', 'tool_input': {'command': 'x'}}, cwd=empty)
        self.assertEqual(sorted(p.name for p in empty.iterdir()), ['.git'])

    def test_question_popup_is_not_a_g2_ask(self):
        """Live run: AskUserQuestion raises a PermissionRequest; L1 already logs that popup as its own gate."""
        before = log_lines(self.task)
        self.hook('ask', {'hook_event_name': 'PermissionRequest', 'tool_name': 'AskUserQuestion',
                          'tool_input': {'questions': [{'question': 'q?'}]}})
        self.assertEqual(log_lines(self.task), before)

    def test_other_session_writes_nothing(self):
        """Criterion 9: PermissionRequest input carries session_id (hooks reference); another session is not this task's."""
        self.ask(session_id='s-other')
        self.hook('answer', {'hook_event_name': 'PostToolUse', 'session_id': 's-other', 'tool_name': 'Bash',
                             'tool_input': {'command': CMD}, 'tool_response': {}})
        self.assertEqual(log_lines(self.task), [])

    def test_same_session_records_session(self):
        self.ask(session_id='s-test')
        self.assertEqual(parse(log_lines(self.task)[-1])['session'], 's-test')
        self.hook('answer', {'hook_event_name': 'PostToolUse', 'session_id': 's-test', 'tool_name': 'Bash',
                             'tool_input': {'command': CMD}, 'tool_response': {}})
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['result'], f['session']), ('allowed', 's-test'))

    def test_missing_session_records_as_before(self):
        self.ask()
        self.assertNotIn('session', parse(log_lines(self.task)[-1]))

    def test_bad_stdin(self):
        r = run_hook('permission-log.py', 'ask', '{oops', self.root, env=self.env)
        self.assertEqual((r.returncode, r.stdout), (0, ''))


if __name__ == '__main__':
    unittest.main()

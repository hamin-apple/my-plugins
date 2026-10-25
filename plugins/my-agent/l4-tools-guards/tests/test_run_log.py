"""run-log.py: the L1 Recorder's CLI (architecture 4.7.2 "누가 무엇을 기록하나", P9)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import L4, events, log_lines, make_task, parse, run_script

SCRIPT = L4 / 'scripts' / 'run-log.py'


class RunLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root, session='s-active')
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'CLAUDE_CODE_SESSION_ID': 's-9',
                    'MA_CLAUDE_PROJECTS': str(self.root / 'projects')}

    def tearDown(self):
        self.tmp.cleanup()

    def run_log(self, *args, env=None):
        return run_script(SCRIPT, *args, '--cwd', str(self.root), env=dict(self.env, **(env or {})))

    def test_step_fills_rev_and_session(self):
        (self.task / 'run-log.md').write_text('2026-10-25 09:00:00 revision: rev=1 why=x\n')
        r = self.run_log('step', 'n=3', 'name=Plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['n'], f['name'], f['rev'], f['session']), ('3', 'Plan', '1', 's-9'))
        self.assertEqual(events(self.task).step_enter[-1][1], 3)
        self.assertIn(log_lines(self.task)[-1], r.stdout)

    def test_step_session_from_active_without_env(self):
        r = self.run_log('step', 'n=1', 'name=Intake', env={'CLAUDE_CODE_SESSION_ID': ''})
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['rev'], f['session']), ('0', 's-active'))

    def test_step_needs_n_and_name(self):
        r = self.run_log('step', 'n=3')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(log_lines(self.task), [])

    def test_ask_answer_pair(self):
        self.assertEqual(self.run_log('ask', 'gate=G1b', 'q=계획을 승인할까요?').returncode, 0)
        ev = events(self.task)
        self.assertEqual(ev.gates.get('G1b'), 'wait')
        self.assertEqual(self.run_log('answer', 'gate=G1b', 'choice=승인').returncode, 0)
        ev = events(self.task)
        self.assertEqual(ev.answered['G1b'], '승인')
        self.assertNotEqual(ev.gates.get('G1b'), 'wait')

    def test_value_with_quotes(self):
        self.run_log('fix', 'what=say "hi" \\ there')
        self.assertEqual(parse(log_lines(self.task)[-1])['what'], 'say "hi" \\ there')

    def test_unknown_kind(self):
        r = self.run_log('bogus', 'a=1')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(log_lines(self.task), [])

    def test_bad_field(self):
        r = self.run_log('fix', 'noequals')
        self.assertEqual(r.returncode, 2)

    def test_main_mismatch(self):
        r = self.run_log('step', 'n=1', 'name=Intake', '--model', 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')
        r = self.run_log('step', 'n=2', 'name=Explore', '--model', 'claude-opus-5-5')
        self.assertNotIn('MISMATCH', r.stdout)

    def test_main_model_read_from_transcript(self):
        # live run: the skill's `model: opus` held for the first turn only (F13); later turns ran on Sonnet,
        # yet L1 kept passing --model claude-opus-5-5, so the check never fired
        t = self.root / 'projects' / '-x-proj' / 's-9.jsonl'
        t.parent.mkdir(parents=True)
        rows = [{'type': 'assistant', 'isSidechain': False, 'message': {'model': 'claude-opus-5-5'}},
                {'type': 'user', 'message': {'content': 'x'}},
                {'type': 'assistant', 'isSidechain': False, 'message': {'model': 'claude-sonnet-5-5'}},
                {'type': 'assistant', 'isSidechain': True, 'message': {'model': 'claude-opus-5-5'}},
                {'type': 'assistant', 'isSidechain': False, 'message': {'model': '<synthetic>'}}]
        t.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        r = self.run_log('step', 'n=3', 'name=Plan', '--model', 'claude-opus-5-5')
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        r = self.run_log('ask', 'gate=G3', 'q=x')     # only step lines (or an explicit --model) carry the model
        self.assertNotIn('model', parse(log_lines(self.task)[-1]))
        self.assertNotIn('MISMATCH', r.stdout)

    def test_main_mismatch_reported_once_per_model(self):
        r = self.run_log('step', 'n=2', 'name=Explore-Scope', '--model', 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        r = self.run_log('step', 'n=3', 'name=Plan', '--model', 'claude-sonnet-5-5')
        self.assertNotIn('MISMATCH', r.stdout)
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')   # still recorded
        r = self.run_log('step', 'n=4', 'name=Plan-Review', '--model', 'claude-haiku-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-haiku-5-5', r.stdout)

    def test_reports_subagent_mismatch_once(self):
        (self.task / 'run-log.md').write_text(
            '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=s\n'
            '2026-10-25 09:00:01 start: agent=my-agent:coder id=a1 configured=sonnet effort=medium\n'
            '2026-10-25 09:00:09 stop: id=a1 actual=claude-opus-5-5 tokens=10 in=1 out=1 cw=1 cr=7 secs=8 '
            'result=DONE end=ok mismatch=1\n')
        r = self.run_log('step', 'n=6', 'name=Merge')
        self.assertIn('MISMATCH: my-agent:coder configured sonnet, actual claude-opus-5-5', r.stdout)
        r = self.run_log('step', 'n=7', 'name=Verify')
        self.assertNotIn('MISMATCH', r.stdout)

    def test_no_active(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_script(SCRIPT, 'step', 'n=1', 'name=Intake', '--cwd', d, env=self.env)
            self.assertEqual(r.returncode, 1)
            self.assertIn('run-log: no active my-agent task under', r.stdout)
            self.assertEqual(list(Path(d).iterdir()), [])


if __name__ == '__main__':
    unittest.main()

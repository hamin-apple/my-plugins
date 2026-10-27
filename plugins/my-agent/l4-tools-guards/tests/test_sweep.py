"""Sweep: an agent that ends at maxTurns gets no SubagentStop (probe r4/r7); the next L1 record or
subagent hook closes it from its meta file with end=partial (architecture 4.7.2, E "slice stopped twice")."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import L4, events, log_lines, make_task, parse, run_hook, run_script

RUN_LOG = L4 / 'scripts' / 'run-log.py'


def transcript(rows):
    return ''.join(json.dumps(r) + '\n' for r in rows)


def assistant(mid, stop_reason, content, ts):
    return {'type': 'assistant', 'timestamp': ts, 'effort': 'low',
            'message': {'id': mid, 'model': 'claude-haiku-5-5', 'stop_reason': stop_reason, 'content': content,
                        'usage': {'input_tokens': 2, 'output_tokens': 10, 'cache_creation_input_tokens': 100,
                                  'cache_read_input_tokens': 0}}}


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root / 'proj')
        self.claude = self.root / 'claude'
        self.sub = self.claude / '-proj' / 's-main' / 'subagents'
        self.sub.mkdir(parents=True)
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'MA_CLAUDE_PROJECTS': str(self.claude),
                    'CLAUDE_CODE_SESSION_ID': 's-main'}
        (self.task / 'run-log.md').write_text(
            '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=s-main\n'
            '2026-10-25 09:00:01 start: agent=my-agent:coder id=c7 configured=haiku effort=low session=s-main\n')

    def tearDown(self):
        self.tmp.cleanup()

    def agent_files(self, finished, last):
        (self.sub / 'agent-c7.meta.json').write_text(json.dumps({'agentType': 'my-agent:coder', 'finished': finished}))
        (self.sub / 'agent-c7.jsonl').write_text(transcript([
            {'type': 'user', 'timestamp': '2026-10-25T00:00:01Z', 'message': {'content': 'go'}}, last,
            {'type': 'attachment', 'timestamp': '2026-10-25T00:00:30Z'}]))

    def run_log(self):
        return run_script(RUN_LOG, 'step', 'n=6', 'name=Merge', '--cwd', str(self.root / 'proj'), env=self.env)

    def test_max_turns_closed_as_partial(self):
        self.agent_files(True, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        r = self.run_log()
        stops = [parse(l) for l in log_lines(self.task) if ' stop: ' in l]
        self.assertEqual(len(stops), 1)
        self.assertEqual((stops[0]['id'], stops[0]['end'], stops[0]['actual'], stops[0]['tokens']),
                         ('c7', 'partial', 'claude-haiku-5-5', '112'))
        self.assertIn('PARTIAL: my-agent:coder c7 stopped before its final reply (maxTurns?)', r.stdout)
        self.assertEqual(events(self.task).sstop, 1)
        self.assertNotIn('PARTIAL', self.run_log().stdout)   # reported once

    def test_start_without_session_searched_in_every_session(self):
        """start: lines written before session= existed; .active names another session."""
        (self.task / 'run-log.md').write_text(
            '2026-10-25 09:00:01 start: agent=my-agent:coder id=c7 configured=haiku effort=low mode=-\n')
        make_task(self.root / 'proj', session='s-other')
        self.agent_files(True, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        self.run_log()
        self.assertTrue(any(' stop: id=c7 ' in l and 'end=partial' in l for l in log_lines(self.task)))

    def test_finished_with_end_turn_left_for_subagent_stop(self):
        self.agent_files(True, assistant('m1', 'end_turn', [{'type': 'text', 'text': 'DONE'}], '2026-10-25T00:00:20Z'))
        self.run_log()
        self.assertFalse(any(' stop: ' in l for l in log_lines(self.task)))

    def test_running_agent_untouched(self):
        self.agent_files(False, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        self.run_log()
        self.assertFalse(any(' stop: ' in l for l in log_lines(self.task)))

    def test_already_stopped_untouched(self):
        with open(self.task / 'run-log.md', 'a') as f:
            f.write('2026-10-25 09:00:09 stop: id=c7 actual=claude-haiku-5-5 tokens=1 secs=1 result=DONE end=ok\n')
        self.agent_files(True, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        self.run_log()
        self.assertEqual(sum(' stop: ' in l for l in log_lines(self.task)), 1)

    def test_resumed_run_left_for_subagent_stop(self):
        """SendMessage resumes the agent under the same id; its meta file still says finished from run 1, so a
        sweep during run 2 would close a working agent as partial (and count toward E)."""
        with open(self.task / 'run-log.md', 'a') as f:
            f.write('2026-10-25 09:00:09 stop: id=c7 actual=claude-haiku-5-5 tokens=1 secs=1 result=DONE end=ok\n'
                    '2026-10-25 09:01:00 start: agent=my-agent:coder id=c7 configured=haiku effort=low session=s-main\n')
        self.agent_files(True, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        self.assertNotIn('PARTIAL', self.run_log().stdout)
        self.assertEqual(sum(' stop: ' in l for l in log_lines(self.task)), 1)

    def test_subagent_start_also_sweeps(self):
        self.agent_files(True, assistant('m1', 'tool_use', [{'type': 'tool_use', 'name': 'Bash'}], '2026-10-25T00:00:20Z'))
        r = run_hook('subagent-log.py', 'start', {'agent_type': 'my-agent:writer', 'agent_id': 'w1',
                                                 'session_id': 's-main'}, self.root / 'proj',
                     env=dict(self.env, CLAUDE_PLUGIN_ROOT=str(self.root / 'noplugin')))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        self.assertTrue(any(' stop: id=c7 ' in l and 'end=partial' in l for l in log_lines(self.task)))


if __name__ == '__main__':
    unittest.main()

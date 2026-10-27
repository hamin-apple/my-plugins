"""subagent-log.py call/start/stop (architecture 4.7.2 "hook 설계")."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path

from helpers import L4, events, log_lines, make_task, parse, run_hook

FIXTURE = L4 / 'tests' / 'fixtures' / 'agent-transcript.jsonl'
CALL = {'hook_event_name': 'PreToolUse', 'tool_name': 'Agent',
        'tool_input': {'subagent_type': 'my-agent:probe-worker', 'model': 'opus', 'isolation': 'worktree',
                       'run_in_background': True, 'prompt': 'x', 'description': 'd'}}


class SubagentLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root / 'proj')
        self.cwd = self.root / 'proj'
        self.plugin = self.root / 'plugin'
        (self.plugin / '.claude-plugin').mkdir(parents=True)
        (self.plugin / 'agents').mkdir()
        (self.plugin / '.claude-plugin' / 'plugin.json').write_text(
            json.dumps({'name': 'my-agent', 'agents': ['./agents/probe-worker.md']}))
        (self.plugin / 'agents' / 'probe-worker.md').write_text(
            '---\nname: probe-worker\nmodel: haiku\neffort: low\ntools: Bash, Read\n---\nbody\n')
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'CLAUDE_PLUGIN_ROOT': str(self.plugin),
                    'CLAUDE_CODE_EFFORT_LEVEL': ''}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, mode, payload, cwd=None, env=None):
        r = run_hook('subagent-log.py', mode, payload, cwd or self.cwd, env=dict(self.env, **(env or {})))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '')
        return r

    def start(self, agent_id='ag1', agent='my-agent:probe-worker', env=None, **kw):
        self.hook('start', dict({'hook_event_name': 'SubagentStart', 'agent_type': agent, 'agent_id': agent_id,
                                 'permission_mode': 'auto'}, **kw), env=env)

    def stop(self, agent_id='ag1', transcript=FIXTURE, message='DONE\nmore', **kw):
        self.hook('stop', dict({'hook_event_name': 'SubagentStop', 'agent_type': 'my-agent:probe-worker',
                                'agent_id': agent_id, 'agent_transcript_path': str(transcript),
                                'last_assistant_message': message}, **kw))

    def last(self):
        return parse(log_lines(self.task)[-1])

    def test_call_written_for_my_agent(self):
        self.hook('call', CALL)
        line = log_lines(self.task)[-1]
        self.assertTrue(line.endswith(' call: agent=my-agent:probe-worker model=opus effort=- isolation=worktree background=true'), line)

    def test_unit_on_call_and_stop(self):
        """D3: the `작업 단위: u<n>` line L1 puts in a worker's prompt lands on call: and stop: as unit=."""
        prompt = '작업 단위: u2 CLI 옵션\nplan.md: docs/agent/x/plan.md'
        self.hook('call', dict(CALL, tool_input=dict(CALL['tool_input'], prompt=prompt)))
        self.assertEqual(self.last()['unit'], 'u2')
        self.start()
        tr = self.root / 'unit.jsonl'
        first = json.dumps({'type': 'user', 'timestamp': '2026-10-25T00:00:00.000Z',
                            'message': {'role': 'user', 'content': prompt}})
        tr.write_text(first + '\n' + FIXTURE.read_text(encoding='utf-8').split('\n', 1)[1], encoding='utf-8')
        self.stop(transcript=tr)
        f = self.last()
        self.assertEqual((f['unit'], f['end']), ('u2', 'ok'))
        self.hook('call', CALL)   # no unit line: no unit= field
        self.assertNotIn('unit', self.last())

    def test_call_ignored_for_others(self):
        self.hook('call', dict(CALL, tool_input={'subagent_type': 'Explore', 'prompt': 'x'}))
        self.assertEqual(log_lines(self.task), [])

    def test_start_uses_call_model_then_definition(self):
        self.hook('call', CALL)
        self.start()
        f = self.last()
        self.assertEqual((f['agent'], f['id'], f['configured'], f['effort']),
                         ('my-agent:probe-worker', 'ag1', 'opus', 'low'))
        self.assertNotIn('mode', f)   # SubagentStart has no permission_mode (probe); stop: carries it
        self.hook('call', dict(CALL, tool_input={'subagent_type': 'my-agent:probe-worker', 'prompt': 'x'}))
        self.start('ag2')
        f = self.last()
        self.assertEqual((f['configured'], f['effort']), ('haiku', 'low'))

    def test_start_effort_from_env(self):
        self.start(env={'CLAUDE_CODE_EFFORT_LEVEL': 'high'})
        self.assertEqual(self.last()['effort'], 'high(env)')

    def test_start_unknown_definition(self):
        self.start(agent='my-agent:nobody')
        lines = [parse(l) for l in log_lines(self.task)]
        self.assertTrue(any(f.get('configured') == 'unknown' for f in lines))
        self.assertTrue(any('where' in f for f in lines))   # log-error line

    def test_stop_from_transcript(self):
        self.start()
        self.stop()
        f = self.last()
        self.assertEqual({k: f[k] for k in ('id', 'actual', 'tokens', 'in', 'out', 'cw', 'cr', 'secs', 'result', 'end')},
                         {'id': 'ag1', 'actual': 'claude-haiku-5-5', 'tokens': '2180', 'in': '103', 'out': '27',
                          'cw': '1050', 'cr': '1000', 'secs': '12', 'result': 'DONE', 'end': 'ok'})
        self.assertNotIn('mismatch', f)
        agent = [i for i in events(self.task).log if i['k'] == 'agent'][-1]
        self.assertEqual((agent['res'], agent['live']), ('DONE', False))

    def test_stop_mismatch(self):
        self.hook('call', dict(CALL, tool_input={'subagent_type': 'my-agent:probe-worker', 'model': 'sonnet'}))
        self.start()
        self.stop()
        self.assertEqual(self.last()['mismatch'], '1')

    def test_stop_without_start(self):
        self.stop(agent_id='lonely')
        f = self.last()
        self.assertEqual((f['id'], f['end']), ('lonely', 'ok'))
        self.assertNotIn('mismatch', f)

    def test_stop_empty_message_is_error(self):
        self.start()
        self.stop(message='')
        self.assertEqual((self.last()['end'], self.last()['result']), ('error', '-'))

    def test_stop_reads_subagent_handback(self):
        """The final report arrives as a SubagentHandback tool call; last_assistant_message is then empty (F30)."""
        tr = self.root / 'handback.jsonl'
        tr.write_text(FIXTURE.read_text().rstrip('\n') + '\n' + json.dumps({
            'type': 'assistant', 'timestamp': '2026-10-25T10:00:12Z',
            'message': {'id': 'm-hb', 'model': 'claude-haiku-5-5', 'usage': {},
                        'content': [{'type': 'tool_use', 'name': 'SubagentHandback',
                                     'input': {'message': 'BLOCKER 0\n\nchecked'}}]}}) + '\n')
        self.start()
        self.stop(transcript=tr, message='')
        self.assertEqual((self.last()['end'], self.last()['result']), ('ok', 'BLOCKER 0'))

    def test_stop_waits_briefly_for_a_late_handback(self):
        """Live run: SubagentStop fired before the SubagentHandback line reached the transcript (same second)."""
        import threading
        import time
        tr = self.root / 'late.jsonl'
        tr.write_text(FIXTURE.read_text().rstrip('\n') + '\n')
        line = json.dumps({'type': 'assistant', 'message': {'id': 'm-late', 'content': [
            {'type': 'tool_use', 'name': 'SubagentHandback', 'input': {'message': 'DONE late'}}]}}) + '\n'
        writer = threading.Timer(0.6, lambda: tr.open('a').write(line))
        self.start()
        writer.start()
        t0 = time.time()
        self.stop(transcript=tr, message='')
        writer.join()
        self.assertEqual((self.last()['end'], self.last()['result']), ('ok', 'DONE late'))
        self.assertLess(time.time() - t0, 5)

    def test_missing_transcript(self):
        self.start()
        self.stop(transcript=self.root / 'nope.jsonl')
        lines = [parse(l) for l in log_lines(self.task)]
        stop = [f for f in lines if f.get('id') == 'ag1' and 'end' in f][-1]
        self.assertEqual((stop['tokens'], stop['actual'], stop['end']), ('-', '-', 'error'))
        self.assertTrue(any('where' in f for f in lines))

    def test_start_records_session_stop_records_mode_and_effort(self):
        self.start(session_id='s-main')
        self.assertEqual(self.last()['session'], 's-main')
        self.stop(permission_mode='auto', effort={'level': 'low'})
        f = self.last()
        self.assertEqual((f['mode'], f['effort']), ('auto', 'low'))
        agent = [i for i in events(self.task).log if i['k'] == 'agent'][-1]
        self.assertEqual((agent['res'], agent['live'], agent['effort']), ('DONE', False, 'low'))

    def test_stop_written_once_per_id(self):
        self.start()
        self.stop()
        self.stop()
        self.assertEqual(sum(' stop: ' in l for l in log_lines(self.task)), 1)

    def test_resumed_agent_gets_a_stop_per_run(self):
        # live run: SendMessage resumed the architect twice (same id); only the first run got a stop: line.
        # Probe (2026-10-25): SubagentStart/SubagentStop fire again per resumed run. A run is read from its start: time.
        t = self.root / 'resumed.jsonl'
        t.write_text(FIXTURE.read_text().rstrip('\n') + '\n')
        self.start()
        self.stop(transcript=t)
        now = datetime.now(timezone.utc)
        at = lambda s: (now + timedelta(seconds=s)).isoformat().replace('+00:00', 'Z')
        more = [{'type': 'user', 'timestamp': at(1), 'message': {'role': 'user', 'content': 'The coordinator sent a message: fix it'}},
                {'type': 'assistant', 'timestamp': at(2),
                 'message': {'id': 'msg_9', 'model': 'claude-haiku-5-5',
                             'usage': {'input_tokens': 7, 'output_tokens': 3, 'cache_creation_input_tokens': 0,
                                       'cache_read_input_tokens': 10}}},
                # a mid-run message (background task done, or another SendMessage) does not start a new run
                {'type': 'user', 'timestamp': at(3), 'message': {'role': 'user', 'content': '[SYSTEM NOTIFICATION] task done'}},
                {'type': 'assistant', 'timestamp': at(5),
                 'message': {'id': 'msg_10', 'model': 'claude-haiku-5-5',
                             'content': [{'type': 'tool_use', 'name': 'SubagentHandback', 'input': {'message': 'DONE again'}}],
                             'usage': {'input_tokens': 1, 'output_tokens': 1, 'cache_creation_input_tokens': 0,
                                       'cache_read_input_tokens': 0}}}]
        with open(t, 'a') as f:
            f.write(''.join(json.dumps(r) + '\n' for r in more))
        self.start()
        self.stop(transcript=t, message='')
        stops = [parse(l) for l in log_lines(self.task) if ' stop: ' in l]
        self.assertEqual(len(stops), 2)
        self.assertEqual((stops[0]['tokens'], stops[0]['secs']), ('2180', '12'))
        self.assertEqual({k: stops[1][k] for k in ('tokens', 'in', 'out', 'cw', 'cr', 'secs', 'result', 'end')},
                         {'tokens': '22', 'in': '8', 'out': '4', 'cw': '0', 'cr': '10', 'secs': '4',
                          'result': 'DONE again', 'end': 'ok'})

    def test_bad_stdin(self):
        r = run_hook('subagent-log.py', 'stop', 'not json', self.cwd, env=self.env)
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        self.assertEqual(log_lines(self.task), [])

    def test_no_active_all_modes(self):
        empty = self.root / 'empty'
        empty.mkdir()
        for mode, payload in (('call', CALL), ('start', {'agent_type': 'my-agent:probe-worker', 'agent_id': 'x'}),
                              ('stop', {'agent_type': 'my-agent:probe-worker', 'agent_id': 'x',
                                        'agent_transcript_path': str(FIXTURE), 'last_assistant_message': 'DONE'})):
            with self.subTest(mode=mode):
                self.hook(mode, payload, cwd=empty)
        self.assertEqual(list(empty.iterdir()), [])

    def test_ignores_non_my_agent_start(self):
        self.start(agent='Explore')
        self.assertEqual(log_lines(self.task), [])


if __name__ == '__main__':
    unittest.main()

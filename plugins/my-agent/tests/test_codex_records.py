"""Record hooks, session id and data folder on Codex input: same run-log lines as the Claude case (criterion 5)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import L4, REPO, log_lines, make_task, parse, run_hook, run_script

FIX = REPO / 'tests' / 'fixtures' / 'codex'
SESSION = '019a0000-0000-7000-8000-000000000001'
WORKER_A = '019a0000-0000-7000-8000-0000000000b1'


def fixture(name, **kw):
    return dict(json.loads((FIX / name).read_text(encoding='utf-8')), **kw)


class CodexRecordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root / 'proj', session=SESSION)
        self.cwd = self.root / 'proj'
        self.plugin = self.root / 'plugin'
        (self.plugin / '.claude-plugin').mkdir(parents=True)
        (self.plugin / 'agents').mkdir()
        (self.plugin / '.claude-plugin' / 'plugin.json').write_text(
            json.dumps({'name': 'my-agent', 'agents': ['./agents/coder.md']}))
        (self.plugin / 'agents' / 'coder.md').write_text('---\nname: coder\nmodel: opus\neffort: high\n---\nbody\n')
        self.tmpdir = self.root / 'tmp'
        self.tmpdir.mkdir()
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'CLAUDE_PLUGIN_ROOT': str(self.plugin),
                    'CLAUDE_CODE_EFFORT_LEVEL': '', 'MA_HOST': 'codex', 'TMPDIR': str(self.tmpdir)}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, script, mode, payload, env=None):
        r = run_hook(script, mode, payload, self.cwd, env=dict(self.env, **(env or {})))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def last(self):
        return parse(log_lines(self.task)[-1])

    def test_call_line_from_spawn_tool(self):
        inp = fixture('hook-pre-tool-use-spawn-agent.json')
        inp['tool_input'] = dict(inp['tool_input'], agent_type='my-agent-coder',
                                 message='Work unit: u3 Make it\nbody')
        self.hook('subagent-log.py', 'call', inp)
        f = self.last()
        self.assertEqual((f['agent'], f['unit']), ('my-agent:coder', 'u3'))
        claude = dict(inp, tool_name='Agent',
                      tool_input={'subagent_type': 'my-agent:coder', 'prompt': 'Work unit: u3 Make it\nbody'})
        task2 = make_task(self.root / 'proj2', session=SESSION)
        run_hook('subagent-log.py', 'call', claude, self.root / 'proj2', env=dict(self.env, MA_HOST='claude'))
        self.assertEqual(set(parse(log_lines(task2)[-1])), set(f))

    def test_call_line_carries_model_and_effort(self):
        inp = fixture('hook-pre-tool-use-spawn-agent.json')
        inp['tool_input'] = dict(inp['tool_input'], agent_type='my-agent-coder', message='Work unit: u3 Make it',
                                 model='gpt-6-luna', reasoning_effort='medium')
        self.hook('subagent-log.py', 'call', inp)
        f = self.last()
        self.assertEqual((f['agent'], f['model'], f['effort']), ('my-agent:coder', 'gpt-6-luna', 'medium'))
        inp['tool_input'] = {k: v for k, v in inp['tool_input'].items() if k not in ('model', 'reasoning_effort')}
        self.hook('subagent-log.py', 'call', inp)
        f = self.last()
        self.assertEqual((f['model'], f['effort']), ('-', '-'))

    def test_start_takes_configured_from_the_call(self):
        inp = fixture('hook-pre-tool-use-spawn-agent.json')
        inp['tool_input'] = dict(inp['tool_input'], agent_type='my-agent-coder', message='x',
                                 model='gpt-6-luna', reasoning_effort='medium')
        self.hook('subagent-log.py', 'call', inp)
        self.hook('subagent-log.py', 'start', fixture('hook-subagent-start-worker-a.json'))
        f = self.last()
        self.assertEqual((f['configured'], f['effort']), ('gpt-6-luna', 'medium'))

    def test_non_my_agent_spawn_is_not_recorded(self):
        self.hook('subagent-log.py', 'call', fixture('hook-pre-tool-use-spawn-agent.json'))
        self.assertEqual(log_lines(self.task), [])

    def test_start_and_stop_lines(self):
        self.hook('subagent-log.py', 'start', fixture('hook-subagent-start-worker-a.json'))
        f = self.last()
        self.assertEqual((f['agent'], f['id'], f['configured'], f['session']),
                         ('my-agent:coder', WORKER_A, 'opus', SESSION))
        self.hook('subagent-log.py', 'stop', fixture('hook-subagent-stop-worker-a.json'))
        lines = log_lines(self.task)
        f = parse(lines[-1])
        self.assertIn(' stop: ', lines[-1])
        self.assertEqual((f['id'], f['result']), (WORKER_A, 'Worker finished.'))
        for key in ('actual', 'tokens', 'in', 'out', 'cw', 'cr', 'secs', 'end', 'mode', 'effort'):
            self.assertIn(key, f)

    def test_start_line_maps_hyphen_name(self):
        self.hook('subagent-log.py', 'start', fixture('hook-subagent-start-worker-a.json'))
        self.assertEqual(self.last()['agent'], 'my-agent:coder')

    def test_stop_reads_tokens_from_codex_record(self):
        rec = self.root / 'sub.jsonl'
        rec.write_text('\n'.join(json.dumps(e) for e in [
            {'timestamp': '2026-01-01T00:00:00.000Z', 'type': 'turn_context',
             'payload': {'turn_id': 't1', 'model': 'gpt-6-luna'}},
            {'timestamp': '2026-01-01T00:00:09.000Z', 'type': 'token_usage_record',
             'payload': {'thread_id': WORKER_A, 'turn_id': 't1',
                         'usage': {'input_tokens': 1000, 'cached_input_tokens': 400, 'cache_write_input_tokens': 0,
                                   'output_tokens': 30}}}]) + '\n')
        self.hook('subagent-log.py', 'start', fixture('hook-subagent-start-worker-a.json'))
        self.hook('subagent-log.py', 'stop',
                  fixture('hook-subagent-stop-worker-a.json', agent_transcript_path=str(rec)))
        f = self.last()
        self.assertEqual((f['actual'], f['in'], f['out'], f['cr']), ('gpt-6-luna', '600', '30', '400'))

    def test_permission_ask_and_answer(self):
        base = fixture('hook-pre-tool-use-worker-bash.json', hook_event_name='PermissionRequest')
        self.assertEqual(base['agent_type'], 'my-agent-coder')
        self.hook('permission-log.py', 'ask', base)
        f = self.last()
        self.assertEqual((f['gate'], f['agent'], f['id'], f['tool'], f['session']),
                         ('G2', 'my-agent:coder', base['agent_id'], 'Bash', SESSION))
        self.hook('permission-log.py', 'answer', dict(base, hook_event_name='PostToolUse', tool_response='ok'))
        f = self.last()
        self.assertEqual((f['gate'], f['result']), ('G2', 'allowed'))

    def test_permission_ask_main_session(self):
        self.hook('permission-log.py', 'ask',
                  fixture('hook-pre-tool-use-bash.json', hook_event_name='PermissionRequest'))
        self.assertEqual((self.last()['agent'], self.last()['id']), ('main', '-'))

    def test_session_notice(self):
        r = self.hook('session-notice.py', None, fixture('hook-session-start.json'))
        text = json.loads(r.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn('Run `/my-agent continue` before doing anything else.', text)

    def test_hooks_leave_marks_on_codex_only(self):
        self.hook('session-notice.py', None, fixture('hook-session-start.json'))
        marks = self.tmpdir / 'my-agent-codex' / 'marks' / SESSION
        self.assertTrue((marks / 'session-notice').is_file())
        self.hook('permission-log.py', 'ask', fixture('hook-pre-tool-use-bash.json'))
        self.assertTrue((marks / 'permission-log').is_file())
        other = self.root / 'tmp2'
        other.mkdir()
        run_hook('permission-log.py', 'ask', fixture('hook-pre-tool-use-bash.json'), self.cwd,
                 env=dict(self.env, MA_HOST='claude', TMPDIR=str(other)))
        self.assertEqual(list(other.iterdir()), [])

    def test_data_dir_same_in_both_hosts(self):
        sys.path.insert(0, str(L4 / 'lib'))
        import ma_data
        keys = ('MA_TASKS_DIR', 'MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_DATA_DIR', 'MA_HOST')
        old = {k: os.environ.pop(k, None) for k in keys}
        try:
            for host in ('claude', 'codex'):
                os.environ['MA_HOST'] = host
                os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = str(self.root / 'data')
                self.assertEqual(ma_data.data_dir(), self.root / 'data')
                os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = '${user_config.data_dir}'
                self.assertEqual(ma_data.data_dir(), Path.home() / 'dev' / 'log' / 'my-agent')
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_run_log_session_from_codex_thread_id(self):
        env = dict(self.env, CODEX_THREAD_ID='thread-7', MA_STATUSLINE_DIR=str(self.root))
        r = run_script(L4 / 'scripts' / 'run-log.py', 'ask', 'gate=G3', 'q=x', '--cwd', str(self.cwd),
                       env=env, drop=('CLAUDE_CODE_SESSION_ID',))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last()['session'], 'thread-7')


if __name__ == '__main__':
    unittest.main()

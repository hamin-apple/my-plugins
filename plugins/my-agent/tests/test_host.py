"""ma_host.py: the host adapter (Codex hook input -> Claude-shaped inputs, decision output per host)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts lib on sys.path)
import ma_host

FIX = Path(__file__).resolve().parent / 'fixtures' / 'codex'


def fixture(name):
    return (FIX / name).read_text(encoding='utf-8')


def patch(*body):
    return '*** Begin Patch\n' + '\n'.join(body) + '\n*** End Patch'


def codex_file(text, agent=None):
    d = json.loads(fixture('hook-pre-tool-use-file-change.json'))
    d['tool_input'] = {'command': text}
    if agent:
        d.update(agent_type=agent, agent_id='a1')
    return json.dumps(d)


class HostTest(unittest.TestCase):
    def test_claude_input_passes_unchanged(self):
        raw = json.dumps({'tool_name': 'Edit', 'tool_input': {'file_path': 'x'}, 'agent_type': 'my-agent:coder'})
        c = ma_host.parse(raw)
        self.assertEqual((c.host, c.file_change), ('claude', False))
        self.assertEqual(c.inps, [json.loads(raw)])

    def test_non_object_passes_and_bad_json_raises(self):
        self.assertEqual(ma_host.parse('[1]').inps, [[1]])
        with self.assertRaises(ValueError):
            ma_host.parse('not json')

    def test_names_map_both_ways(self):
        self.assertEqual(ma_host.claude_agent('my-agent-plan-reviewer'), 'my-agent:plan-reviewer')
        self.assertEqual(ma_host.codex_agent('my-agent:gate-analyst'), 'my-agent-gate-analyst')
        self.assertEqual(ma_host.claude_agent('default'), 'default')
        for name in ('my-agent-plan-reviewer', 'my-agent-gate-analyst'):
            self.assertEqual(ma_host.codex_agent(ma_host.claude_agent(name)), name)
        for name in ('my-explorer', 'worker'):
            self.assertEqual(ma_host.claude_agent(name), name)
            self.assertEqual(ma_host.codex_agent(name), name)

    def test_codex_prefix_agent_types(self):
        self.assertTrue(ma_host.is_codex({'agent_type': 'my-agent-coder'}))
        self.assertFalse(ma_host.is_codex({'agent_type': 'my-explorer'}))
        # pins the prefix match: a Claude-style type that starts with `my-agent-` counts as Codex
        self.assertTrue(ma_host.is_codex({'agent_type': 'my-agent-tray:helper'}))
        self.assertEqual(ma_host.claude_agent('my-agent-tray:helper'), 'my-agent:tray:helper')

    def test_worker_bash(self):
        c = ma_host.parse(fixture('hook-pre-tool-use-worker-bash.json'))
        self.assertEqual(c.host, 'codex')
        inp = c.inps[0]
        self.assertEqual((inp['tool_name'], inp['agent_type'], inp['tool_input']), ('Bash', 'my-agent:coder', {'command': 'ls -la'}))
        self.assertEqual(inp['agent_id'], '019a0000-0000-7000-8000-0000000000b1')

    def test_worker_file_change(self):
        c = ma_host.parse(fixture('hook-pre-tool-use-worker-file-change.json'))
        self.assertTrue(c.file_change)
        self.assertEqual(len(c.inps), 1)
        inp = c.inps[0]
        self.assertEqual((inp['tool_name'], inp['tool_input']['file_path'], inp['agent_type']),
                         ('Write', 'notes/worker-made-up.txt', 'my-agent:coder'))

    def test_spawn_becomes_agent(self):
        d = json.loads(fixture('hook-pre-tool-use-spawn-agent.json'))
        d['tool_input']['agent_type'] = 'my-agent-plan-reviewer'
        c = ma_host.parse(json.dumps(d))
        inp = c.inps[0]
        self.assertEqual(inp['tool_name'], 'Agent')
        self.assertEqual(inp['tool_input']['subagent_type'], 'my-agent:plan-reviewer')
        self.assertFalse(c.file_change)

    def test_spawn_model_and_effort_pass_through(self):
        d = json.loads(fixture('hook-pre-tool-use-spawn-agent.json'))
        d['tool_input'].update(agent_type='my-agent-coder', model='gpt-6-luna', reasoning_effort='medium')
        ti = ma_host.parse(json.dumps(d)).inps[0]['tool_input']
        self.assertEqual((ti['model'], ti['effort']), ('gpt-6-luna', 'medium'))
        ti = ma_host.record_input(d)['tool_input']
        self.assertEqual((ti['model'], ti['effort']), ('gpt-6-luna', 'medium'))
        for key in ('model', 'reasoning_effort'):
            del d['tool_input'][key]
        for ti in (ma_host.parse(json.dumps(d)).inps[0]['tool_input'], ma_host.record_input(d)['tool_input']):
            self.assertNotIn('model', ti)
            self.assertNotIn('effort', ti)

    def test_spawn_without_agent_type_raises(self):
        d = json.loads(fixture('hook-pre-tool-use-spawn-agent.json'))
        del d['tool_input']['agent_type']
        with self.assertRaises(ValueError):
            ma_host.parse(json.dumps(d))

    def test_patch_targets(self):
        text = patch('*** Add File: a.txt', '+one', '+two', '*** Update File: b.txt', '*** Move to: c.txt',
                     '@@ def f():', ' keep', '-old', '+new', '*** Delete File: d.txt')
        got = [(i['tool_name'], i['tool_input']['file_path']) for i in ma_host.parse(codex_file(text)).inps]
        self.assertEqual(got, [('Write', 'a.txt'), ('Edit', 'c.txt'), ('Edit', 'b.txt'), ('Edit', 'd.txt')])
        edit = ma_host.parse(codex_file(text)).inps[2]['tool_input']
        self.assertEqual((edit['old_string'], edit['new_string']), ('keep\nold', 'keep\nnew'))
        self.assertEqual(ma_host.parse(codex_file(text)).inps[0]['tool_input']['content'], 'one\ntwo')

    def test_unreadable_patches_raise(self):
        for text in ('', 'garbage', patch('+nothing named'), patch('*** Add File: ')):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    ma_host.parse(codex_file(text))
        for bad in ({'tool_name': 'apply_patch'}, {'tool_name': 'apply_patch', 'tool_input': {'command': 3}},
                    {'tool_name': 'apply_patch', 'tool_input': 'x'},
                    {'tool_name': 'Bash', 'agent_type': 'my-agent-coder', 'tool_input': {}},
                    {'tool_name': 'Bash', 'agent_type': 'my-agent-coder'}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ma_host.parse(json.dumps(bad))

    def test_stronger(self):
        deny = {'hookSpecificOutput': {'permissionDecision': 'deny'}}
        ask = {'hookSpecificOutput': {'permissionDecision': 'ask'}}
        msg = {'systemMessage': 'x'}
        self.assertIs(ma_host.stronger(None, msg), msg)
        self.assertIs(ma_host.stronger(msg, ask), ask)
        self.assertIs(ma_host.stronger(ask, deny), deny)
        self.assertIs(ma_host.stronger(deny, ask), deny)

    def test_emit_forms(self):
        deny = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                       'permissionDecisionReason': 'why'}}
        for call, code, out, err in (
                (ma_host.Call('claude', [], False), 0, json.dumps(deny) + '\n', ''),
                (ma_host.Call('codex', [], False), 0, json.dumps(deny) + '\n', ''),
                (ma_host.Call('codex', [], True), 2, '', 'why\n')):
            o, e = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
                self.assertEqual(ma_host.emit(call, deny), code)
            self.assertEqual((o.getvalue(), e.getvalue()), (out, err))
        self.assertEqual(ma_host.emit(ma_host.Call('codex', [], True), None), 0)

    def test_emit_codex_ask_goes_to_ma_g2(self):
        ask = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                      'permissionDecisionReason': 'why'}}
        deny = {'hookSpecificOutput': {'permissionDecision': 'deny', 'permissionDecisionReason': 'no'}}
        bash = json.loads(fixture('hook-pre-tool-use-bash.json'))
        self.assertNotIn('agent_id', bash)
        self.assertEqual(ma_host.parse(json.dumps(bash)).host, 'claude')   # a main-session Bash input is not reshaped
        cases = (('apply_patch', codex_file(patch('*** Add File: src/x.py', '+x'))),
                 ('Bash', json.dumps(dict(bash, tool_input={'command': 'echo x > src/y.txt'}))))
        for tool, raw in cases:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                task = helpers.make_task(root, session='019a0000-0000-7000-8000-000000000001')
                raw = json.dumps(dict(json.loads(raw), cwd=str(root)))
                env = {'MA_TASKS_DIR': str(root / 'data'), 'MA_HOST': ''}
                err = io.StringIO()
                with mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', ['plan-approved-check.py']), \
                        contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(ma_host.emit(ma_host.parse(raw), ask), 2)
                    self.assertEqual(out.getvalue(), '')
                    self.assertEqual(ma_host.emit(ma_host.parse(raw), deny), 2 if tool == 'apply_patch' else 0)
                self.assertTrue(err.getvalue().startswith('my-agent G2 (plan-approved-check): why.'), err.getvalue())
                lines = helpers.log_lines(task)
                self.assertEqual(len(lines), 1)   # the ask line; a deny writes none
                f = helpers.parse(lines[0])
                self.assertEqual((f['gate'], f['tool'], f['hook']), ('G2', tool, 'plan-approved-check'))

    def test_emit_claude_ask_keeps_json(self):
        ask = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                      'permissionDecisionReason': 'why'}}
        claude = json.dumps({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'session_id': 's',
                             'tool_input': {'command': 'ls'}})
        o, e = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {'MA_HOST': 'claude'}), contextlib.redirect_stdout(o), \
                contextlib.redirect_stderr(e):
            self.assertEqual(ma_host.emit(ma_host.parse(claude), ask), 0)
        self.assertEqual((o.getvalue(), e.getvalue()), (json.dumps(ask) + '\n', ''))

    def test_scratch_base_per_host(self):
        self.assertIn('claude-', str(ma_host.scratch_base({})))
        self.assertIn('my-agent-codex', str(ma_host.scratch_base({'_host': 'codex'})))


if __name__ == '__main__':
    unittest.main()

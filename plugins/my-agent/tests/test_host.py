"""ma_host.py: the host adapter (Codex hook input -> Claude-shaped inputs, decision output per host)."""
import contextlib
import io
import json
import unittest
from pathlib import Path

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
        self.assertEqual(ma_host.claude_agent('my_agent_plan_reviewer'), 'my-agent:plan-reviewer')
        self.assertEqual(ma_host.codex_agent('my-agent:gate-analyst'), 'my_agent_gate_analyst')
        self.assertEqual(ma_host.claude_agent('default'), 'default')

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
        d['tool_input']['agent_type'] = 'my_agent_plan_reviewer'
        c = ma_host.parse(json.dumps(d))
        inp = c.inps[0]
        self.assertEqual(inp['tool_name'], 'Agent')
        self.assertEqual(inp['tool_input']['subagent_type'], 'my-agent:plan-reviewer')
        self.assertFalse(c.file_change)

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
                    {'tool_name': 'Bash', 'agent_type': 'my_agent_coder', 'tool_input': {}},
                    {'tool_name': 'Bash', 'agent_type': 'my_agent_coder'}):
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

    def test_scratch_base_per_host(self):
        self.assertIn('claude-', str(ma_host.scratch_base({})))
        self.assertIn('my-agent-codex', str(ma_host.scratch_base({'_host': 'codex'})))


if __name__ == '__main__':
    unittest.main()

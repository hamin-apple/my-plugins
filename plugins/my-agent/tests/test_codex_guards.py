"""The three gate hooks on Codex-shaped input (ma_host): same decisions as for Claude, in the host's output form."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import make_task, run_hook

TASK = '261025-probe-task'
FIX = Path(__file__).resolve().parent / 'fixtures' / 'codex'


def fixture(name, **over):
    d = json.loads((FIX / name).read_text(encoding='utf-8'))
    d.update(over)
    return d


def patch(*body):
    return '*** Begin Patch\n' + '\n'.join(body) + '\n*** End Patch'


def decision(r):
    """(exit code, decision or None) of a hook run; stdout must be JSON or empty."""
    if not r.stdout:
        return r.returncode, None
    return r.returncode, json.loads(r.stdout)['hookSpecificOutput']['permissionDecision']


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.L = self.root / 'proj'
        self.L.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.L)], check=True)
        self.T = make_task(self.L, task=TASK, git=False, session='019a0000-0000-7000-8000-000000000001')
        (self.L / 'src').mkdir()
        self.env = {'MA_TASKS_DIR': str(self.root / 'agent-tasks'), 'MA_GATE_REPORT_DIR': str(self.root / 'gate-report')}

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, script, payload):
        return run_hook(script, None, payload, self.L, env=self.env)

    def worker_file(self, text, agent='my_agent_coder'):
        d = fixture('hook-pre-tool-use-worker-file-change.json', agent_type=agent)
        d['tool_input'] = {'command': text}
        return d

    def main_file(self, text):
        d = fixture('hook-pre-tool-use-file-change.json')
        d['tool_input'] = {'command': text}
        return d

    def guard_lines(self):
        p = self.T / 'run-log.md'
        return [x for x in p.read_text(encoding='utf-8').splitlines() if ' guard: ' in x] if p.exists() else []


class ScopeGuardCodexTest(Base):
    def scope(self, payload):
        return self.run_it('scope-guard.py', payload)

    def test_worker_bash_same_decision_as_claude(self):
        for cmd, denied in (('ls -la', False), ('cat /etc/hosts', True)):
            with self.subTest(cmd=cmd):
                codex = self.scope(fixture('hook-pre-tool-use-worker-bash.json', tool_input={'command': cmd}))
                claude = self.scope({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': cmd},
                                     'session_id': 's', 'agent_type': 'my-agent:coder', 'agent_id': 'a1'})
                self.assertEqual(decision(codex), decision(claude))
                self.assertEqual(decision(codex), (0, 'deny') if denied else (0, None))

    def test_worker_file_change_inside_passes(self):
        r = self.scope(self.worker_file(patch('*** Add File: src/new.txt', '+x', '*** Update File: src/a.py', '@@', '-a', '+b')))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_worker_file_change_outside_is_exit2(self):
        outside = self.root / 'elsewhere.txt'
        r = self.scope(self.worker_file(patch(f'*** Add File: {outside}', '+x')))
        self.assertEqual((r.returncode, r.stdout), (2, ''))
        self.assertIn('Outside the write scope of coder', r.stderr)
        self.assertEqual(len(self.guard_lines()), 1)
        self.assertIn('agent=my-agent:coder', self.guard_lines()[0])

    def test_one_target_outside_denies_the_patch(self):
        r = self.scope(self.worker_file(patch('*** Add File: src/ok.txt', '+x', f'*** Delete File: {self.root}/x.txt')))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(self.guard_lines()), 1)

    def test_read_only_roles_and_secrets(self):
        r = self.scope(self.worker_file(patch('*** Add File: src/new.txt', '+x'), agent='my_agent_explorer'))
        self.assertEqual(r.returncode, 2)
        r = self.scope(self.worker_file(patch('*** Add File: src/.env', '+x')))
        self.assertEqual(r.returncode, 2)

    def test_role_with_hyphen_maps(self):
        r = self.scope(self.worker_file(patch(f'*** Add File: {self.T}/plan-review.md', '+x'), agent='my_agent_plan_reviewer'))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)
        r = self.scope(self.worker_file(patch(f'*** Add File: {self.T}/plan.md', '+x'), agent='my_agent_plan_reviewer'))
        self.assertEqual(r.returncode, 2)

    def test_fail_closed(self):
        bad = [
            'my_agent_ not json',
            json.dumps({'agent_type': 'my_agent_coder', 'tool_name': 'Bash'}),
            json.dumps({'agent_type': 'my_agent_coder', 'tool_name': 'apply_patch', 'tool_input': {}}),
            json.dumps(self.worker_file('no patch here')),
            json.dumps(self.worker_file(patch('+names no target'))),
            json.dumps(self.worker_file(patch('*** Add File: '))),
            json.dumps(fixture('hook-pre-tool-use-worker-bash.json', tool_input={'cmd': 'ls'})),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                r = run_hook('scope-guard.py', None, raw, self.L, env=self.env)
                self.assertEqual(r.returncode, 2)

    def test_main_session_and_other_agents_skipped(self):
        r = self.scope(self.main_file(patch(f'*** Add File: {self.root}/x.txt', '+x')))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        r = self.scope(fixture('hook-pre-tool-use-worker-bash.json', agent_type='default',
                               tool_input={'command': 'cat /etc/hosts'}))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_claude_active_with_codex_call_has_no_task_denies_like_claude(self):
        (self.L / '.my-agent' / '.active').unlink()
        r = self.scope(fixture('hook-pre-tool-use-worker-bash.json'))
        self.assertEqual(decision(r), (0, 'deny'))


class PlanApprovedCodexTest(Base):
    def gate(self, payload):
        return self.run_it('plan-approved-check.py', payload)

    def spawn(self, agent):
        d = fixture('hook-pre-tool-use-spawn-agent.json')
        d['tool_input']['agent_type'] = agent
        return d

    def test_spawn_before_approval(self):
        for agent, want in (('my_agent_coder', 'deny'), ('default', 'deny'), ('my_agent_explorer', None),
                            ('my_agent_plan_reviewer', None)):
            with self.subTest(agent=agent):
                self.assertEqual(decision(self.gate(self.spawn(agent))), (0, want))
        self.assertEqual(len(self.guard_lines()), 2)
        claude = self.gate({'hook_event_name': 'PreToolUse', 'tool_name': 'Agent', 'session_id': '019a0000-0000-7000-8000-000000000001',
                            'tool_input': {'subagent_type': 'my-agent:coder'}})
        self.assertEqual(decision(claude), (0, 'deny'))

    def test_file_change_before_approval(self):
        inside = self.gate(self.main_file(patch(f'*** Add File: {self.T}/work/n.md', '+x')))
        self.assertEqual((inside.returncode, inside.stdout), (0, ''))
        outside = self.gate(self.main_file(patch('*** Add File: src/x.py', '+x')))
        self.assertEqual((outside.returncode, outside.stdout), (2, ''))   # ask on the file-change tool: exit 2
        self.assertIn('plan gate', outside.stderr)
        mixed = self.gate(self.main_file(patch(f'*** Add File: {self.T}/work/n.md', '+x', '*** Add File: src/x.py', '+x')))
        self.assertEqual(mixed.returncode, 2)

    def test_bash_ask_keeps_json(self):
        r = self.gate(fixture('hook-pre-tool-use-bash.json', tool_input={'command': 'echo x > src/y.txt'}))
        self.assertEqual(decision(r), (0, 'ask'))

    def test_worker_call_and_other_session_pass(self):
        r = self.gate(fixture('hook-pre-tool-use-worker-bash.json', tool_input={'command': 'echo x > /etc/y'}))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        r = self.gate(dict(self.spawn('my_agent_coder'), session_id='019a0000-0000-7000-8000-0000000000ff'))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        r = self.gate(dict(self.main_file(patch('*** Add File: src/x.py', '+x')), session_id='other'))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_fail_closed(self):
        bad = [
            'not json at all',
            json.dumps({'tool_name': 'apply_patch', 'session_id': 's'}),
            json.dumps(self.main_file('no patch')),
            json.dumps(self.main_file(patch('+names no target'))),
            json.dumps({'tool_name': 'collaborationspawn_agent', 'tool_input': {'message': 'x'}, 'session_id': 's'}),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                self.assertEqual(run_hook('plan-approved-check.py', None, raw, self.L, env=self.env).returncode, 2)


class VerdictFreshCodexTest(Base):
    def setUp(self):
        super().setUp()
        self.t0 = time.time() - 1000

    def file(self, path, text, at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        os.utime(path, (self.t0 + at, self.t0 + at))

    def verdicts(self, verify_at=10, review_at=10):
        self.file(self.T / 'verify.md', 'Verdict: ALL PASS\n', verify_at)
        self.file(self.T / 'review.md', 'BLOCKER 0\n', review_at)

    def vfc(self, payload):
        return self.run_it('verdict-fresh-check.py', payload)

    def test_commit_with_stale_verdict_asks_in_json(self):
        self.verdicts()
        self.file(self.L / 'src/a.py', 'x', 30)
        r = self.vfc(fixture('hook-pre-tool-use-bash.json', tool_input={'command': 'git commit -m x'}))
        self.assertEqual(decision(r), (0, 'ask'))
        self.verdicts(verify_at=40, review_at=40)
        r = self.vfc(fixture('hook-pre-tool-use-bash.json', tool_input={'command': 'git commit -m x'}))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_deliverable_write_stale_is_exit2_fresh_passes(self):
        text = patch(f'*** Add File: {self.T}/deliverable/out.md', '+x')
        r = self.vfc(self.main_file(text))
        self.assertEqual((r.returncode, r.stdout), (2, ''))
        self.assertIn('G3', r.stderr)
        self.verdicts(verify_at=900, review_at=900)
        r = self.vfc(self.main_file(text))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_other_file_changes_and_other_sessions_pass(self):
        r = self.vfc(self.main_file(patch('*** Add File: src/x.py', '+x')))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        text = patch(f'*** Add File: {self.T}/deliverable/out.md', '+x')
        r = self.vfc(dict(self.main_file(text), session_id='other'))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        r = self.vfc(fixture('hook-pre-tool-use-worker-file-change.json', tool_input={'command': text}))
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_fail_closed(self):
        for raw in ('{', json.dumps(self.main_file('no patch')), json.dumps({'tool_name': 'apply_patch'})):
            with self.subTest(raw=raw[:40]):
                self.assertEqual(run_hook('verdict-fresh-check.py', None, raw, self.L, env=self.env).returncode, 2)


if __name__ == '__main__':
    unittest.main()

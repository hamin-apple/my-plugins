"""plan-approved-check.py: the G1b hard gate (architecture 4.4 "G1b hard gate")."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import L4, clean_task_env, make_task, records, rel, run_hook
import ma_logline

TASK = '261025-probe-task'


class PlanApprovedCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.proj = self.root / 'proj'
        self.task = make_task(self.proj, task=TASK)
        self.tasks_dir = self.root / 'agent-tasks'
        self.tasks_dir.mkdir()
        self.reports = self.root / 'my-surrogate' / 'gate-report'
        self.env = {'MA_TASKS_DIR': str(self.tasks_dir), 'MA_GATE_REPORT_DIR': str(self.reports)}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, tool, tool_input, cwd=None, env=None, **extra):
        payload = dict({'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': tool_input,
                        'session_id': 's-test'}, **extra)
        return run_hook('plan-approved-check.py', None, payload, cwd or self.proj, env=env or self.env)

    def assertDenied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual(out['hookEventName'], 'PreToolUse')
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn(TASK, out['permissionDecisionReason'])
        self.assertIn('delegation and workflows are blocked, writes are asked (G1b)', out['permissionDecisionReason'])

    GATE = 'my-agent plan gate: write outside the task folder ({}); allow it only if this is your own request, not the task\'s'

    def assertAsked(self, r, slot=None):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'ask'))
        if slot is not None:
            self.assertEqual(out['permissionDecisionReason'], self.GATE.format(slot))
        return out['permissionDecisionReason']

    def assertPassed(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '')

    def plan(self, text):
        (self.task / 'plan.md').write_text(text, encoding='utf-8')

    def guard_lines(self):
        p = self.task / 'run-log.md'
        return [l for l in p.read_text(encoding='utf-8').splitlines() if ' guard: ' in l] if p.exists() else []

    def test_delegation_deny_writes_guard_line(self):
        r = self.hook('Agent', {'subagent_type': 'my-agent:coder'})
        self.assertDenied(r)
        lines = self.guard_lines()
        self.assertEqual(len(lines), 1)
        kind, f = ma_logline.parse_line(lines[0])
        self.assertEqual(kind, 'guard')
        self.assertEqual((f['hook'], f['agent'], f['id'], f['tool'], f['decision']),
                         ('plan-approved-check', 'main', '-', 'Agent', 'deny'))
        self.assertEqual(f['why'], json.loads(r.stdout)['hookSpecificOutput']['permissionDecisionReason'])

    def test_ask_writes_no_guard_line(self):
        self.assertAsked(self.hook('Write', {'file_path': str(self.root / 'outside.txt')}))
        self.assertEqual(self.guard_lines(), [])

    def test_not_applicable_is_silent(self):
        other = self.root / 'other'
        (other / '.git').mkdir(parents=True)
        self.assertPassed(self.hook('Edit', {'file_path': str(other / 'a.py')}, cwd=other))
        self.assertPassed(self.hook('Workflow', {'script': 'x'}, cwd=other))

    def test_define_phase_blocks_write(self):
        self.assertAsked(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}), str(self.proj / 'src/a.py'))
        self.assertAsked(self.hook('Write', {'file_path': str(self.proj / 'README.md')}), str(self.proj / 'README.md'))
        self.assertAsked(self.hook('NotebookEdit', {'notebook_path': str(self.proj / 'n.ipynb')}), str(self.proj / 'n.ipynb'))

    def test_define_phase_allows_task_folder_write(self):
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'explore.md')}))
        self.assertPassed(self.hook('Edit', {'file_path': str(records(self.proj) / '.active')}))

    def test_sibling_task_folder_asks_before_approval(self):
        sib = records(self.proj) / '261024-other-task'
        sib.mkdir()
        for tool, ti in (('Write', {'file_path': str(sib / 'work/a.md')}),
                         ('Edit', {'file_path': str(sib / 'plan.md')})):
            with self.subTest(tool=tool):
                self.assertAsked(self.hook(tool, ti), ti['file_path'])
        self.assertIn(str(sib / 'work/a.md'), self.assertAsked(self.hook('Bash', {'command': f'cp a.md {sib}/work/a.md'})))
        self.assertIn(str(sib / 'x.md'), self.assertAsked(self.hook('Bash', {'command': f'echo x > {sib}/x.md'})))

    def test_active_task_and_bookkeeping_pass_before_approval(self):
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'work/a.md')}))
        self.assertPassed(self.hook('Bash', {'command': f'cp a.md {self.task}/work/a.md'}))
        self.assertPassed(self.hook('Edit', {'file_path': str(records(self.proj) / '.active')}))
        for name in ('active-index.json', 'projects.txt'):
            self.assertPassed(self.hook('Write', {'file_path': str(self.tasks_dir / name)}))

    def test_sibling_task_folder_after_approval_unchanged(self):
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        sib = records(self.proj) / '261024-other-task'
        sib.mkdir()
        self.assertPassed(self.hook('Write', {'file_path': str(sib / 'a.md')}))

    def test_allows_index_and_projects(self):
        for name in ('active-index.json', 'projects.txt'):
            self.assertPassed(self.hook('Write', {'file_path': str(self.tasks_dir / name)}))
        self.assertAsked(self.hook('Write', {'file_path': str(self.tasks_dir / 'monitor.json')}), str(self.tasks_dir / 'monitor.json'))
        self.assertAsked(self.hook('Write', {'file_path': str(self.tasks_dir / 'feedback.md')}), str(self.tasks_dir / 'feedback.md'))
        projects = self.tasks_dir / 'projects.txt'
        self.assertPassed(self.hook('Bash', {'command': f'mkdir -p {self.tasks_dir} && echo /p >> {projects}'}))
        self.assertAsked(self.hook('Bash', {'command': f'mkdir -p {self.tasks_dir}/x'}), f'{self.tasks_dir}/x')

    def test_allowlist(self):
        for agent in ('my-agent:explorer', 'my-agent:architect', 'my-agent:plan-reviewer'):
            self.assertPassed(self.hook('Agent', {'subagent_type': agent, 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'general-purpose', 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:writer', 'prompt': 'x'}))
        self.plan('# Plan\n\nPrototype: requested\n\n## Prototype\n\nneeded\n\n## Approval\n')   # A5: outside the section
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:writer', 'prompt': 'x'}))
        self.plan('# Plan\n\n## Prototype\n\nPrototype: requested\n\n## Approval\n')
        self.assertPassed(self.hook('Agent', {'subagent_type': 'my-agent:writer', 'prompt': 'x'}))

    def test_writer_at_g1a_prototype_from_scope(self):
        """Criterion 9: scope.md `Prototype: requested` opens the writer before approval, and only the writer."""
        writer = {'subagent_type': 'my-agent:writer', 'prompt': 'x'}
        self.assertDenied(self.hook('Agent', writer))
        scope = self.task / 'scope.md'
        scope.write_text('# Scope\n\nPrototype: requested\n\n## Prototype\n\nneeded\n', encoding='utf-8')   # outside the section
        self.assertDenied(self.hook('Agent', writer))
        scope.write_text('# Scope\n\n## Prototype\n\nPrototype: requested\n\n## Next\n', encoding='utf-8')
        self.assertPassed(self.hook('Agent', writer))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))
        self.assertDenied(self.hook('Workflow', {'script': 'x'}))

    def test_deny_line_carries_cwd(self):
        self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'})
        self.assertTrue(self.guard_lines()[0].endswith(f'cwd={self.proj}'))

    def test_broken_active_warns(self):
        """C9: a `.active` without `task:` passes, but says so instead of passing silently."""
        (records(self.proj) / '.active').write_text('phase: 2\n')
        r = self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('task:', json.loads(r.stdout)['systemMessage'])

    def test_workflow_denied(self):
        self.assertDenied(self.hook('Workflow', {'script': 'x'}))

    def test_bash_patterns(self):
        self.assertAsked(self.hook('Bash', {'command': 'rm -rf src'}), str(self.proj / 'src'))
        self.assertAsked(self.hook('Bash', {'command': 'git checkout -- a'}), 'cannot tell: git checkout -- a')
        self.assertAsked(self.hook('Bash', {'command': 'echo x > "$F"'}), 'cannot tell: echo x > "$F"')
        self.assertPassed(self.hook('Bash', {'command': f'mkdir -p {rel()}/{TASK}/work'}))
        self.assertPassed(self.hook('Bash', {'command': f'echo "{self.proj}" >> {self.tasks_dir}/projects.txt'}))
        self.assertPassed(self.hook('Bash', {'command': 'ls -la && git status --porcelain'}))

    def test_asks_for_outside_writes(self):
        self.assertAsked(self.hook('Write', {'file_path': '/tmp/x/notes.md'}), str(Path('/tmp/x/notes.md').resolve()))
        self.assertAsked(self.hook('Bash', {'command': 'git commit -m x'}), 'cannot tell: git commit -m x')
        self.assertAsked(self.hook('Bash', {'command': 'git add .'}), 'cannot tell: git add .')
        self.assertAsked(self.hook('Bash', {'command': 'cp a b'}), str(self.proj / 'b'))
        cmd = 'git commit -m "' + 'x' * 200 + '"'
        self.assertAsked(self.hook('Bash', {'command': cmd}), 'cannot tell: ' + cmd[:120])
        why = self.assertAsked(self.hook('Bash', {'command': 'git mv a b'}))
        self.assertIn(str(self.proj / 'a'), why)
        self.assertIn(str(self.proj / 'b'), why)

    def test_delegation_stays_denied(self):
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))
        self.assertDenied(self.hook('Workflow', {'script': 'x'}))

    def test_outside_write_from_subagent_or_other_session_passes(self):
        self.assertPassed(self.hook('Write', {'file_path': '/tmp/x/notes.md'}, agent_id='ag1'))
        self.assertPassed(self.hook('Write', {'file_path': '/tmp/x/notes.md'}, session_id='s-other'))
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'notes.md')}))
        self.assertPassed(self.hook('Write', {'file_path': str(self.tasks_dir / 'active-index.json')}))

    def test_approved_passes(self):
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))
        self.assertPassed(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))
        self.assertPassed(self.hook('Bash', {'command': 'rm -rf build'}))

    def test_approved_outside_write_asks(self):
        """Probe 2026-10-25: auto mode let an outside-directory Write through without a prompt; user decision:
        after G1b the hook asks for writes outside the location, agent-tasks and the declared result path."""
        out = self.root / 'outside'
        notes = self.root / 'notes'
        self.plan('# Plan\n\n## Scope summary\n- Deliverable location: `%s/out.md`\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n' % notes)
        (self.task / 'scope.md').write_text('## Deliverable format\n- Save path: `%s/sub/`\n' % (self.root / 'res'), encoding='utf-8')
        self.assertPassed(self.hook('Write', {'file_path': str(self.proj / 'src/a.py'), 'content': 'x'}))
        self.assertPassed(self.hook('Write', {'file_path': str(self.tasks_dir / 'projects.txt'), 'content': 'x'}))
        self.assertPassed(self.hook('Write', {'file_path': str(notes / 'out.md'), 'content': 'x'}))
        self.assertPassed(self.hook('Bash', {'command': f'cp a.md {self.root}/res/sub/a.md'}))
        for tool, ti in (('Write', {'file_path': str(out / 'x.md'), 'content': 'x'}),
                         ('Edit', {'file_path': str(notes / 'other.md')}),
                         ('Bash', {'command': f'cp a.md {out}/x.md'})):
            with self.subTest(tool=tool):
                r = self.hook(tool, ti)
                self.assertEqual(r.returncode, 0, r.stderr)
                o = json.loads(r.stdout)['hookSpecificOutput']
                self.assertEqual(o['permissionDecision'], 'ask')
                self.assertIn('outside the task location', o['permissionDecisionReason'])

    def test_approved_report_folder_passes_unasked(self):
        """The gate-report copy folder is a place of its own; a sibling folder still asks."""
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        dest = self.reports / 'x.md'
        self.assertPassed(self.hook('Write', {'file_path': str(dest), 'content': 'x'}))
        self.assertPassed(self.hook('Bash', {'command': f'mkdir -p {self.reports}'}))
        self.assertPassed(self.hook('Bash', {'command': f'cp a.md {dest}'}))
        script = L4 / 'scripts' / 'gate-report.py'
        self.assertPassed(self.hook('Bash', {'command': f'python3 "{script}" copy'}))
        sibling = self.reports.parent / 'data' / 'x.md'
        r = self.hook('Write', {'file_path': str(sibling), 'content': 'x'})
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual(o['permissionDecision'], 'ask')
        self.assertIn('outside the task location', o['permissionDecisionReason'])
        self.assertIn(str(sibling), o['permissionDecisionReason'])

    def test_report_folder_before_approval_still_denied(self):
        self.assertAsked(self.hook('Write', {'file_path': str(self.reports / 'x.md'), 'content': 'x'}), str(self.reports / 'x.md'))
        self.assertAsked(self.hook('Bash', {'command': f'cp a.md {self.reports}/x.md'}), str(self.reports / 'x.md'))

    def test_approved_line_elsewhere_does_not_count(self):
        self.plan('# Plan\n\n- Approved 2026-10-25 10:00 G1b\n\n## Approval\n\n## Notes\n')
        self.assertAsked(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))

    def test_cleared_approval_blocks_again(self):
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))
        self.plan('# Plan (rev 2)\n\n## Approval\n')
        self.assertAsked(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))

    def test_found_via_active_index(self):
        run = self.root / 'elsewhere'
        run.mkdir()
        (self.tasks_dir / 'active-index.json').write_text(json.dumps({str(run): str(self.proj)}))
        self.assertAsked(self.hook('Write', {'file_path': str(run / 'x.md')}, cwd=run))
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'scope.md')}, cwd=run))

    def test_missing_task_folder_warns(self):
        (self.task / '..' / '.active').resolve().write_text(f'task: 261025-gone\nphase: 1\nsession: s-test\nstarted: x\n')
        r = self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn('261025-gone', out['systemMessage'])
        self.assertNotIn('hookSpecificOutput', out)

    def setting_env(self, data):
        """Env with only the plugin setting (what a plugin hook gets): no MA_* overrides."""
        env = {k: '' for k in os.environ if k.startswith('MA_') and k != 'MA_TASK_DIR'}   # run_script merges os.environ; empty = not set
        env.update({k: '' for k in ('MA_TASKS_DIR', 'MA_PROJECTS_FILE', 'MA_FEEDBACK_FILE', 'MA_GATE_REPORT_DIR')})
        return dict(env, CLAUDE_PLUGIN_OPTION_DATA_DIR=str(data))

    def test_other_session_passes(self):
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}, session_id='s-other'))
        self.assertAsked(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}, session_id='s-test'))

    def test_subagent_call_passes(self):
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}, agent_id='ag1'))

    def test_missing_session_still_applies(self):
        (records(self.proj) / '.active').write_text(f'task: {TASK}\nphase: 1\nsession: \nstarted: x\n')
        self.assertAsked(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}, session_id='s-other'))
        (records(self.proj) / '.active').write_text(f'task: {TASK}\nphase: 1\nsession: s-test\nstarted: x\n')
        r = run_hook('plan-approved-check.py', None, {'tool_name': 'Edit', 'tool_input': {'file_path': str(self.proj / 'src/a.py')}},
                     self.proj, env=self.env)
        self.assertAsked(r)

    def test_broken_active_warns_before_session_compare(self):
        (records(self.proj) / '.active').write_text('phase: 1\nsession: s-test\n')
        r = self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}, session_id='s-other')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('no `task:` line', json.loads(r.stdout)['systemMessage'])

    def layout_hook(self, proj, tool, tool_input, env=None):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': tool_input, 'session_id': 's-test'}
        return run_hook('plan-approved-check.py', None, payload, proj, env=dict(self.env, **(env or {})),
                        drop=('MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_TASK_DIR') if not env else ('MA_TASK_DIR',))

    def test_default_layout_reads_only_the_default_folder(self):
        proj = self.root / 'dflt'
        with clean_task_env():
            task = make_task(proj, task=TASK)
        self.assertPassed(self.layout_hook(proj, 'Write', {'file_path': str(task / 'plan.md')}))
        self.assertAsked(self.layout_hook(proj, 'Write', {'file_path': str(proj / 'src/a.py')}))
        only_old = self.root / 'old-only'
        with clean_task_env():
            make_task(only_old, task=TASK, sub='docs/agent')
        self.assertPassed(self.layout_hook(only_old, 'Write', {'file_path': str(only_old / 'src/a.py')}))

    def test_setting_selects_the_former_layout(self):
        env = {'CLAUDE_PLUGIN_OPTION_TASK_DIR': 'docs/agent'}
        proj = self.root / 'former'
        with clean_task_env():
            task = make_task(proj, task=TASK, sub='docs/agent')
            make_task(self.root / 'new-only', task=TASK)
        self.assertPassed(self.layout_hook(proj, 'Write', {'file_path': str(task / 'plan.md')}, env))
        self.assertAsked(self.layout_hook(proj, 'Write', {'file_path': str(proj / 'src/a.py')}, env))
        self.assertPassed(self.layout_hook(self.root / 'new-only', 'Write',
                                           {'file_path': str(self.root / 'new-only' / 'src/a.py')}, env))

    def test_link_layout_passes_through_both_names(self):
        proj = self.root / 'linked'
        with clean_task_env():
            make_task(proj, task=TASK, sub='docs/agent')
        (proj / '.my-agent').symlink_to('docs/agent')
        for base in ('.my-agent', 'docs/agent'):
            with self.subTest(base=base):
                self.assertPassed(self.layout_hook(proj, 'Write', {'file_path': str(proj / base / TASK / 'plan.md')}))

    def test_no_active_anywhere_with_setting_only(self):
        other = self.root / 'other'
        (other / '.git').mkdir(parents=True)
        data = self.root / 'empty-data'
        data.mkdir()
        self.assertPassed(self.hook('Write', {'file_path': str(other / 'a.py')}, cwd=other, env=self.setting_env(data)))

    def test_setting_data_dir_write_rules(self):
        data = self.root / 'setting-data'
        data.mkdir()
        env = self.setting_env(data)
        sib = self.root / 'setting-data-sibling' / 'x.md'
        self.assertPassed(self.hook('Write', {'file_path': str(data / 'projects.txt')}, env=env))
        self.assertAsked(self.hook('Write', {'file_path': str(sib)}, env=env), str(sib))
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        r = self.hook('Write', {'file_path': str(data / 'gate-report' / 'x.md')}, env=env)
        self.assertPassed(r)
        r = self.hook('Write', {'file_path': str(sib)}, env=env)
        self.assertEqual(json.loads(r.stdout)['hookSpecificOutput']['permissionDecision'], 'ask')

    def test_script_error_exits_nonzero(self):
        r = run_hook('plan-approved-check.py', None, 'not json', self.proj, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()

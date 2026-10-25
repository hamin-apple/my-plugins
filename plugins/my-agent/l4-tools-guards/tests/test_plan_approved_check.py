"""plan-approved-check.py: the G1b hard gate (architecture 4.4 "G1b 하드 게이트")."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_task, run_hook

TASK = '261025-probe-task'


class PlanApprovedCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.proj = self.root / 'proj'
        self.task = make_task(self.proj, task=TASK)
        self.tasks_dir = self.root / 'agent-tasks'
        self.tasks_dir.mkdir()
        self.env = {'MA_TASKS_DIR': str(self.tasks_dir)}

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, tool, tool_input, cwd=None):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': tool_input}
        return run_hook('plan-approved-check.py', None, payload, cwd or self.proj, env=self.env)

    def assertDenied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)['hookSpecificOutput']
        self.assertEqual(out['hookEventName'], 'PreToolUse')
        self.assertEqual(out['permissionDecision'], 'deny')
        self.assertIn(TASK, out['permissionDecisionReason'])
        self.assertIn('G1b', out['permissionDecisionReason'])

    def assertPassed(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '')

    def plan(self, text):
        (self.task / 'plan.md').write_text(text, encoding='utf-8')

    def test_not_applicable_is_silent(self):
        other = self.root / 'other'
        (other / '.git').mkdir(parents=True)
        self.assertPassed(self.hook('Edit', {'file_path': str(other / 'a.py')}, cwd=other))
        self.assertPassed(self.hook('Workflow', {'script': 'x'}, cwd=other))

    def test_define_phase_blocks_write(self):
        self.assertDenied(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))
        self.assertDenied(self.hook('Write', {'file_path': str(self.proj / 'README.md')}))
        self.assertDenied(self.hook('NotebookEdit', {'notebook_path': str(self.proj / 'n.ipynb')}))

    def test_define_phase_allows_task_folder_write(self):
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'explore.md')}))
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'docs/agent/.active')}))

    def test_allows_index_and_projects(self):
        for name in ('active-index.json', 'projects.txt'):
            self.assertPassed(self.hook('Write', {'file_path': str(self.tasks_dir / name)}))
        self.assertDenied(self.hook('Write', {'file_path': str(self.tasks_dir / 'monitor.json')}))
        projects = self.tasks_dir / 'projects.txt'
        self.assertPassed(self.hook('Bash', {'command': f'mkdir -p {self.tasks_dir} && echo /p >> {projects}'}))
        self.assertDenied(self.hook('Bash', {'command': f'mkdir -p {self.tasks_dir}/x'}))

    def test_allowlist(self):
        for agent in ('my-agent:explorer', 'my-agent:architect', 'my-agent:plan-reviewer'):
            self.assertPassed(self.hook('Agent', {'subagent_type': agent, 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:coder', 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'general-purpose', 'prompt': 'x'}))
        self.assertDenied(self.hook('Agent', {'subagent_type': 'my-agent:writer', 'prompt': 'x'}))
        self.plan('# Plan\n\n## Prototype\n\nPrototype: requested\n\n## Approval\n')
        self.assertPassed(self.hook('Agent', {'subagent_type': 'my-agent:writer', 'prompt': 'x'}))

    def test_workflow_denied(self):
        self.assertDenied(self.hook('Workflow', {'script': 'x'}))

    def test_bash_patterns(self):
        self.assertDenied(self.hook('Bash', {'command': 'rm -rf src'}))
        self.assertDenied(self.hook('Bash', {'command': 'git checkout -- a'}))
        self.assertDenied(self.hook('Bash', {'command': 'echo x > "$F"'}))
        self.assertPassed(self.hook('Bash', {'command': f'mkdir -p docs/agent/{TASK}/work'}))
        self.assertPassed(self.hook('Bash', {'command': f'echo "{self.proj}" >> {self.tasks_dir}/projects.txt'}))
        self.assertPassed(self.hook('Bash', {'command': 'ls -la && git status --porcelain'}))

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
        self.plan('# Plan\n\n## 범위 요약\n- 결과물 위치: `%s/out.md`\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n' % notes)
        (self.task / 'scope.md').write_text('## 결과물 형식\n- 저장 경로: `%s/sub/`\n' % (self.root / 'res'), encoding='utf-8')
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
                self.assertIn('작업 위치 밖', o['permissionDecisionReason'])

    def test_approved_line_elsewhere_does_not_count(self):
        self.plan('# Plan\n\n- Approved 2026-10-25 10:00 G1b\n\n## Approval\n\n## Notes\n')
        self.assertDenied(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))

    def test_cleared_approval_blocks_again(self):
        self.plan('# Plan\n\n## Approval\n\n- Approved 2026-10-25 10:00 G1b\n')
        self.assertPassed(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))
        self.plan('# Plan (rev 2)\n\n## Approval\n')
        self.assertDenied(self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')}))

    def test_found_via_active_index(self):
        run = self.root / 'elsewhere'
        run.mkdir()
        (self.tasks_dir / 'active-index.json').write_text(json.dumps({str(run): str(self.proj)}))
        self.assertDenied(self.hook('Write', {'file_path': str(run / 'x.md')}, cwd=run))
        self.assertPassed(self.hook('Write', {'file_path': str(self.task / 'scope.md')}, cwd=run))

    def test_missing_task_folder_warns(self):
        (self.task / '..' / '.active').resolve().write_text(f'task: 261025-gone\nphase: 1\nsession: s\nstarted: x\n')
        r = self.hook('Edit', {'file_path': str(self.proj / 'src/a.py')})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn('261025-gone', out['systemMessage'])
        self.assertNotIn('hookSpecificOutput', out)

    def test_script_error_exits_nonzero(self):
        r = run_hook('plan-approved-check.py', None, 'not json', self.proj, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()

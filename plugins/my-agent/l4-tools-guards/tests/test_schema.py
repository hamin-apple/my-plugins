"""ma_schema is the one source of shared words: definitions write them, parsers read them (handoff C3, C5, A1)."""
import importlib.util
import json
import unittest
from pathlib import Path

from helpers import L4, REPO, events  # noqa: F401  (helpers puts lib/ and monitor/ on sys.path)
import ma_logline
import ma_schema
from monitor import events as monitor_events
from monitor.events import build_events
from monitor.runlog import parse_line

AGENTS_DIR = {'L2': REPO / 'l2-design-judge' / 'agents', 'L3': REPO / 'l3-workers' / 'agents'}


def definition(name):
    return (AGENTS_DIR[ma_schema.AGENTS[name]] / f'{name}.md').read_text(encoding='utf-8')


def hook_module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), L4 / 'hooks' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SchemaTest(unittest.TestCase):
    def test_agents_match_manifest(self):
        manifest = json.loads((REPO / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(Path(a).stem for a in manifest['agents']), sorted(ma_schema.AGENTS))
        self.assertLessEqual(set(ma_schema.UNIT_AGENTS) | set(ma_schema.BEFORE_APPROVAL), set(ma_schema.AGENTS))
        self.assertEqual(monitor_events.WORKERS, set(ma_schema.UNIT_AGENTS))

    def test_scope_guard_has_rules_for_every_agent(self):
        guard = hook_module('scope-guard')
        active = type('A', (), {'location': Path('/p'), 'task_dir': Path('/p/docs/agent/t')})()
        for name in ma_schema.AGENTS:
            with self.subTest(agent=name):
                self.assertIsNotNone(guard.rules(name, active, Path('/p')))
        self.assertIsNone(guard.rules('nobody', active, Path('/p')))
        self.assertEqual(set(guard.OWN_FILE), {n for n, lv in ma_schema.AGENTS.items() if lv == 'L2'})

    def test_definitions_spell_the_parsed_verdicts(self):
        """A1: what each judge is told to write first is what the hooks, scripts and monitor compare against."""
        self.assertIn(f'{ma_schema.VERIFY_PASS} | {ma_schema.VERIFY_FAIL}', definition('verifier'))
        self.assertIn(f'{ma_schema.PLAN_READY} | {ma_schema.PLAN_REVISE}', definition('plan-reviewer'))
        self.assertIn(f'{ma_schema.REVIEW_PREFIX}<n>', definition('reviewer'))
        self.assertIn(f'`{ma_schema.REVIEW_PASS}`', definition('reviewer'))
        self.assertIn(f'## {ma_schema.APPLIED_AFTER_REVIEW}', definition('reviewer'))
        for name in ('architect', 'gate-analyst', 'explorer', 'researcher', 'writer', 'coder'):
            self.assertIn(f'`{ma_schema.WORKER_DONE}` 또는 `{ma_schema.WORKER_PARTIAL} <이유>`', definition(name), name)
        plan_phase = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        self.assertIn(f'`{ma_schema.PLAN_SKIPPED} <이유>`', plan_phase)

    def test_verifier_fail_counts_in_monitor(self):
        """A1 regression: a real verifier stop line (`result="Verdict: FAIL"`) is a FAIL for the E counter."""
        lines = []
        for i in range(3):
            lines.append(ma_logline.format_line('start', [('agent', 'my-agent:verifier'), ('id', f'v{i}')]))
            lines.append(ma_logline.format_line('stop', [('id', f'v{i}'), ('result', ma_schema.VERIFY_FAIL),
                                                         ('end', 'ok')]))
        e = build_events([parse_line(l) for l in lines])
        self.assertEqual((e.vfail, e.vfail_max), (3, 3))

    def test_one_line_parser(self):
        line = ma_logline.format_line('ask', [('gate', 'G3'), ('q', 'a "b" c'), ('rec', '수용')])
        self.assertEqual(ma_logline.parse_line(line), (parse_line(line).kind, parse_line(line).f))
        self.assertEqual(ma_schema.unreadable_lines(line + '\n2026-10-25 10:00:00 ask: q="x\n# heading'), [2])

    def test_sections(self):
        text = '# t\n## 완료 기준 (일반)\n1. a\n### sub\n## Approval\n- Approved 2026-10-25 10:00 G1b\n'
        self.assertEqual(ma_schema.section_lines(text, '완료 기준'), ['1. a', '### sub'])
        self.assertEqual(ma_schema.approved_at(text), '2026-10-25 10:00')
        self.assertIsNone(ma_schema.section_lines(text, 'Revisions'))
        self.assertEqual(ma_schema.units('## 작업 단위\n### u1 a\n- Status: done\n### u12 b\n- x\n## Approval\n'),
                         [('u1', 'a', 'done'), ('u12', 'b', None)])
        self.assertEqual(ma_schema.unit_of_prompt('작업 단위: u3 cli\n…'), 'u3')
        self.assertIsNone(ma_schema.unit_of_prompt('see 작업 단위: u3'))


if __name__ == '__main__':
    unittest.main()

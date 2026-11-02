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
        active = type('A', (), {'location': Path('/p'), 'task_dir': Path('/p/.my-agent/t')})()
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
            self.assertIn(f'`{ma_schema.WORKER_DONE}` or `{ma_schema.WORKER_PARTIAL} <reason>`', definition(name), name)
        plan_phase = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        self.assertIn(f'`{ma_schema.PLAN_SKIPPED} <reason>`', plan_phase)

    def test_verifier_fail_counts_in_monitor(self):
        """A1 regression: a real verifier stop line (`result="Verdict: FAIL"`) is a FAIL for the E counter."""
        lines = []
        for i in range(3):
            lines.append(ma_logline.format_line('start', [('agent', 'my-agent:verifier'), ('id', f'v{i}')]))
            lines.append(ma_logline.format_line('stop', [('id', f'v{i}'), ('result', ma_schema.VERIFY_FAIL),
                                                         ('end', 'ok')]))
        e = build_events([parse_line(l) for l in lines])
        self.assertEqual((e.vfail, e.vfail_max), (3, 3))

    def test_guard_kind(self):
        self.assertEqual(ma_schema.GUARD, 'guard')
        self.assertEqual(ma_schema.GUARD_FIELDS, ('hook', 'agent', 'id', 'tool', 'decision', 'why', 'cwd'))
        self.assertTrue(ma_logline.is_hook_line('guard', {}))
        line = ma_logline.guard_line('scope-guard', 'my-agent:coder', 'a1', 'Bash', 'deny', 'scope-guard: Outside "x"')
        kind, fields = ma_logline.parse_line(line)
        self.assertEqual(kind, 'guard')
        self.assertEqual(list(fields), list(ma_schema.GUARD_FIELDS))
        self.assertEqual(fields['why'], 'scope-guard: Outside "x"')
        self.assertEqual(fields['cwd'], '-')   # the trailing cwd defaults to `-`
        line = ma_logline.guard_line('scope-guard', 'my-agent:coder', 'a1', 'Bash', 'deny', 'why', '/a b/c')
        self.assertEqual(ma_logline.parse_line(line)[1]['cwd'], '/a b/c')

    def test_old_six_field_guard_line_parses(self):
        line = '2026-11-01 02:40:27 guard: hook=scope-guard agent=my-agent:coder id=a1 tool=Bash decision=deny why="x y"'
        kind, fields = ma_logline.parse_line(line)
        self.assertEqual(kind, 'guard')
        self.assertEqual(list(fields), list(ma_schema.GUARD_FIELDS[:6]))
        self.assertEqual(fields['why'], 'x y')

    def test_one_line_parser(self):
        line = ma_logline.format_line('ask', [('gate', 'G3'), ('q', 'a "b" c'), ('rec', 'Accept')])
        self.assertEqual(ma_logline.parse_line(line), (parse_line(line).kind, parse_line(line).f))
        self.assertEqual(ma_schema.unreadable_lines(line + '\n2026-10-25 10:00:00 ask: q="x\n# heading'), [2])

    def test_sections(self):
        text = '# t\n## Completion criteria (general)\n1. a\n### sub\n## Approval\n- Approved 2026-10-25 10:00 G1b\n'
        self.assertEqual(ma_schema.section_lines(text, 'Completion criteria'), ['1. a', '### sub'])
        self.assertEqual(ma_schema.approved_at(text), '2026-10-25 10:00')
        self.assertIsNone(ma_schema.section_lines(text, 'Revisions'))
        self.assertEqual(ma_schema.units('## Work units\n### u1 a\n- Status: done\n### u12 b\n- x\n## Approval\n'),
                         [('u1', 'a', 'done'), ('u12', 'b', None)])
        self.assertEqual(ma_schema.unit_of_prompt('Work unit: u3 cli\n…'), 'u3')
        self.assertIsNone(ma_schema.unit_of_prompt('see Work unit: u3'))


class ReportParsersTest(unittest.TestCase):
    def test_criteria_and_purpose(self):
        text = ('## Purpose and users\n\nClose it.\nSecond line.\n\n## Completion criteria\n'
                '1. First thing works. More. [check: command]\n2. Second\n   continued. [check: file]\n3. No tag\n## Hard\n')
        self.assertEqual(ma_schema.criteria(text), [(1, 'First thing works. More.', 'command'),
                                                    (2, 'Second continued.', 'file'), (3, 'No tag', None)])
        self.assertEqual(ma_schema.purpose(text), 'Close it. Second line.')
        self.assertEqual(ma_schema.purpose('## Scope summary\nA.\n'), 'A.')
        for empty in (None, '', 'no sections'):
            self.assertEqual(ma_schema.criteria(empty), [])
            self.assertIsNone(ma_schema.purpose(empty))

    def test_verify(self):
        text = 'Verdict: FAIL\nRun: 2\n- 1. PASS a.py:3 ok\n- 2. FAIL broken\n## Commands run\n- 3. PASS late\n'
        self.assertEqual(ma_schema.verify_rows(text), [(1, 'PASS', 'a.py:3 ok'), (2, 'FAIL', 'broken')])
        self.assertEqual(ma_schema.run_number(text), 2)
        self.assertEqual((ma_schema.verify_rows(None), ma_schema.run_number('')), ([], None))

    def test_review(self):
        text = ('BLOCKER 0\n\n## Findings\n- SHOULD-FIX /p/SKILL.md:104 glued bullets → fix\n'
                '- NITPICK /p/lib/a.py:36 copy (new)\n- NITPICK /p/lib/b.py:5 other (carried)\n\n'
                '## Applied after review\n\n- SKILL.md:104 line break restored (plugins/x/SKILL.md)\n')
        self.assertEqual(ma_schema.review_blockers(text), 0)
        found = ma_schema.review_findings(text)
        self.assertEqual([(f[0], f[1], f[3]) for f in found],
                         [('SHOULD-FIX', '/p/SKILL.md:104', None), ('NITPICK', '/p/lib/a.py:36', 'new'),
                          ('NITPICK', '/p/lib/b.py:5', 'carried')])
        self.assertEqual(found[1][2], 'copy')
        applied = ma_schema.review_applied(text)
        self.assertEqual([ma_schema.finding_applied(f[1], applied) for f in found], [True, False, False])
        self.assertTrue(ma_schema.finding_applied('/p/q/gate.py:9', ['docstring (q/gate.py)']))
        self.assertEqual((ma_schema.review_blockers(None), ma_schema.review_findings(''), ma_schema.review_applied(None)),
                         (None, [], []))

    def test_plan_review(self):
        text = ('REVISE\nRun: 1\n\n## Findings\n- BLOCKER plan.md:1 a\n- SHOULD-FIX plan.md:2 b\n- SHOULD-FIX x c\n'
                '- NITPICK y d\n\n## Run 1 resolution\n- R1 BLOCKER done\n')
        self.assertEqual(ma_schema.plan_review(text), {'verdict': 'REVISE', 'run': 1, 'blockers': 1, 'should_fix': 2, 'nitpicks': 1})
        self.assertIsNone(ma_schema.plan_review(''))
        self.assertIsNone(ma_schema.plan_review(None))

    def test_gate_report(self):
        text = ('# G\n\n## Summary\n1. one\n2. two\n\n## Tendencies\n- (weak) x\n\n## Suggested improvements\n'
                '- [L1, weak] First.\n- [L3, clear] Second.\n')
        self.assertEqual(ma_schema.gate_report_summary(text), ['one', 'two'])
        self.assertEqual(ma_schema.gate_report_improvements(text), [('L1', 'weak', 'First.'), ('L3', 'clear', 'Second.')])
        self.assertEqual((ma_schema.gate_report_summary(None), ma_schema.gate_report_improvements('')), ([], []))

    def test_unit_details_and_criterion_numbers(self):
        line = '1, 6, 7; the SKILL.md parts of 2 (…), 4 (… item 10 …) and 8 (…)'
        self.assertEqual(ma_schema.criterion_numbers(line), [1, 2, 4, 6, 7, 8])
        text = ('## Work units\n### u1 First\n- Agent: coder\n- Files to change: `P/a.md`, `P/b.py`\n'
                '- Parallel group: group 1 (worktree)\n- Completion criteria: ' + line + '\n- Status: done\n'
                '### u2 Second\n- Files to change:\n  - `P/c.py`: new\n  - `P/d.py`\n- Completion criteria: 3\n'
                '- Status: pending\n## Approval\n')
        units = ma_schema.unit_details(text)
        self.assertEqual(units[0], {'id': 'u1', 'name': 'First', 'status': 'done', 'group': 'group 1 (worktree)',
                                    'files': ['P/a.md', 'P/b.py'], 'criteria': [1, 2, 4, 6, 7, 8]})
        self.assertEqual((units[1]['files'], units[1]['criteria'], units[1]['group']), (['P/c.py', 'P/d.py'], [3], None))
        self.assertEqual((ma_schema.unit_details(None), ma_schema.criterion_numbers(None)), ([], []))

    def test_background_purpose_labeled(self):
        text = ('# Scope\n\n## Purpose and users\n\nBackground: The export command writes one file per run\n'
                'and overwrites the last one.\n\nPurpose: Keep every export by adding a dated name,\nand ship it as 1.4.0.\n\n'
                'Users: the person running exports; the release script.\n\n## Other\nx\n')
        self.assertEqual(ma_schema.background_purpose(text),
                         ('The export command writes one file per run and overwrites the last one.',
                          'Keep every export by adding a dated name, and ship it as 1.4.0.'))
        only = '## Purpose and users\n\nPurpose: Only this.\n'
        self.assertEqual(ma_schema.background_purpose(only), (None, 'Only this.'))
        bullets = '## Purpose and users\n\n- Background: B text.\n- Purpose: P text.\n'
        self.assertEqual(ma_schema.background_purpose(bullets), ('B text.', 'P text.'))

    def test_background_purpose_unlabeled(self):
        text = '## Purpose and users\n\nFirst para\nwraps.\n\nSecond para.\n\nUsers: someone.\n\n## Next\n'
        self.assertEqual(ma_schema.background_purpose(text), ('First para wraps.', 'Second para.'))
        one = '## Purpose and users\n\nOnly one.\n\nUsers: someone.\n'
        self.assertEqual(ma_schema.background_purpose(one), ('Only one.', None))
        lst = '## Purpose and users\n\nIntro.\n\n1. one\n2. two\n\nUsers: x.\n'
        self.assertEqual(ma_schema.background_purpose(lst), ('Intro.', '1. one 2. two'))

    def test_background_purpose_scope_summary(self):
        text = ('# Plan: x\n\n## Scope summary\n- Purpose: Show the history.\n- Non-goals: No GUI.\n'
                '- Deliverable location: the repo.\n\n## Work units\n')
        self.assertEqual(ma_schema.background_purpose(text), (None, 'Show the history.'))

    def test_background_purpose_missing(self):
        self.assertEqual(ma_schema.background_purpose(None), (None, None))
        self.assertEqual(ma_schema.background_purpose(''), (None, None))
        self.assertEqual(ma_schema.background_purpose('## Other\nx\n'), (None, None))
        self.assertEqual(ma_schema.background_purpose('## Purpose and users\n\nUsers: x.\n'), (None, None))

    def test_section_bullets(self):
        text = ('## Non-goals\n- No change to the file format.\n- A wrapped bullet\n  that goes on.\n  - nested\n\n'
                '- Last.\n\n## Estimate\n- Subagents: 6.\n')
        self.assertEqual(ma_schema.section_bullets(text, 'Non-goals'),
                         ['No change to the file format.', 'A wrapped bullet that goes on. - nested', 'Last.'])
        self.assertEqual(ma_schema.section_bullets(text, 'Estimate'), ['Subagents: 6.'])
        self.assertEqual(ma_schema.section_bullets(text, 'Missing'), [])
        self.assertEqual(ma_schema.section_bullets(None, 'Estimate'), [])

    def test_plan_lead(self):
        self.assertEqual(ma_schema.plan_lead('# Plan: x\n\nTwo coder units:\nthe name, then the docs.\n\nSecond para.\n\n## Work units\n'),
                         'Two coder units: the name, then the docs.')
        self.assertIsNone(ma_schema.plan_lead('# Plan: x\n\n## Work units\n\nText.\n'))
        self.assertIsNone(ma_schema.plan_lead('# Plan: x\n## Work units\n'))
        self.assertEqual(ma_schema.plan_lead('# Plan: x\n\nProfile: dev. Completion criteria 1-3 are in scope.md.\n\n## A\n'),
                         'Profile: dev. Completion criteria 1-3 are in scope.md.')
        self.assertIsNone(ma_schema.plan_lead(None))
        self.assertIsNone(ma_schema.plan_lead(''))

    def test_models_table(self):
        text = ('## Models\nPreset: standard (definition values)\n\n| Agent | Model | Effort | Note |\n|---|---|---|---|\n'
                '| architect | opus | high | |\n| coder | sonnet | medium | cheaper here |\n| newbie | haiku | low | |\n\n'
                'Recommendation: economy fits this plan.\n\n## Approval\n')
        self.assertEqual(ma_schema.models_table(text), {
            'preset': 'standard (definition values)', 'recommendation': 'economy fits this plan.',
            'rows': [{'agent': 'architect', 'model': 'opus', 'effort': 'high', 'note': ''},
                     {'agent': 'coder', 'model': 'sonnet', 'effort': 'medium', 'note': 'cheaper here'},
                     {'agent': 'newbie', 'model': 'haiku', 'effort': 'low', 'note': ''}]})
        bare = ma_schema.models_table('## Models\nPreset: economy\n')
        self.assertEqual(bare, {'preset': 'economy', 'rows': [], 'recommendation': None})
        self.assertIsNone(ma_schema.models_table('## Approval\nx\n'))
        self.assertIsNone(ma_schema.models_table(None))

    def test_verify_verdict(self):
        self.assertEqual(ma_schema.verify_verdict('\nVerdict: ALL PASS\nRun: 1\n'), 'ALL PASS')
        self.assertEqual(ma_schema.verify_verdict('Verdict: FAIL\n- 1. FAIL x\n'), 'FAIL')
        self.assertIsNone(ma_schema.verify_verdict('Something else\nVerdict: FAIL\n'))
        self.assertIsNone(ma_schema.verify_verdict(''))
        self.assertIsNone(ma_schema.verify_verdict(None))

    def test_plan_review_decisions(self):
        text = ('REVISE\nRun: 1\n\n## Findings\n- BLOCKER plan.md:1 a\n\n## Decisions\n'
                '- BLOCKER plan.md:1 fix the thing → applied by L1\n'
                '- SHOULD-FIX plan.md:259 pin updated → applied by architect\n'
                '- NITPICK plan.md:60 skip it → declined\n'
                '- NITPICK plan.md:61 no outcome\n\n## Other\n- BLOCKER x y → declined\n')
        self.assertEqual(ma_schema.plan_review_decisions(text), [
            ('BLOCKER', 'plan.md:1', 'applied'), ('SHOULD-FIX', 'plan.md:259', 'applied'),
            ('NITPICK', 'plan.md:60', 'declined'), ('NITPICK', 'plan.md:61', None)])
        self.assertEqual((ma_schema.plan_review_decisions(None), ma_schema.plan_review_decisions('x')), ([], []))

    def test_aborted_reason(self):
        self.assertEqual(ma_schema.aborted_reason('Status: aborted 2026-11-03 10:20 person stopped it\nTask: x\n'), 'person stopped it')
        self.assertEqual(ma_schema.aborted_reason('Status: aborted 2026-11-03 10:20\n'), '')
        self.assertEqual(ma_schema.aborted_reason('Status: aborted\n'), '')
        self.assertIsNone(ma_schema.aborted_reason('Status: done\n'))
        self.assertIsNone(ma_schema.aborted_reason('Status: active\n'))
        self.assertIsNone(ma_schema.aborted_reason(None))
        self.assertIsNone(ma_schema.aborted_reason(''))

    def test_existing_parsers_unchanged(self):
        text = '## Purpose and users\n\nFirst.\nSecond line.\n\nUsers: x\n'
        self.assertEqual(ma_schema.purpose(text), 'First. Second line. Users: x')
        rv = '## Findings\n- SHOULD-FIX a.py:3 text (new)\n- NITPICK b.py:4 other\n'
        self.assertEqual(ma_schema.review_findings(rv), [('SHOULD-FIX', 'a.py:3', 'text', 'new'), ('NITPICK', 'b.py:4', 'other', None)])
        pr = 'REVISE\nRun: 2\n\n## Findings\n- BLOCKER p:1 a\n- NITPICK q b\n'
        self.assertEqual(ma_schema.plan_review(pr), {'verdict': 'REVISE', 'run': 2, 'blockers': 1, 'should_fix': 0, 'nitpicks': 1})


if __name__ == '__main__':
    unittest.main()

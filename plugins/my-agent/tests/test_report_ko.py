"""report-ko.py and the Korean copy helpers in ma_schema (SKILL.md "Gate reports", Korean copy)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script

import ma_schema

SCRIPT = L4 / 'scripts' / 'report-ko.py'

SCOPE = """# Scope: 261106-probe

## Purpose and users

Background: The report shows English only.

Purpose: Show a Korean copy.

Users: the person.

## Completion criteria

1. The copy is shown. [check: command]
2. A stale item falls back. [check: command]
"""

PLAN = """# Plan: 261106-probe

Lead.

## Work units

### u1 Copy helper
- Status: pending

### u2 Report view
- Status: pending

## Approval
"""


class KoSourcesTest(unittest.TestCase):
    def test_sources_and_sha(self):
        src = ma_schema.ko_sources(SCOPE, PLAN)
        self.assertEqual(list(src), ['background', 'purpose', 'c1', 'c2', 'u1', 'u2'])
        self.assertEqual(src['c1'], 'The copy is shown.')          # without the check tag
        self.assertEqual(src['u2'], 'Report view')
        self.assertEqual(ma_schema.text_sha('a  b\n c'), ma_schema.text_sha('a b c'))   # whitespace collapsed
        self.assertRegex(ma_schema.text_sha('x'), r'^[0-9a-f]{8}$')

    def test_general_plan_scope_summary(self):
        plan = PLAN.replace('## Work units', '## Scope summary\n\nBackground: B.\n\nPurpose: P.\n\n'
                                             '## Completion criteria\n\n1. One. [check: file]\n\n## Work units')
        src = ma_schema.ko_sources(None, plan)
        self.assertEqual(src['background'], 'B.')
        self.assertEqual(src['c1'], 'One.')

    def test_copy_reader_never_raises(self):
        self.assertEqual(ma_schema.ko_copy(None), {})
        self.assertEqual(ma_schema.ko_copy('not json'), {})
        self.assertEqual(ma_schema.ko_copy('[1, 2]'), {})
        self.assertEqual(ma_schema.ko_copy('{"items": {"c1": {"sha": "x", "ko": "가"}, "c2": "bad"}}'),
                         {'c1': {'sha': 'x', 'ko': '가'}})

    def test_current_ko(self):
        src = ma_schema.ko_sources(SCOPE, PLAN)
        items = {'c1': {'sha': ma_schema.text_sha(src['c1']), 'ko': '사본이 보인다.'},
                 'c2': {'sha': 'deadbeef', 'ko': '오래된 번역'}}
        self.assertEqual(ma_schema.ko_current(src, items), {'c1': '사본이 보인다.'})


class ReportKoScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.task = Path(self.tmp.name).resolve() / '261106-probe'
        self.task.mkdir()
        (self.task / 'scope.md').write_text(SCOPE, encoding='utf-8')
        (self.task / 'plan.md').write_text(PLAN, encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def todo(self):
        res = run_script(SCRIPT, '--task', str(self.task), 'todo')
        self.assertEqual(res.returncode, 0, res.stderr)
        body, last = res.stdout.rstrip('\n').rsplit('\n', 1)
        return json.loads(body), last

    def write_copy(self, items):
        (self.task / ma_schema.KO_COPY).write_text(json.dumps({'items': items}, ensure_ascii=False), encoding='utf-8')

    def test_new_task_lists_everything(self):
        todo, last = self.todo()
        self.assertEqual(list(todo), ['background', 'purpose', 'c1', 'c2', 'u1', 'u2'])
        self.assertEqual(todo['c2']['en'], 'A stale item falls back.')
        self.assertEqual(last, 'report-ko: 6 to translate, 0 current')
        self.assertFalse((self.task / ma_schema.KO_COPY).exists())     # todo writes nothing

    def test_matching_copy_then_edited_source(self):
        todo, _ = self.todo()
        self.write_copy({k: {'sha': v['sha'], 'ko': '번역 ' + k} for k, v in todo.items()})
        todo, last = self.todo()
        self.assertEqual(todo, {})
        self.assertEqual(last, 'report-ko: 0 to translate, 6 current')
        self.assertEqual(run_script(SCRIPT, '--task', str(self.task), 'check').returncode, 0)
        (self.task / 'scope.md').write_text(SCOPE.replace('falls back.', 'falls back to English.'), encoding='utf-8')
        (self.task / 'plan.md').write_text(PLAN.replace('## Approval', '### u3 Rules\n- Status: pending\n\n## Approval'),
                                           encoding='utf-8')
        todo, last = self.todo()
        self.assertEqual(list(todo), ['c2', 'u3'])
        self.assertEqual(last, 'report-ko: 2 to translate, 5 current')   # c2 stale, u3 new
        res = run_script(SCRIPT, '--task', str(self.task), 'check')
        self.assertEqual((res.returncode, res.stdout.strip()), (1, 'report-ko: 2 to translate, 5 current'))

    def test_broken_copy_reads_as_none(self):
        (self.task / ma_schema.KO_COPY).write_text('{broken', encoding='utf-8')
        _todo, last = self.todo()
        self.assertEqual(last, 'report-ko: 6 to translate, 0 current')

    def test_bad_arguments(self):
        self.assertEqual(run_script(SCRIPT, '--task', str(self.task), 'nope').returncode, 2)
        self.assertEqual(run_script(SCRIPT, '--task', str(self.task / 'missing'), 'todo').returncode, 2)


if __name__ == '__main__':
    unittest.main()

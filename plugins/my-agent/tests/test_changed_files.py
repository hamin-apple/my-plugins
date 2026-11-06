"""changed-files.py: the changed-file map L1 hands to the verifier and the reviewer (accept.md step 7)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script

import ma_schema

SCRIPT = L4 / 'scripts' / 'changed-files.py'
TASK = '261106-probe-task'

PLAN = """# Plan: 261106-probe-task

Lead.

## Work units

### u1 Parser
- Agent: my-agent:coder
- Files to change: `plugins/demo/lib/parser.py`, new `plugins/demo/tests/test_parser.py`
- Parallel group: group 1
- Completion criteria: 1, 2
- Status: done

### u2 View
- Agent: my-agent:coder
- Files to change: `web/view.html`
- Parallel group: group 1
- Completion criteria: 3
- Status: done

## Approval
"""


def git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)


class ChangedFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'proj'
        self.root.mkdir()
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 't@example.com')
        git(self.root, 'config', 'user.name', 't')
        for rel, body in (('plugins/demo/lib/parser.py', 'a = 1\n'), ('web/view.html', '<p>x</p>\n'),
                          ('plugins/demo/tests/helpers.py', 'h = 1\n'), ('README.md', 'r\n')):
            self.write(rel, body)
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '-m', 'base')
        self.task = self.root / '.my-agent' / TASK
        self.task.mkdir(parents=True)
        (self.task / 'intake.md').write_text(f'Status: active\nLocation: {self.root}\nProfile: dev\nTask: {TASK}\n',
                                             encoding='utf-8')
        (self.task / 'plan.md').write_text(PLAN, encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')

    def run_cf(self, *extra):
        return run_script(SCRIPT, '--task', str(self.task), *extra)

    def table(self):
        text = (self.task / ma_schema.CHANGED_FILES).read_text(encoding='utf-8')
        rows, rejudge = ma_schema.changed_files_rows(text)
        return text, {r['file']: r for r in rows}, rejudge

    def test_first_run_maps_units_and_lists_unmapped(self):
        self.write('plugins/demo/lib/parser.py', 'a = 2\n')
        self.write('plugins/demo/tests/test_parser.py', 'def test(): pass\n')   # untracked, named by u1
        self.write('web/view.html', '<p>y</p>\n')
        self.write('README.md', 'r2\n')
        (self.task / 'notes.md').write_text('task record\n', encoding='utf-8')
        res = self.run_cf()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), 'changed-files: 4 files, 1 unmapped')
        text, rows, rejudge = self.table()
        self.assertEqual(rejudge, 'all')
        self.assertIn('Previous: none', text)
        self.assertEqual(rows['plugins/demo/lib/parser.py']['units'], 'u1')
        self.assertEqual(rows['plugins/demo/lib/parser.py']['criteria'], '1, 2')
        self.assertEqual(rows['plugins/demo/tests/test_parser.py']['units'], 'u1')
        self.assertEqual(rows['web/view.html']['criteria'], '3')
        self.assertEqual(rows['README.md']['units'], 'unmapped')
        self.assertEqual(rows['README.md']['criteria'], 'all')
        self.assertFalse(any(f.startswith('.my-agent/') for f in rows))   # the task records are left out
        self.assertRegex(rows['web/view.html']['fingerprint'], r'^[0-9a-f]{12}$')
        self.assertEqual(rows['web/view.html']['since'], '-')

    def first_then_archive(self):
        self.write('plugins/demo/lib/parser.py', 'a = 2\n')
        self.write('web/view.html', '<p>y</p>\n')
        self.assertEqual(self.run_cf().returncode, 0)
        arch = self.task / 'archive' / '261106-120000-run1'
        arch.mkdir(parents=True)
        (arch / ma_schema.CHANGED_FILES).write_text((self.task / ma_schema.CHANGED_FILES).read_text(encoding='utf-8'),
                                                     encoding='utf-8')
        (arch / 'verify.md').write_text('Verdict: FAIL\nRun: 1\n- 3. FAIL x\n', encoding='utf-8')
        return arch

    def test_previous_marks_changed_and_limits_rejudge(self):
        arch = self.first_then_archive()
        self.write('web/view.html', '<p>z</p>\n')
        res = self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), 'changed-files: 2 files, 0 unmapped, 1 changed since Run 1')
        text, rows, rejudge = self.table()
        self.assertEqual(rejudge, '3')
        self.assertEqual(rows['web/view.html']['since'], 'changed')
        self.assertEqual(rows['plugins/demo/lib/parser.py']['since'], 'same')
        self.assertIn('(Run 1)', text)

    def test_shared_helper_change_rejudges_all(self):
        arch = self.first_then_archive()
        self.write('plugins/demo/tests/helpers.py', 'h = 2\n')
        res = self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        self.assertEqual(res.returncode, 0, res.stderr)
        _text, rows, rejudge = self.table()
        self.assertEqual(rows['plugins/demo/tests/helpers.py']['units'], 'shared')
        self.assertEqual(rows['plugins/demo/tests/helpers.py']['criteria'], 'all')
        self.assertEqual(rejudge, 'all')

    def test_unmapped_change_since_previous_rejudges_all(self):
        arch = self.first_then_archive()
        self.write('README.md', 'r3\n')
        self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        self.assertEqual(self.table()[2], 'all')

    def test_deleted_file(self):
        arch = self.first_then_archive()
        (self.root / 'web' / 'view.html').unlink()
        self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        _text, rows, rejudge = self.table()
        self.assertEqual(rows['web/view.html']['fingerprint'], 'deleted')
        self.assertEqual(rows['web/view.html']['since'], 'changed')
        self.assertEqual(rejudge, '3')

    def test_reverted_file_counts_as_changed(self):
        """A file in the previous map that is no longer changed (reverted) is touched by the fix."""
        arch = self.first_then_archive()
        git(self.root, 'checkout', '--', 'web/view.html')
        res = self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        _text, rows, rejudge = self.table()
        self.assertEqual(rows['web/view.html']['fingerprint'], 'reverted')
        self.assertEqual(rows['web/view.html']['since'], 'changed')
        self.assertEqual(rejudge, '3')
        self.assertIn('1 changed since Run 1', res.stdout)

    def test_reverted_row_is_listed_once(self):
        """The map after the one that marked a file `reverted` leaves it out, so the map does not grow with it."""
        arch = self.first_then_archive()
        git(self.root, 'checkout', '--', 'web/view.html')
        self.run_cf('--previous', str(arch / ma_schema.CHANGED_FILES))
        arch2 = self.task / 'archive' / '261106-130000-run2'
        arch2.mkdir(parents=True)
        (arch2 / ma_schema.CHANGED_FILES).write_text((self.task / ma_schema.CHANGED_FILES).read_text(encoding='utf-8'),
                                                      encoding='utf-8')
        (arch2 / 'verify.md').write_text('Verdict: FAIL\nRun: 2\n- 1. FAIL x\n', encoding='utf-8')
        res = self.run_cf('--previous', str(arch2 / ma_schema.CHANGED_FILES))
        self.assertEqual(res.returncode, 0, res.stderr)
        _text, rows, rejudge = self.table()
        self.assertNotIn('web/view.html', rows)
        self.assertEqual(rows['plugins/demo/lib/parser.py']['since'], 'same')
        self.assertEqual(rejudge, 'none')
        self.assertEqual(res.stdout.strip(), 'changed-files: 1 files, 0 unmapped, 0 changed since Run 2')

    def test_non_ascii_path_is_not_quoted(self):
        """git quotes non-ASCII paths by default (core.quotepath); the map keeps the real name and maps it."""
        (self.task / 'plan.md').write_text(PLAN.replace('`web/view.html`', '`web/보기.html`'), encoding='utf-8')
        self.write('web/보기.html', '<p>k</p>\n')
        res = self.run_cf()
        self.assertEqual(res.returncode, 0, res.stderr)
        _text, rows, _r = self.table()
        self.assertEqual(rows['web/보기.html']['units'], 'u2')
        self.assertNotEqual(rows['web/보기.html']['fingerprint'], 'deleted')

    def test_missing_plan_and_previous(self):
        (self.task / 'plan.md').unlink()
        res = self.run_cf()
        self.assertEqual(res.returncode, 1)
        self.assertIn('changed-files: ', res.stdout)
        (self.task / 'plan.md').write_text(PLAN, encoding='utf-8')
        res = self.run_cf('--previous', str(self.task / 'nope.md'))
        self.assertEqual(res.returncode, 2)

    def test_not_a_git_location_lists_work_files(self):
        """A general task: the files under work/ and deliverable/, mapped by any backticked path of a unit."""
        (self.task / 'intake.md').write_text(f'Status: active\nLocation: {self.root.parent}\nProfile: general\nTask: {TASK}\n',
                                             encoding='utf-8')
        plan = PLAN.replace('`web/view.html`', f'`.my-agent/{TASK}/work/draft.md`')
        (self.task / 'plan.md').write_text(plan, encoding='utf-8')
        (self.task / 'work').mkdir()
        (self.task / 'work' / 'draft.md').write_text('d\n', encoding='utf-8')
        res = self.run_cf()
        self.assertEqual(res.returncode, 0, res.stderr)
        _text, rows, _r = self.table()
        self.assertEqual(list(rows), ['work/draft.md'])
        self.assertEqual(rows['work/draft.md']['units'], 'u2')

    def test_parser_tolerates_missing_text(self):
        self.assertEqual(ma_schema.changed_files_rows(None), ([], None))
        self.assertEqual(ma_schema.changed_files_rows(''), ([], None))


if __name__ == '__main__':
    unittest.main()

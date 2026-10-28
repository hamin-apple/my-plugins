"""ma_usage, usage-snapshot.py and archive-tasks.py (architecture 4.8.2 "Task records over time")."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from helpers import L4, make_task, run_script

import ma_usage

SNAP = L4 / 'scripts' / 'usage-snapshot.py'
ARCHIVE = L4 / 'scripts' / 'archive-tasks.py'


def entry(ts, mid, model='claude-opus-5-5', inp=10, out=5):
    stamp = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').astimezone().isoformat()
    return json.dumps({'type': 'assistant', 'timestamp': stamp,
                       'message': {'id': mid, 'model': model, 'usage': {'input_tokens': inp, 'output_tokens': out}}})


LOG = ['2026-10-01 10:00:00 step: n=1 name=Intake rev=0 session=s-1',
       '2026-10-01 10:10:00 step: n=2 name=Explore rev=0 session=s-1',
       '2026-10-01 10:20:00 answer: gate=G3 choice=Accept']


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.claude = self.root / 'claude'
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'MA_CLAUDE_PROJECTS': str(self.claude)}

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, proj='proj', task='261001-probe', status='done', log=LOG):
        d = make_task(self.root / proj, task=task)
        (d / 'intake.md').write_text(f'Status: {status}\nProfile: general\nRequest: probe\n', encoding='utf-8')
        if log is not None:
            (d / 'run-log.md').write_text('\n'.join(log) + '\n', encoding='utf-8')
        return d

    def transcript(self, *lines, session='s-1'):
        p = self.claude / '-x-proj' / f'{session}.jsonl'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')


class UsageTest(Base):
    def test_windows_end_after_last_line_when_finished(self):
        t = [datetime(2026, 10, 1, 10, m) for m in (0, 10, 20)]
        enter = [(t[0], 1, 0, 's'), (t[1], 2, 0, 's')]
        self.assertEqual(ma_usage.windows(enter, t[2], running=False)[-1][2], datetime(2026, 10, 1, 10, 20, 1))
        self.assertIsNone(ma_usage.windows(enter, t[2], running=True)[-1][2])

    def test_measure_counts_each_response_once_per_window(self):
        d = self.task()
        self.transcript(entry('2026-10-01 10:01:00', 'a'), entry('2026-10-01 10:01:00', 'a', inp=30),
                        entry('2026-10-01 10:11:00', 'b', model='claude-sonnet-5-5'),
                        entry('2026-10-01 10:30:00', 'c'))   # after the task: not counted
        sessions, missing, usage = ma_usage.measure(d, self.claude)
        self.assertEqual((sessions, missing), (['s-1'], []))
        self.assertEqual(usage[(0, 1)]['claude-opus-5-5']['input_tokens'], 30)
        self.assertEqual(list(usage[(0, 2)]), ['claude-sonnet-5-5'])
        self.assertEqual(len(usage), 2)

    def test_snapshot_round_trip(self):
        d = self.task()
        self.transcript(entry('2026-10-01 10:01:00', 'a'), entry('2026-10-01 10:11:00', 'b'))
        code, _ = ma_usage.write_snapshot(d, self.claude, datetime(2026, 10, 2))
        self.assertEqual(code, 0)
        self.assertEqual(ma_usage.read_snapshot(d), ma_usage.measure(d, self.claude)[2])
        self.assertIsNone(ma_usage.read_snapshot(self.root))


class SnapshotScriptTest(Base):
    def test_active_task(self):
        d = self.task(status='active')
        self.transcript(entry('2026-10-01 10:01:00', 'a'))
        r = run_script(SNAP, '--cwd', str(self.root / 'proj'), env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((d / ma_usage.SNAPSHOT).is_file())

    def test_no_transcript_writes_nothing_and_keeps_old(self):
        d = self.task()
        (d / ma_usage.SNAPSHOT).write_text('{"windows": []}', encoding='utf-8')
        r = run_script(SNAP, '--task-dir', str(d), env=self.env)
        self.assertEqual(r.returncode, 3)
        self.assertIn('no transcript', r.stdout)
        self.assertEqual((d / ma_usage.SNAPSHOT).read_text(encoding='utf-8'), '{"windows": []}')

    def test_data_dir_finds_run_index(self):
        d = self.task(status='active')
        self.transcript(entry('2026-10-01 10:01:00', 'a'))
        data, run = self.root / 'data', self.root / 'run'
        data.mkdir()
        run.mkdir()
        (data / 'active-index.json').write_text(json.dumps({str(run): str(self.root / 'proj')}), encoding='utf-8')
        env = dict(self.env, MA_TASKS_DIR='')
        r = run_script(SNAP, '--cwd', str(run), '--data-dir', str(data), env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((d / ma_usage.SNAPSHOT).is_file())

    def test_no_task(self):
        self.assertEqual(run_script(SNAP, '--cwd', str(self.root), env=self.env).returncode, 1)
        self.assertEqual(run_script(SNAP, '--task-dir', str(self.root), env=self.env).returncode, 1)


class ArchiveTest(Base):
    def setUp(self):
        super().setUp()
        self.projects = self.root / 'projects.txt'
        self.projects.write_text(f'{self.root / "proj"}\n# comment\n{self.root / "missing"}\n', encoding='utf-8')
        self.env['MA_PROJECTS_FILE'] = str(self.projects)

    def run_archive(self, *args):
        return run_script(ARCHIVE, *args, env=self.env)

    def agent(self):
        return self.root / 'proj' / 'docs' / 'agent'

    def test_moves_old_finished_tasks_only(self):
        self.task(task='261001-done')
        self.task(task='261001-aborted', status='aborted 2026-10-01 10:20 reason')
        self.task(task='261001-running', status='active')
        recent = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.task(task='261028-recent', log=[f'{recent} step: n=1 name=Intake rev=0 session=s-2'])
        self.task(task='261001-current')   # the one .active names (make_task writes it last)
        self.transcript(entry('2026-10-01 10:01:00', 'a'))
        r = self.run_archive('--days', '7')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        left = sorted(p.name for p in self.agent().iterdir() if not p.name.startswith('.'))
        self.assertEqual(left, ['261001-current', '261001-running', '261028-recent'])
        moved = sorted(p.name for p in (self.agent() / '.archived').iterdir())
        self.assertEqual(moved, ['261001-aborted', '261001-done'])
        self.assertTrue((self.agent() / '.archived' / '261001-done' / ma_usage.SNAPSHOT).is_file())
        self.assertTrue((self.agent() / '.active').is_file())

    def test_data_dir_projects_file(self):
        """Criterion 4: without MA_PROJECTS_FILE the list is <data folder>/projects.txt."""
        self.task(task='261001-done')
        self.task(task='261001-current', status='active')
        data = self.root / 'data'
        data.mkdir()
        (data / 'projects.txt').write_text(f'{self.root / "proj"}\n', encoding='utf-8')
        self.env.update(MA_PROJECTS_FILE='', MA_TASKS_DIR='')
        r = self.run_archive('--dry-run', '--days', '7', '--data-dir', str(data))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('would move', r.stdout)

    def test_dry_run_moves_nothing(self):
        self.task(task='261001-done')
        self.task(task='261001-current', status='active')
        r = self.run_archive('--dry-run', '--days', '7')
        self.assertIn('would move', r.stdout)
        self.assertTrue((self.agent() / '261001-done').is_dir())
        self.assertFalse((self.agent() / '.archived').exists())

    def test_moves_without_transcript_and_takes_free_name(self):
        self.task(task='261001-done')
        self.task(task='261001-current', status='active')
        (self.agent() / '.archived' / '261001-done').mkdir(parents=True)
        r = self.run_archive('--days', '7')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('no usage snapshot', r.stdout)
        self.assertTrue((self.agent() / '.archived' / '261001-done-b' / 'intake.md').is_file())

    def test_bad_days(self):
        self.assertEqual(self.run_archive('--days', '-1').returncode, 2)


if __name__ == '__main__':
    unittest.main()

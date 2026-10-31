import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from monitor.taskview import build_task
from monitor.transcript import TranscriptCache
from tests.fixtures.build_fixtures import CLAUDE, EXPECTED_MAIN, PROJECTS

import ma_prices
from ma_prices import cost, load_prices

ROOT = Path(__file__).resolve().parent.parent
PRICES = load_prices(ma_prices.BUNDLED)
NOW = datetime(2026, 10, 24, 16, 8)
G = lambda a, b, c, d: {'G1a': a, 'G1b': b, 'G2': c, 'G3': d}

EXPECTED = {
    ('claude-sessions', '261024-cli-json-output'): dict(
        status='running', step=5, profile='dev', gates=G('ok', 'ok', 'ok', 'todo'),
        crit={'total': 2, 'res': []}, vfail=0, sstop=0, revs=None),
    ('agent-tasks', '261024-hitl-survey'): dict(
        status='running', step=5, profile='research', gates=G('ok', 'ok', 'todo', 'todo'),
        crit={'total': 4, 'res': []}, vfail=0, sstop=0,
        revs=[{'at': '14:10'}, {'at': '14:47', 'from': 5, 'back': 3, 'why': 'Added "cost control" to the sub-questions (user)',
                                'archive': 'archive/261024-144700-rev1/',
                                'invalid': ['plan-review.md', 'plan.md ## Approval'],
                                'keep': 'Existing work: work/q1~q3 keep', 'state': 'done'}]),
    ('obsidian-notes', '261023-hooks-notify-note'): dict(
        status='done', step=9, profile='research', gates=G('ok', 'ok', 'ok', 'ok'),
        crit={'total': 5, 'res': ['p'] * 5}, vfail=0, sstop=0, revs=None),
    ('work-notes', '261022-weekly-report'): dict(
        status='done', step=9, profile='general', gates=G('skip', 'ok', 'todo', 'ok'),
        crit={'total': 3, 'res': ['p'] * 3}, vfail=0, sstop=0, revs=None),
    ('flight-search', '261021-flight-watch'): dict(
        status='stopped', step=5, profile='dev', gates=G('ok', 'ok', 'todo', 'todo'),
        crit={'total': 4, 'res': []}, vfail=0, sstop=2, revs=None),
}


def task(project, tid, root=PROJECTS):
    return build_task(root / project, root / project / 'docs/agent' / tid, PRICES, TranscriptCache(CLAUDE), NOW)


class TaskViewTest(unittest.TestCase):
    def test_fixture_tasks_match_mockup(self):
        for (project, tid), want in EXPECTED.items():
            t = task(project, tid)
            self.assertNotIn('error', t, t.get('error'))
            self.assertEqual({k: t.get(k) for k in want}, want, tid)
        self.assertEqual(task('obsidian-notes', '261023-hooks-notify-note')['vfailMax'], 1)

    def test_header_fields(self):
        t = task('claude-sessions', '261024-cli-json-output')
        self.assertEqual((t['started'], t['elapsed'], t['now'], t['cost']), ('15:30', 38, '16:08', '2.41'))
        self.assertNotIn('est', t)
        self.assertEqual(t['title'], 'Add a --json output option to the CLI')
        self.assertRegex(t['key'], r'^[0-9a-f]{8}/261024-cli-json-output$')
        self.assertEqual(t['running'][0]['a'], 'coder')
        done = task('obsidian-notes', '261023-hooks-notify-note')
        self.assertEqual((done['started'], done['now'], done['elapsed']), ('10-23 14:02', '15:14', 72))

    def test_agent_cost_and_main(self):
        t = task('claude-sessions', '261024-cli-json-output')
        c2 = [x for x in t['log'] if x.get('id') == 'ag-c2'][0]
        self.assertIsInstance(c2['c'], float)
        self.assertNotIn('usage', c2)
        self.assertEqual(t['main'][5], round(cost(PRICES, 'claude-opus-5-5', EXPECTED_MAIN[5]), 2))
        self.assertEqual(c2['c'], round(cost(PRICES, 'claude-sonnet-5-5', {
            'input_tokens': 63000, 'output_tokens': 12600, 'cache_creation_input_tokens': 5040,
            'cache_read_input_tokens': 3360}), 2))
        self.assertNotIn('tok', c2)
        self.assertNotIn('tokens', c2)
        self.assertTrue(t['mainApprox'])
        self.assertIsNone(task('flight-search', '261021-flight-watch')['main'])
        self.assertEqual(task('agent-tasks', '261024-hitl-survey')['main'], None)

    def test_unpriced_main_window_is_none(self):
        prices = {k: v for k, v in PRICES.items() if 'opus' not in k}
        root = PROJECTS / 'claude-sessions'
        t = build_task(root, root / 'docs/agent/261024-cli-json-output', prices, TranscriptCache(CLAUDE), NOW)
        self.assertIsNone(t['main'][5])
        self.assertIn('claude-opus-5-5', t['unpriced'])
        self.assertEqual([x for x in t['log'] if x.get('id') == 'ag-c2'][0]['c'], 0.27)

    def test_payload_has_no_token_counts(self):
        def check(t):
            self.assertNotIn('tokens', t)
            self.assertIn('cost', t)
            for it in t['log']:
                for k in ('tok', 'tokens', 'usage'):
                    self.assertNotIn(k, it)
            vals = list((t['main'] or {}).values())
            for m in (t.get('mainR') or {}).values():
                vals += list(m.values())
            for v in vals:
                self.assertIsInstance(v, (int, float))
        for (project, tid) in EXPECTED:
            check(task(project, tid))

    def test_done_task_window_closes_at_last_record(self):
        """After G3 the same main session goes on to other work; that must not count for the finished task."""
        with tempfile.TemporaryDirectory() as d:
            sess = Path(d) / '-x-obsidian-notes' / 's-hooks.jsonl'
            sess.parent.mkdir()
            row = lambda hm, mid: json.dumps({'type': 'assistant', 'timestamp': datetime(2026, 10, 23, *hm).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                                              'message': {'id': mid, 'model': 'claude-opus-5-5', 'usage': {'input_tokens': 4000, 'output_tokens': 0}}})
            sess.write_text(row((15, 5), 'in-step-8') + '\n' + row((16, 20), 'next-task') + '\n', encoding='utf-8')
            t = build_task(PROJECTS / 'obsidian-notes', PROJECTS / 'obsidian-notes/docs/agent/261023-hooks-notify-note',
                           PRICES, TranscriptCache(Path(d)), NOW)
            self.assertEqual(t['main'][8], round(cost(PRICES, 'claude-opus-5-5', {'input_tokens': 4000}), 2))

    def test_files_steps_and_todo(self):
        f = {r['p']: r for r in task('claude-sessions', '261024-cli-json-output')['files']}
        self.assertTrue(f['verify.md']['todo'])
        self.assertEqual(f['plan.md']['s'], 4)   # last written at G1b (step 4)
        self.assertEqual(f['explore.md']['s'], 2)
        self.assertEqual(f['plan.md']['t'], '15:55')
        self.assertTrue(f['plan.md']['pv'].startswith('# Plan'))
        files = [r['p'] for r in task('agent-tasks', '261024-hitl-survey')['files']]
        self.assertIn('archive/', files)
        self.assertFalse([p for p in files if p.startswith('archive/') and p != 'archive/'])

    def test_mocks_with_archive(self):
        m = task('agent-tasks', '261024-hitl-survey')['mocks']
        self.assertEqual([(x['r'], x['at']) for x in m], [(0, '14:31'), (1, '14:56')])
        self.assertEqual(m[1]['kind'], 'note outline + sample paragraph')
        self.assertIn('Cost control', m[1]['body'])

    def test_deliver(self):
        d = task('obsidian-notes', '261023-hooks-notify-note')['deliver']
        self.assertEqual((d['kind'], d['items'][0][:2]), ('file', ['docs/notes/claude-hooks-notify.md', '6.1 KB']))
        self.assertEqual(task('work-notes', '261022-weekly-report')['deliver']['items'][0][1], '–')
        self.assertEqual(task('flight-search', '261021-flight-watch')['deliver']['kind'], 'none')

    def test_commit_deliver_and_prototype(self):
        """E: a dev task's `Delivered: commit:<sha>` is a commit, not a missing file; A5: `Prototype: requested`
        under ## Prototype (not in the mock-up) marks the mock-up."""
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(PROJECTS / 'claude-sessions', Path(d) / 'claude-sessions')
            T = Path(d) / 'claude-sessions/docs/agent/261024-cli-json-output'
            intake = T / 'intake.md'
            intake.write_text(intake.read_text(encoding='utf-8').replace('Status: active', 'Status: done')
                              + 'Delivered: commit:a491e13\n', encoding='utf-8')
            plan = T / 'plan.md'
            plan.write_text(plan.read_text(encoding='utf-8').replace(
                '## Approval', '## Prototype\nneeded\nPrototype: requested\n## Approval'), encoding='utf-8')
            t = task('claude-sessions', '261024-cli-json-output', Path(d))
            self.assertEqual(t['deliver']['items'], [['commit:a491e13', 'commit', '–']])
            self.assertEqual((t['mocks'][-1]['kind'], t['mocks'][-1]['proto']), ('CLI input/output', 'prototype'))
            self.assertFalse(t['mocks'][-1]['body'].startswith('Kind:'))

    def test_broken_task_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(PROJECTS / 'work-notes', Path(d) / 'work-notes')
            intake = Path(d) / 'work-notes/docs/agent/261022-weekly-report/intake.md'
            os.chmod(intake, 0)
            try:
                t = task('work-notes', '261022-weekly-report', Path(d))
            finally:
                os.chmod(intake, 0o644)
            self.assertEqual(set(t), {'id', 'key', 'project', 'error'})


if __name__ == '__main__':
    unittest.main()


def write_transcript(claude, task_dir, ma_usage):
    """A main transcript with one response 30 s after each step line (and one after the task, not counted)."""
    lines = ma_usage.read_log(task_dir / 'run-log.md')
    enter = ma_usage.step_enter(lines)
    rows = []
    for i, (ts, n, rev, sess) in enumerate(enter + [(lines[-1][0], 0, 0, enter[-1][3])]):
        stamp = (ts.replace(microsecond=0) + __import__('datetime').timedelta(seconds=30)).astimezone().isoformat()
        rows.append(json.dumps({'type': 'assistant', 'timestamp': stamp, 'message': {
            'id': f'm{i}', 'model': 'claude-opus-5-5', 'usage': {'input_tokens': 1000 * (i + 1), 'output_tokens': 10}}}))
    path = claude / '-x-obsidian' / f'{enter[0][3]}.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text('\n'.join(rows) + '\n', encoding='utf-8')


class SnapshotTest(unittest.TestCase):
    """A finished task reads main-usage.json (ma_usage) instead of a transcript that may be deleted."""

    def setUp(self):
        import ma_usage
        self.ma_usage = ma_usage
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('obsidian-notes', 'claude-sessions'):
            shutil.copytree(PROJECTS / name, self.root / name)
        self.none = self.root / 'no-transcripts'
        self.claude = self.root / 'claude'
        write_transcript(self.claude, self.root / 'obsidian-notes/docs/agent/261023-hooks-notify-note', ma_usage)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, project, task, claude):
        return build_task(self.root / project, self.root / project / 'docs/agent' / task, PRICES,
                          TranscriptCache(claude), NOW)

    def test_finished_task_same_numbers_from_snapshot(self):
        before = self.build('obsidian-notes', '261023-hooks-notify-note', self.claude)
        self.assertIsNotNone(before['main'])
        task_dir = self.root / 'obsidian-notes/docs/agent/261023-hooks-notify-note'
        self.assertEqual(self.ma_usage.write_snapshot(task_dir, self.claude, NOW)[0], 0)
        after = self.build('obsidian-notes', '261023-hooks-notify-note', self.none)
        self.assertEqual(after['main'], before['main'])
        self.assertEqual([x.get('c') for x in after['log']], [x.get('c') for x in before['log']])
        self.assertNotIn('tokens', after)

    def test_finished_task_without_snapshot_or_transcript(self):
        self.assertIsNone(self.build('obsidian-notes', '261023-hooks-notify-note', self.none)['main'])

    def test_snapshot_payload_has_no_token_counts(self):
        task_dir = self.root / 'obsidian-notes/docs/agent/261023-hooks-notify-note'
        self.ma_usage.write_snapshot(task_dir, self.claude, NOW)
        t = self.build('obsidian-notes', '261023-hooks-notify-note', self.none)
        self.assertNotIn('tokens', t)
        self.assertTrue(all(isinstance(v, (int, float)) for v in t['main'].values()))

    def test_running_task_ignores_snapshot(self):
        task_dir = self.root / 'claude-sessions/docs/agent/261024-cli-json-output'
        (task_dir / self.ma_usage.SNAPSHOT).write_text(
            '{"windows": [{"rev": 0, "step": 1, "model": "claude-opus-5-5", "usage": {"input_tokens": 99}}]}',
            encoding='utf-8')
        self.assertIsNone(self.build('claude-sessions', '261024-cli-json-output', self.none)['main'])

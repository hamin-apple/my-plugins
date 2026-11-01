"""Report data of one task (`monitor/report.py`, `Registry.get_report`) on the static fixtures in fixtures/report/."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monitor.registry import Registry

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'report'
PROJECT = FIXTURE / 'project'
FULL, ONLY, FOLLOW = '261102-full-report', '261103-intake-only', '261104-follow-up'
KEYS = {'overview', 'timeline', 'criteria', 'units', 'review', 'plan_review', 'decisions', 'gate_report'}


class ReportEnv:
    """An environment with MA_TASK_DIR=docs/agent and a Registry whose projects list holds the fixture project."""

    def start(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        projects = tmp / 'projects.txt'
        projects.write_text(str(PROJECT) + '\n', encoding='utf-8')
        self.env = mock.patch.dict(os.environ, {'MA_TASK_DIR': 'docs/agent'})
        self.env.start()
        self.registry = Registry(projects, claude_root=tmp / 'claude', prices_file=tmp / 'prices.json')
        self.keys = {t['id']: t['key'] for t in self.registry.list_tasks()}

    def stop(self):
        self.env.stop()
        self.tmp.cleanup()


def snapshot(folder):
    return sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns, p.stat().st_size) for p in folder.rglob('*'))


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = ReportEnv()
        cls.e.start()
        cls.full = cls.e.registry.get_report(cls.e.keys[FULL])

    @classmethod
    def tearDownClass(cls):
        cls.e.stop()

    def test_keys_and_overview(self):
        self.assertEqual(set(self.full), KEYS)
        o = self.full['overview']
        self.assertEqual((o['task'], o['profile'], o['status']), (FULL, 'dev', 'done'))
        self.assertEqual((o['delivered'], o['base'], o['follows'], o['followed_by']),
                         ('commit:abc1234', '0123456', '261101-earlier-task', [FOLLOW]))
        self.assertTrue(o['request'].startswith('--dev Build the full report'))
        self.assertTrue(o['purpose'].startswith('Give the report tests one task'))

    def test_criteria(self):
        c = self.full['criteria']
        self.assertEqual([r['n'] for r in c], [1, 2, 3])
        self.assertEqual([r['verdict'] for r in c], ['PASS', 'PASS', 'FAIL'])
        self.assertEqual(c[0]['short'], 'The report has eight keys.')
        self.assertEqual(c[0]['title'], 'The report has eight keys. It is read only.')
        self.assertIn('no cost table', c[2]['evidence'])

    def test_units(self):
        u = self.full['units']
        self.assertEqual([(x['id'], x['status'], x['secs']) for x in u], [('u1', 'done', 100), ('u2', 'running', 30)])
        self.assertEqual([x['criteria'] for x in u], [[1, 2, 3], [2, 3]])   # parenthesized numbers are ignored
        self.assertEqual(u[1]['files'], ['P/monitor/server.py', 'P/monitor/tests/test_server.py'])
        self.assertEqual(u[0]['group'], 'group 1 (worktree)')
        self.assertEqual(u[0]['title'], 'Report builder')

    def test_decisions_and_recommended_rate(self):
        d = self.full['decisions']
        self.assertEqual([(x['n'], x['at'], x['gate'], x['choice'], x['picked']) for x in d],
                         [(1, '09:06', 'G1a', 'Confirm', 'yes'), (2, '09:20', 'G1b', 'Reject', 'no'),
                          (3, '09:55', 'G3', 'Commit', 'yes')])
        self.assertEqual(self.full['gate_report']['recommended'], {'picked': 2, 'counted': 3})

    def test_cost_stretches_from_tally(self):
        cost = self.full['timeline']['cost']
        self.assertEqual(cost[0], {'steps': '1 Intake, 2 Explore-Scope', 'span': '09:00-09:10', 'usd': None, 'tokens': 1000})
        self.assertEqual(cost[1]['usd'], 2.5)
        self.assertEqual(cost[1]['tokens'], 2500)

    def test_cost_from_run_log_without_tally(self):
        from monitor import report
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / 'a-task'
            task.mkdir()
            (task / 'intake.md').write_text('Status: active\nProfile: dev\n', encoding='utf-8')
            (task / 'run-log.md').write_text(
                '2026-11-02 09:00:00 step: n=1 name=Intake\n2026-11-02 09:05:00 cost: usd=1.00 session=s\n'
                '2026-11-02 09:06:00 step: n=2 name=Plan\n2026-11-02 09:20:00 cost: usd=4.00 session=s\n', encoding='utf-8')
            data = report.build_report(Path(tmp), task, {'id': 'a-task', 'profile': 'dev', 'status': 'running'}, [])
        self.assertEqual([(c['steps'], c['usd']) for c in data['timeline']['cost']], [('1 Intake', None), ('2 Plan', 3.0)])
        self.assertEqual(data['timeline']['cost'][0]['span'], '09:00-09:05')

    def test_plan_review_runs(self):
        self.assertEqual(self.full['plan_review'], [
            {'run': 1, 'verdict': 'REVISE', 'blockers': 1, 'should_fix': 1, 'nitpicks': 0},
            {'run': 2, 'verdict': 'READY FOR APPROVAL', 'blockers': 0, 'should_fix': 0, 'nitpicks': 2}])

    def test_review_marks(self):
        r = self.full['review']
        self.assertEqual(r['blockers'], 0)
        a, b = r['findings']
        self.assertEqual((a['sev'], a['applied'], 'mark' in a), ('SHOULD-FIX', True, False))
        self.assertEqual((b['sev'], b['applied'], b['mark']), ('NITPICK', False, 'new'))
        self.assertEqual(a['where'], 'monitor/monitor/report.py:40')

    def test_gate_report(self):
        g = self.full['gate_report']
        self.assertEqual(len(g['summary']), 2)
        self.assertEqual([(i['level'], i['strength']) for i in g['improvements']], [('L1', 'weak'), ('L1', 'clear')])

    def test_timeline(self):
        t = self.full['timeline']
        self.assertEqual([s['n'] for s in t['steps']], [1, 2, 3, 4, 5, 7, 5, 7, 8])   # repeats kept, in order
        self.assertEqual(t['steps'][0], {'n': 1, 'name': 'Intake', 'start': '2026-11-02T09:00:00'})
        self.assertEqual(t['gates'], [{'id': 'G1a', 'at': '2026-11-02T09:05:00'}, {'id': 'G1b', 'at': '2026-11-02T09:20:00'},
                                      {'id': 'G3', 'at': '2026-11-02T09:50:00'}])
        self.assertEqual([(b['from'], b['to'], b['at']) for b in t['backs']],
                         [(4, 3, '2026-11-02T09:14:00'), (7, 5, '2026-11-02T09:33:00')])
        self.assertTrue(t['backs'][0]['why'].startswith('Plan Review REVISE'))
        self.assertEqual(t['end'], '2026-11-02T09:50:00')
        self.assertEqual(t['wait'], {'step': 8, 'from': '2026-11-02T09:50:00', 'until': '2026-11-02T09:55:00'})

    def test_intake_only(self):
        data = self.e.registry.get_report(self.e.keys[ONLY])
        self.assertEqual(set(data), KEYS)
        o = data['overview']
        self.assertEqual((o['task'], o['profile'], o['status']), (ONLY, 'dev', 'running'))
        self.assertEqual((o['delivered'], o['base'], o['follows'], o['followed_by'], o['purpose']), (None, None, None, [], None))
        self.assertTrue(o['request'].startswith('--dev add a thing'))
        self.assertTrue(all(data[k] is None for k in KEYS - {'overview'}))

    def test_followed_by_and_unknown_key(self):
        self.assertEqual(self.e.registry.get_report(self.e.keys[FOLLOW])['overview']['follows'], FULL)
        self.assertIsNone(self.e.registry.get_report('deadbeef/nope'))

    def test_read_only(self):
        before = snapshot(PROJECT)
        for key in self.e.keys.values():
            self.e.registry.get_report(key)
        self.assertEqual(snapshot(PROJECT), before)


if __name__ == '__main__':
    unittest.main()

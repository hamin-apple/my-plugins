"""Report data of one task (`monitor/report.py`, `Registry.get_report`) on the static fixtures in fixtures/report/."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monitor.registry import Registry

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'report'
PROJECT = FIXTURE / 'project'
FULL, ONLY, FOLLOW = '261102-full-report', '261103-intake-only', '261104-follow-up'
KEYS = {'overview', 'timeline', 'criteria', 'units', 'review', 'plan_review', 'decisions', 'gate_report',
        'verdict', 'gate', 'takeaway', 'review_totals'}
ROUNDS, G1B, G1A, G3, ABORTED, GENERAL = ('261105-review-rounds', '261106-gate-g1b', '261107-gate-g1a', '261108-gate-g3',
                                          '261109-aborted', '261110-general-running')


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


def temp_copy(name, status=None):
    """(tmp dir object, copy of a fixture task folder, task dict) for tests that edit the files."""
    tmp = tempfile.TemporaryDirectory()
    dst = Path(tmp.name) / name
    shutil.copytree(PROJECT / 'docs' / 'agent' / name, dst)
    return tmp, dst, {'id': name, 'profile': 'dev', 'status': status or 'running', 'key': 'h/' + name}


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
        self.assertTrue(o['background'].startswith('Give the report tests one task'))   # no labels: the first paragraph

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
        old = ('run', 'verdict', 'blockers', 'should_fix', 'nitpicks')
        self.assertEqual([{k: r[k] for k in old} for r in self.full['plan_review']], [
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
        self.assertEqual((o['background'], o['purpose']), (None, None))

    def report(self, name):
        return self.e.registry.get_report(self.e.keys[name])

    def test_background_purpose_labeled(self):
        o = self.report(ROUNDS)['overview']
        self.assertEqual(o['background'], 'The export command writes one file per run and overwrites the last one.')
        self.assertEqual(o['purpose'], 'Keep every export by adding a dated name, and ship it as 1.4.0.')

    def test_background_purpose_unlabeled(self):
        o = self.report(G1A)['overview']
        self.assertEqual((o['background'], o['purpose']),
                         ('The export command lists nothing about earlier runs.', 'Show the export history in the CLI.'))

    def test_background_purpose_general(self):
        o = self.report(GENERAL)['overview']
        self.assertEqual((o['background'], o['purpose']), (None, 'Collect the release notes into one page.'))
        self.assertEqual([c['n'] for c in self.report(GENERAL)['criteria']], [1, 2])

    def test_review_totals_cumulative(self):
        self.assertEqual(self.report(ROUNDS)['review_totals'], {
            'BLOCKER': {'found': 1, 'fixed': 1, 'open': 0}, 'SHOULD-FIX': {'found': 2, 'fixed': 2, 'open': 0},
            'NITPICK': {'found': 3, 'fixed': 1, 'open': 2}, 'rounds': 2})

    def test_review_totals_single_round(self):
        self.assertEqual(self.full['review_totals'], {
            'BLOCKER': {'found': 0, 'fixed': 0, 'open': 0}, 'SHOULD-FIX': {'found': 1, 'fixed': 1, 'open': 0},
            'NITPICK': {'found': 1, 'fixed': 0, 'open': 1}, 'rounds': 1})

    def totals(self, round1, round2, log=''):
        """review_totals of a temp copy of the rounds task with the two rounds and the run-log replaced."""
        from monitor import report
        tmp, task, info = temp_copy(ROUNDS, 'done')
        with tmp:
            (task / 'archive' / '261105-101500-run1' / 'review.md').write_text(round1, encoding='utf-8')
            (task / 'review.md').write_text(round2, encoding='utf-8')
            if log is not None:
                (task / 'run-log.md').write_text(
                    '2026-11-05 10:20:00 step: n=8 name=Review-Deliver rev=0 session=s1\n' + log, encoding='utf-8')
            return report.build_report(PROJECT, task, info, [])['review_totals']

    def test_carried_counted_once(self):
        t = self.totals('BLOCKER 0\n\n## Findings\n- NITPICK a.py:1 x (new)\n',
                        'BLOCKER 0\n\n## Findings\n- NITPICK a.py:1 x (carried)\n')
        self.assertEqual(t['NITPICK'], {'found': 1, 'fixed': 0, 'open': 1})

    def test_carried_without_earlier_round(self):
        t = self.totals('BLOCKER 0\n\n## Findings\n- NITPICK a.py:1 x (new)\n',
                        'BLOCKER 0\n\n## Findings\n- NITPICK b.py:2 y (carried)\n- NITPICK a.py:1 x (carried)\n\n'
                        '## Applied after review\n- b.py:2 done\n')
        self.assertEqual(t['NITPICK'], {'found': 2, 'fixed': 1, 'open': 1})   # never below 0 fixed

    def test_fix_line_before_last_review_ignored(self):
        from monitor import report
        tmp, task, info = temp_copy(ROUNDS, 'done')
        with tmp:
            log = task / 'run-log.md'
            rows = log.read_text(encoding='utf-8').splitlines()
            fix = next(r for r in rows if 'Review NITPICK src/app.py:88' in r)
            rows.remove(fix)
            rows.insert(max(i for i, r in enumerate(rows) if 'n=8' in r), fix)   # now before the last step 8
            text = '\n'.join(rows) + '\n'
            log.write_text(text, encoding='utf-8')
            t = report.build_report(PROJECT, task, info, [])['review_totals']
        self.assertEqual(t['NITPICK'], {'found': 3, 'fixed': 0, 'open': 3})

    def test_plan_review_found_fixed(self):
        a, b = self.report(ROUNDS)['plan_review']
        self.assertEqual((a['found'], a['fixed']), ({'BLOCKER': 1, 'SHOULD-FIX': 2, 'NITPICK': 0}, {'BLOCKER': 1, 'SHOULD-FIX': 0, 'NITPICK': 0}))
        self.assertEqual((b['found'], b['fixed']), ({'BLOCKER': 0, 'SHOULD-FIX': 1, 'NITPICK': 1}, {'BLOCKER': 0, 'SHOULD-FIX': 1, 'NITPICK': 0}))

    def test_gate_g1a(self):
        g = self.report(G1A)['gate']
        self.assertEqual(g, {'id': 'G1a', 'at': '2026-11-07T09:05:00', 'q': 'Scope confirmation: 261107-gate-g1a',
                             'purpose': 'Show the export history in the CLI.', 'criteria': 4,
                             'non_goals': ['No change to the file format.', 'No GUI.']})

    def test_gate_g1b(self):
        g = self.report(G1B)['gate']
        self.assertEqual((g['id'], g['at'], g['q']), ('G1b', '2026-11-06T10:20:00', 'Plan approval: 261106-gate-g1b'))
        self.assertEqual(g['summary'], 'Two coder units: the dated file name, then the docs.')
        self.assertEqual(g['units'], [{'id': 'u1', 'title': 'Dated export names', 'group': 'group 1'},
                                      {'id': 'u2', 'title': 'Docs', 'group': 'group 2'}])
        self.assertEqual(g['groups'], 2)
        self.assertEqual(g['estimate'], ['Subagents: 6 (2 my-agent:coder plus 4 judges).', 'Workflow: none.'])
        self.assertEqual(g['models'], {'preset': 'standard (definition values)', 'recommendation': None, 'rows': [
            {'agent': 'architect', 'model': 'opus', 'effort': 'high', 'note': ''},
            {'agent': 'coder', 'model': 'sonnet', 'effort': 'medium', 'note': ''}]})
        self.assertEqual(g['prototype'], f'/api/tasks/{self.e.keys[G1B]}/prototype')

    def test_gate_g1b_without_prototype(self):
        from monitor import report
        tmp, task, info = temp_copy(G1B)
        with tmp:
            (task / 'prototype' / 'index.html').unlink()
            g = report.build_report(PROJECT, task, info, [])['gate']
        self.assertIsNone(g['prototype'])

    def test_gate_g1b_summary_fallback(self):
        from monitor import report
        tmp, task, info = temp_copy(G1B)
        with tmp:
            plan = task / 'plan.md'
            original = plan.read_text(encoding='utf-8')
            base = report.build_report(PROJECT, task, info, [])['gate']
            for lead in ('', 'Profile: dev. Completion criteria 1-3 are in scope.md (confirmed).\n\n'):
                plan.write_text(original.replace('Two coder units: the dated file name, then the docs.\n\n', lead), encoding='utf-8')
                g = report.build_report(PROJECT, task, info, [])['gate']
                self.assertIsNone(g['summary'])
                self.assertEqual({k: v for k, v in g.items() if k != 'summary'}, {k: v for k, v in base.items() if k != 'summary'})

    def test_gate_g3(self):
        g = self.report(G3)['gate']
        self.assertEqual((g['id'], g['at']), ('G3', '2026-11-08T11:40:00'))
        self.assertEqual(g['verify'], {'verdict': 'ALL PASS', 'run': 1, 'pass': 4, 'total': 4, 'failed': []})
        self.assertEqual(g['review']['blockers'], 0)
        self.assertEqual(g['review']['totals']['SHOULD-FIX'], {'found': 1, 'fixed': 0, 'open': 1})
        self.assertEqual([(i['sev'], i['where'], i['mark']) for i in g['review']['open']],
                         [('SHOULD-FIX', 'src/cli.py:30', 'new'), ('NITPICK', 'src/app.py:70', 'new'), ('NITPICK', 'src/cli.py:12', None)])
        self.assertEqual(g['review']['open'][0]['text'], 'The count line has no unit.')

    def test_gate_g3_without_files(self):
        from monitor import report
        tmp, task, info = temp_copy(G3)
        with tmp:
            (task / 'verify.md').unlink()
            (task / 'review.md').unlink()
            g = report.build_report(PROJECT, task, info, [])['gate']
        self.assertEqual((g['id'], g['verify'], g['review']), ('G3', None, None))

    def test_gate_null_when_answered(self):
        self.assertIsNone(self.full['gate'])
        self.assertIsNone(self.report(GENERAL)['gate'])
        self.assertIsNone(self.report(ROUNDS)['gate'])

    def test_gate_null_when_not_running(self):
        from monitor import report
        tmp, task, info = temp_copy(ROUNDS, 'done')
        with tmp:
            with open(task / 'run-log.md', 'a', encoding='utf-8') as f:
                f.write('2026-11-05 10:40:00 ask: gate=G3 q="Again" rec=Commit session=s1\n')
            self.assertIsNone(report.build_report(PROJECT, task, info, [])['gate'])
        self.assertIsNone(self.report(ABORTED)['gate'])   # an open G1b ask, but the task is stopped

    def test_gate_latest_ask_wins(self):
        from monitor import report
        tmp, task, info = temp_copy(G1B)
        with tmp:
            with open(task / 'run-log.md', 'a', encoding='utf-8') as f:
                f.write('2026-11-06 10:30:00 ask: gate=G3 q="Later" rec=Commit session=s1\n')
            self.assertEqual(report.build_report(PROJECT, task, info, [])['gate']['id'], 'G3')

    def test_verdict_done(self):
        v = self.report(ROUNDS)['verdict']
        self.assertEqual(v, {'status': 'done', 'delivered': 'commit:abc1234', 'commit': 'abc1234', 'tag': None, 'reason': None,
                             'step': None, 'criteria': {'pass': 3, 'total': 3}, 'secs': 5160, 'usd': 12.4})

    def test_verdict_counts_only_the_criteria_rows(self):
        """verify.md may judge `Scope change:` lines after the criteria; those rows never raise the pass count above the total."""
        from monitor import report
        tmp, task, info = temp_copy(ROUNDS)
        with tmp:
            with open(task / 'verify.md', 'a', encoding='utf-8') as f:
                f.write('- 4. PASS the theme switch\n- 5. PASS the banner colors\n')
            self.assertEqual(report.build_report(PROJECT, task, info, [])['verdict']['criteria'], {'pass': 3, 'total': 3})
        tmp, task, info = temp_copy(G3)
        with tmp:
            with open(task / 'verify.md', 'a', encoding='utf-8') as f:
                f.write('- 9. PASS a scope change line\n')
            gate = report.build_report(PROJECT, task, info, [])['gate']
            self.assertEqual(gate['verify']['pass'], gate['verify']['total'])

    def test_verdict_aborted(self):
        v = self.report(ABORTED)['verdict']
        self.assertEqual((v['status'], v['reason'], v['step']), ('aborted', 'the person stopped it to split the work', {'n': 3, 'name': 'Plan'}))
        self.assertEqual((v['commit'], v['tag'], v['usd']), (None, None, None))

    def test_verdict_abort_line_reason(self):
        from monitor import report
        tmp, task, info = temp_copy(ABORTED, 'stopped')
        with tmp:
            with open(task / 'run-log.md', 'a', encoding='utf-8') as f:
                f.write('2026-11-09 10:00:00 abort: why="split into two tasks"\n')
            self.assertEqual(report.build_report(PROJECT, task, info, [])['verdict']['reason'], 'split into two tasks')

    def test_verdict_running_no_gate(self):
        data = self.report(GENERAL)
        v = data['verdict']
        self.assertEqual((v['status'], v['step'], v['delivered'], v['secs']), ('running', {'n': 5, 'name': 'Execute'}, None, 3900))
        self.assertIsNone(data['gate'])

    def test_takeaway_lines(self):
        t = self.report(ROUNDS)['takeaway']
        self.assertEqual(t['scope'], {'criteria': 3, 'pass': 3, 'units': 2, 'units_done': 2, 'verify_run': 2, 'plan_rewrites': 1})
        self.assertEqual(t['delivered'], {'status': 'done', 'delivered': 'commit:abc1234', 'commit': 'abc1234', 'step': None})
        self.assertEqual(t['next'], {'text': 'Record the cost of the Intake stretch.', 'clear': 1, 'weak': 2})

    def test_takeaway_next_weak_first_item(self):
        from monitor import report
        tmp, task, info = temp_copy(ROUNDS, 'done')
        with tmp:
            gr = task / 'gate-report.md'
            gr.write_text(gr.read_text(encoding='utf-8').replace('- [L1, clear]', '- [L1, weak]'), encoding='utf-8')
            n = report.build_report(PROJECT, task, info, [])['takeaway']['next']
        self.assertEqual(n, {'text': 'Put a short summary in the G3 popup.', 'clear': 0, 'weak': 3})

    def test_no_token_label_in_new_keys(self):
        for name in (ROUNDS, G1B, G3):
            data = self.report(name)
            for key in ('verdict', 'gate', 'takeaway', 'review_totals'):
                self.assertNotIn('token', str(data[key]).lower())

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

import unittest
from pathlib import Path

from monitor.events import build_events
from monitor.runlog import parse_line, read_lines

FX = Path(__file__).resolve().parent / 'fixtures' / 'projects'


def ev(project, task):
    return build_events(read_lines(FX / project / 'docs/agent' / task / 'run-log.md'))


def synth(*texts):
    return build_events([parse_line(t) for t in texts])


def agents(e, name):
    return [x for x in e.log if x['k'] == 'agent' and x['a'] == name]


class EventsTest(unittest.TestCase):
    def test_agent_pairing_and_live(self):
        e = ev('claude-sessions', '261024-cli-json-output')
        c1, c2 = agents(e, 'coder')
        self.assertTrue(c1['live'])
        self.assertEqual((c2['tok'], c2['res'], c2['live']), ('84k', 'DONE', False))
        self.assertEqual(c2['effort'], 'medium')
        self.assertEqual(c2['dur'], 8)
        self.assertEqual([r['id'] for r in e.running], ['ag-c1'])

    def test_phase_items(self):
        e = ev('claude-sessions', '261024-cli-json-output')
        ph = [x for x in e.log if x['k'] == 'phase']
        self.assertEqual([(x['s'], x['a']) for x in ph], [(1, 'router'), (3, 'recorder'), (5, 'recorder')])
        self.assertEqual(ph[0]['tx'], '① Define start')
        self.assertEqual(e.step_enter[-1][1:], (5, 0, 's-cli'))

    def test_mismatch(self):
        w, = agents(ev('obsidian-notes', '261023-hooks-notify-note'), 'writer')
        self.assertEqual((w['model'], w['actual'], w['mm']), ('sonnet', 'haiku', True))

    def test_waiting_and_g2(self):
        e = synth('2026-10-24 16:00:00 step: n=5 name=Execute rev=0 session=s',
                  '2026-10-24 16:01:15 ask: gate=G2 agent=my-agent:coder id=a1 tool=Bash q="npm i x"',
                  '2026-10-24 16:01:31 answer: gate=G2 id=a1 result=allowed',
                  '2026-10-24 16:10:00 ask: gate=G3 q="Accept it?"')
        self.assertEqual(e.waiting, {'gate': 'G3', 'q': 'Accept it?'})
        self.assertEqual(e.gates['G3'], 'wait')
        self.assertEqual(e.gates['G2'], 'ok')
        g2 = [x for x in e.log if x['k'] == 'popup' and x['a'] == 'perms'][0]
        self.assertEqual(g2['sub'], 'allowed')

    def test_g2_denied_guess(self):
        e = synth('2026-10-24 16:00:00 call: agent=my-agent:coder model=- effort=- isolation=- background=false',
                  '2026-10-24 16:00:01 start: agent=my-agent:coder id=a1 configured=sonnet effort=medium',
                  '2026-10-24 16:01:15 ask: gate=G2 agent=my-agent:coder id=a1 tool=Bash q="rm -rf build"',
                  '2026-10-24 16:03:00 stop: id=a1 actual=claude-sonnet-5-5 tokens=1000 secs=120 result=DONE end=ok')
        g2 = [x for x in e.log if x['k'] == 'popup'][0]
        self.assertEqual(g2['sub'], 'not run (denied?)')
        self.assertIsNone(e.waiting)

    def test_revision_steps(self):
        e = ev('agent-tasks', '261024-hitl-survey')
        self.assertEqual(len(e.revs), 2)
        self.assertEqual(e.revs[0], {'at': '14:10'})
        r1 = e.revs[1]
        self.assertEqual((r1['at'], r1['from'], r1['back']), ('14:47', 5, 3))
        self.assertEqual(r1['invalid'], ['plan-review.md', 'plan.md ## Approval'])
        self.assertEqual(r1['archive'], 'archive/261024-144700-rev1/')
        after = [x for x in e.log if x['ts'] > '2026-10-24 14:47:00']
        self.assertTrue(after and all(x['r'] == 1 for x in after))
        rev = [x for x in e.log if x['k'] == 'rev'][0]
        self.assertEqual(rev['r'], 1)

    def test_escalation_counters(self):
        """A1: the verifier's real first line is `Verdict: FAIL` (verifier.md); D5: a revision starts the count again."""
        def verify(i, res):
            return [f'2026-10-24 16:0{i}:00 call: agent=my-agent:verifier model=- effort=- isolation=- background=false',
                    f'2026-10-24 16:0{i}:01 start: agent=my-agent:verifier id=v{i} configured=opus effort=high',
                    f'2026-10-24 16:0{i}:30 stop: id=v{i} actual=claude-opus-5-5 tokens=1000 secs=29 result={res} end=ok']
        lines = []
        for i, res in enumerate(['"Verdict: FAIL"', '"Verdict: FAIL"', '"Verdict: ALL PASS"', '"Verdict: FAIL"']):
            lines += verify(i, res)
        e = synth(*lines)
        self.assertEqual((e.vfail, e.vfail_max), (1, 2))
        e = synth(*(lines + ['2026-10-24 16:05:00 revision: rev=1 why=x archive=a state=pending'] + verify(6, '"Verdict: FAIL"')))
        self.assertEqual((e.vfail, e.vfail_max), (1, 2))
        self.assertEqual(ev('flight-search', '261021-flight-watch').sstop, 2)

    def test_unit_stops_counted_per_unit(self):
        """D3: E's "same unit stopped twice" counts per `unit=`; two units stopping once each is 1."""
        def worker(i, unit):
            return [f'2026-10-24 16:0{i}:01 start: agent=my-agent:coder id=c{i} configured=sonnet effort=medium',
                    f'2026-10-24 16:0{i}:30 stop: id=c{i} unit={unit} actual=claude-sonnet-5-5 tokens=1 result=- end=partial']
        self.assertEqual(synth(*(worker(1, 'u1') + worker(2, 'u2'))).sstop, 1)
        self.assertEqual(synth(*(worker(1, 'u1') + worker(2, 'u2') + worker(3, 'u1'))).sstop, 2)

    def test_unitless_stops_are_not_one_unit(self):
        """A stop without unit= (a prototype writer, an old line) is not "the same unit" as another one."""
        lines = [f'2026-10-24 16:0{i}:01 start: agent=my-agent:writer id=w{i} configured=sonnet effort=medium\n'
                 f'2026-10-24 16:0{i}:30 stop: id=w{i} actual=claude-sonnet-5-5 tokens=1 result=- end=partial'
                 for i in (1, 2)]
        self.assertEqual(synth(*'\n'.join(lines).splitlines()).sstop, 1)

    def test_back_to_execute_logged(self):
        """B2: the `step:` line that goes back to Execute shows its reason and the kept verdicts."""
        e = synth('2026-10-24 16:00:00 step: n=7 name=Verify rev=0',
                  '2026-10-24 16:10:00 step: n=5 name=Execute rev=0 back="Verify FAIL 2" archive=archive/261024-161000-run1')
        it = [x for x in e.log if x['tx'].startswith('back to')][0]
        self.assertEqual((it['tx'], it['sub'], it['s']), ('back to Execute · Verify FAIL 2', 'archive archive/261024-161000-run1', 5))

    def test_draft_and_done_revisions(self):
        """B1/B4: a plan rewritten before G1b is no new rev; `state=done` updates its revision, not a second one."""
        e = synth('2026-10-24 16:00:00 step: n=3 name=Plan rev=0 session=s',
                  '2026-10-24 16:01:00 revision: rev=0 before=G1b why="Request changes" archive=archive/a-rev0/',
                  '2026-10-24 16:02:00 step: n=3 name=Plan rev=0 session=s',
                  '2026-10-24 16:10:00 revision: rev=1 why=x archive=archive/b-rev1/ state=pending',
                  '2026-10-24 16:10:30 revision: rev=1 state=done',
                  '2026-10-24 16:11:00 step: n=3 name=Plan rev=1 session=s')
        self.assertEqual(len(e.revs), 2)
        self.assertEqual((e.revs[1]['state'], e.revs[1]['back']), ('done', 3))
        self.assertEqual([x['r'] for x in e.log if x['tx'].startswith('plan rewrite')], [0])

    def test_two_questions_one_popup(self):
        e = synth('2026-10-30 10:00:00 step: n=1 name=Intake rev=0',
                  '2026-10-30 10:00:01 ask: gate=Q q=A qn=1',
                  '2026-10-30 10:00:01 ask: gate=Q q=B qn=2',
                  '2026-10-30 10:00:09 answer: gate=Q choice=two qn=2')
        self.assertEqual(e.gates['Q'], 'wait')
        e = synth('2026-10-30 10:00:00 step: n=1 name=Intake rev=0',
                  '2026-10-30 10:00:01 ask: gate=Q q=A qn=1',
                  '2026-10-30 10:00:01 ask: gate=Q q=B qn=2',
                  '2026-10-30 10:00:09 answer: gate=Q choice=two qn=2',
                  '2026-10-30 10:00:10 answer: gate=Q choice=one qn=1')
        self.assertNotIn('Q', e.gates)
        self.assertIsNone(e.waiting)
        subs = {x['tx']: x['sub'] for x in e.log if x['k'] == 'popup'}
        self.assertEqual(subs, {'Q A': 'one', 'Q B': 'two'})

    def test_old_asks_without_qn(self):
        e = synth('2026-10-30 10:00:01 ask: gate=Q q=A', '2026-10-30 10:00:02 ask: gate=Q q=B',
                  '2026-10-30 10:00:09 answer: gate=Q choice=two')
        subs = {x['tx']: x['sub'] for x in e.log if x['k'] == 'popup'}
        self.assertEqual(subs, {'Q A': None, 'Q B': 'two'})
        self.assertEqual(e.waiting, None)

    def test_delegated_approval_items(self):
        e = synth('2026-10-29 04:00:01 step: n=1 name=Intake rev=0',
                  '2026-10-29 04:00:02 delegate: state=on how=flag',
                  '2026-10-29 04:06:10 ask: gate=G1a q="Scope?" rec=Confirm',
                  '2026-10-29 04:06:10 answer: gate=G1a choice=Confirm by=L1',
                  '2026-10-29 04:07:00 ask: gate=G1b q="Plan?" rec=Approve',
                  '2026-10-29 04:07:05 answer: gate=G1b choice=Approve',
                  '2026-10-29 04:09:00 delegate: state=off how=person')
        tx = [x['tx'] for x in e.log]
        self.assertIn('delegated approval on (flag)', tx)
        self.assertIn('delegated approval off (person)', tx)
        subs = {x['tx']: x['sub'] for x in e.log if x['k'] == 'popup'}
        self.assertEqual(subs, {'G1a Scope?': 'Confirm · answered by L1', 'G1b Plan?': 'Approve'})

    def test_profile_and_plan_edit_items(self):
        e = synth('2026-10-29 03:12:40 profile: from=dev to=general back=2 archive=archive/a',
                  '2026-10-29 03:13:00 profile: from=research to=dev back=- archive=-',
                  '2026-10-29 03:14:00 fix: what="Plan Review NIT plan.md:41" files=plan.md before=G1b archive=archive/b',
                  '2026-10-29 03:15:00 fix: what=plain')
        self.assertEqual([x['tx'] for x in e.log],
                         ['profile dev → general · back to ② Plan', 'profile research → dev',
                          'plan edit by L1 · Plan Review NIT plan.md:41'])

    def test_cost_usd(self):
        self.assertEqual(ev('claude-sessions', '261024-cli-json-output').cost_usd, '2.41')

    def test_pre_v019_log(self):
        e = synth('15:56 call: my-agent:coder model=- isolation=worktree', '15:56 start: coder-1 Configured=sonnet')
        self.assertEqual((e.log, e.step_enter), ([], []))
        e = build_events([l for l in map(parse_line, ['# run-log x', '15:56 stop: coder-2 Actual=sonnet 84k DONE']) if l])
        self.assertEqual(e.log, [])
        self.assertIsNone(e.started)


if __name__ == '__main__':
    unittest.main()

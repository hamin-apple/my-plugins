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
                  '2026-10-24 16:10:00 ask: gate=G3 q="수용할까요?"')
        self.assertEqual(e.waiting, {'gate': 'G3', 'q': '수용할까요?'})
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
        lines = []
        for i, res in enumerate(['FAIL', 'FAIL', '"ALL PASS"', 'FAIL']):
            lines += [f'2026-10-24 16:0{i}:00 call: agent=my-agent:verifier model=- effort=- isolation=- background=false',
                      f'2026-10-24 16:0{i}:01 start: agent=my-agent:verifier id=v{i} configured=opus effort=high',
                      f'2026-10-24 16:0{i}:30 stop: id=v{i} actual=claude-opus-5-5 tokens=1000 secs=29 result={res} end=ok']
        e = synth(*lines)
        self.assertEqual((e.vfail, e.vfail_max), (1, 2))
        self.assertEqual(ev('flight-search', '261021-flight-watch').sstop, 2)

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

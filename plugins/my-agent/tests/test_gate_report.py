"""gate-report.py: the decision tally and the report copy (architecture 4.11 "retrospective")."""
import os
import tempfile
import unittest
from pathlib import Path

from helpers import L4, make_task, parse, run_script

SCRIPT = L4 / 'scripts' / 'gate-report.py'
TASK = '261025-probe-task'
DEFAULT_COPY = Path.home() / 'dev' / 'log' / 'my-agent'


class GateReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root / 'proj', task=TASK)
        self.proj = self.root / 'proj'
        self.reports = self.root / 'reports'
        self.env = {'MA_GATE_REPORT_DIR': str(self.reports), 'MA_TASKS_DIR': str(self.root / 'none')}
        # no test may write into the real default data folder
        self.assertTrue(self.env['MA_GATE_REPORT_DIR'].startswith(str(self.root)))
        self.assertFalse(self.reports.is_relative_to(DEFAULT_COPY))

    def tearDown(self):
        self.tmp.cleanup()

    def log(self, *lines):
        (self.task / 'run-log.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def run_gr(self, command, cwd=None):
        return run_script(SCRIPT, command, '--cwd', str(cwd or self.proj), env=self.env)

    def rows(self, out):
        return [[c.strip() for c in l.strip('|').split(' | ')] for l in out.splitlines()
                if l.startswith('| ') and l[2:3].isdigit()]

    def tally(self, *lines):
        self.log(*lines)
        r = self.run_gr('tally')
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_rec_same_or_different(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=G1a q="Scope confirmation" rec=Confirm',
                         '2026-10-26 23:01:00 answer: gate=G1a choice="Request changes"',
                         '2026-10-26 23:02:00 ask: gate=G1a q="Scope confirmation" rec=Confirm',
                         '2026-10-26 23:03:00 answer: gate=G1a choice=Confirm')
        self.assertEqual(self.rows(out), [['1', 'G1a', 'Scope confirmation', 'Confirm', 'Request changes', 'no', ''],
                                          ['2', 'G1a', 'Scope confirmation', 'Confirm', 'Confirm', 'yes', '']])

    def test_old_ask_without_rec(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q="Open the monitor"',
                         '2026-10-26 23:01:00 answer: gate=Q choice=Separate')
        self.assertEqual(self.rows(out), [['1', 'Q', 'Open the monitor', '(not recorded)', 'Separate', 'unknown', '']])

    def test_rec_dash_and_other(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q="Location" rec=-',
                         '2026-10-26 23:01:00 answer: gate=Q choice=Plain',
                         '2026-10-26 23:02:00 ask: gate=Q q="Location2" rec=A',
                         '2026-10-26 23:03:00 answer: gate=Q choice="plugins/my-agent only" other=1')
        self.assertEqual(self.rows(out), [['1', 'Q', 'Location', 'none', 'Plain', 'unknown', ''],
                                          ['2', 'Q', 'Location2', 'A', 'plugins/my-agent only', 'typed (Other)', '']])

    def test_unpaired_lines_are_noted(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=E q="Same slice"',
                         '2026-10-26 23:01:00 answer: gate=Q choice=Alone',
                         '2026-10-26 23:02:00 ask: gate=G3 q="Commit approval" rec=Commit',
                         '2026-10-26 23:03:00 answer: gate=G3 choice=Commit',
                         '2026-10-26 23:04:00 answer: gate=G3 choice=Rework')
        self.assertEqual(self.rows(out), [['1', 'E', 'Same slice', '(not recorded)', '-', 'unknown', 'no answer'],
                                          ['2', 'Q', '-', '(not recorded)', 'Alone', 'unknown', 'answer only'],
                                          ['3', 'G3', 'Commit approval', 'Commit', 'Commit', 'yes', ''],
                                          ['4', 'G3', 'Commit approval', 'Commit', 'Rework', 'no', 'answered twice']])

    def test_g2_lines_are_left_out(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=G2 tool=Bash',
                         '2026-10-26 23:00:05 answer: gate=G2 result=allow',
                         '2026-10-26 23:01:00 ask: gate=Q q=x rec=a',
                         '2026-10-26 23:01:30 answer: gate=Q choice=a')
        self.assertEqual(len(self.rows(out)), 1)
        self.assertIn('L1 lines 2, hook lines 0, G2 lines 2 left out', out)

    def test_metrics(self):
        out = self.tally(
            '2026-10-26 23:00:00 step: n=7 name=Verify model=claude-opus-4-8 session=s1',
            '2026-10-26 23:00:01 step: n=7 name=Verify model=claude-sonnet-5-5 session=s1',
            '2026-10-26 23:00:02 start: agent=my-agent:plan-reviewer id=p1 configured=opus',
            '2026-10-26 23:00:02 start: agent=my-agent:plan-reviewer id=p2 configured=opus',
            '2026-10-26 23:00:03 call: agent=my-agent:coder model=opus effort=-',
            '2026-10-26 23:00:04 call: agent=my-agent:coder model=- effort=-',
            '2026-10-26 23:00:05 start: agent=my-agent:coder id=a1 configured=sonnet',
            '2026-10-26 23:00:06 start: agent=my-agent:coder id=a2 configured=sonnet',
            '2026-10-26 23:00:07 stop: id=a1 actual=claude-opus-4-8 tokens=10 mismatch=1',
            '2026-10-26 23:00:08 stop: id=a2 actual=claude-sonnet-5-5 tokens=5',
            '2026-10-26 23:00:09 fix: what=x', '2026-10-26 23:00:10 fix: what=y',
            '2026-10-26 23:00:11 fix: what="Scope change: criterion 2 is checked by the user later" files=plan.md',
            '2026-10-26 23:00:12 revision: rev=0 before=G1b why=x archive=a',
            '2026-10-26 23:00:13 revision: rev=1 why=x archive=b state=pending',
            '2026-10-26 23:00:14 revision: rev=1 state=done')
        for row in ('| Verify runs | 2 |', '| Plan Review runs | 2 |', '| Subagents | 4 |',
                    '| Model mismatches | 2 (main session 1 · by step lines, subagents 1) |',
                    '| L1 small fixes | 2 |', '| Adjustments within the approved scope | 1 |', '| Plan rewrites before approval | 1 |',
                    '| In-flight revisions | 1 |',
                    '| Calls raised to opus | 1 (retries and explicit calls are not told apart) |'):
            self.assertIn(row, out)

    def misses(self, *events):
        """The Judge misses value for events: 'pass', 'fail', 'partial', 'verify' (step), 'rework'."""
        lines, n = [], 0
        for ev in events:
            n += 1
            t = f'2026-10-30 10:00:{n:02d}'
            if ev in ('pass', 'fail', 'partial'):
                result = {'pass': 'Verdict: ALL PASS', 'fail': 'Verdict: FAIL (1 of 3)',
                          'partial': 'PARTIAL could not run'}[ev]
                lines += [f'{t} start: agent=my-agent:verifier id=v{n} configured=sonnet',
                          f'{t} stop: id=v{n} actual=claude-sonnet-5-5 tokens=1 result="{result}"']
            elif ev == 'verify':
                lines.append(f'{t} step: n=7 name=Verify model=claude-opus-4-8 session=s1')
            elif ev == 'rework':
                lines.append(f'{t} answer: gate=G3 choice="Rework (Recommended)"')
        out = self.tally(*lines)
        prefix = '| Judge misses | '
        row = [l for l in out.splitlines() if l.startswith(prefix)]
        self.assertEqual(len(row), 1)
        self.assertIn('| Verify runs |', out.split(prefix)[0])
        return row[0][len(prefix):].rstrip(' |')

    def test_judge_misses(self):
        self.assertEqual(self.misses('pass', 'rework'), '1')
        self.assertEqual(self.misses('pass', 'rework', 'verify', 'pass', 'rework'), '2')
        self.assertEqual(self.misses('rework'), '0')
        self.assertEqual(self.misses('pass', 'verify', 'fail', 'rework'), '0')
        self.assertEqual(self.misses('pass', 'rework', 'rework'), '1')
        self.assertEqual(self.misses('pass', 'partial', 'rework'), '0')
        self.assertEqual(self.misses('pass', 'fail', 'rework'), '0')
        self.assertEqual(self.misses('pass', 'verify', 'rework'), '0')
        self.assertEqual(self.misses(), '0')

    def test_delegated_answer_note_and_new_rows(self):
        out = self.tally(
            '2026-10-29 04:00:01 delegate: state=on how=flag',
            '2026-10-29 04:06:10 ask: gate=G1a q="Scope?" rec=Confirm',
            '2026-10-29 04:06:10 answer: gate=G1a choice=Confirm by=L1',
            '2026-10-29 04:07:00 ask: gate=G3 q="Accept?" rec=Commit',
            '2026-10-29 04:07:30 answer: gate=G3 choice=Commit',
            '2026-10-29 04:08:00 fix: what="Plan Review NIT" files=plan.md before=G1b archive=a',
            '2026-10-29 04:08:30 fix: what=x',
            '2026-10-29 04:09:00 profile: from=dev to=general back=2 archive=a',
            '2026-10-29 04:10:00 delegate: state=off how=end')
        rows = self.rows(out)
        self.assertEqual(rows[0][1:], ['G1a', 'Scope?', 'Confirm', 'Confirm', 'delegated', 'answered by L1'])
        self.assertEqual(rows[1][6], '')
        for row in ('| Delegated answers | 1 |', '| Plan edits by L1 before approval | 1 |', '| L1 small fixes | 1 |',
                    '| Delegated approval | 04:00 on (flag), 04:10 off (end) |',
                    '| Profile changes | 1 (dev → general) |'):
            self.assertIn(row, out)

    def test_two_questions_one_popup(self):
        out = self.tally(
            '2026-10-30 10:00:00 ask: gate=Q q=A rec=x session=s1 qn=1',
            '2026-10-30 10:00:00 ask: gate=Q q=B rec=y session=s1 qn=2',
            '2026-10-30 10:01:00 answer: gate=Q choice=y session=s1 qn=2',
            '2026-10-30 10:01:01 answer: gate=Q choice=z session=s1 qn=1')
        self.assertEqual(self.rows(out), [['1', 'Q', 'A', 'x', 'z', 'no', ''], ['2', 'Q', 'B', 'y', 'y', 'yes', '']])
        out = self.tally(
            '2026-10-30 10:00:00 ask: gate=Q q=A rec=x session=s1 qn=1',
            '2026-10-30 10:00:00 ask: gate=Q q=B rec=y session=s1 qn=2',
            '2026-10-30 10:01:00 answer: gate=Q choice=x session=s1 qn=1')
        self.assertEqual(self.rows(out), [['1', 'Q', 'A', 'x', 'x', 'yes', ''], ['2', 'Q', 'B', 'y', '-', 'unknown', 'no answer']])

    def test_answered_twice_per_key(self):
        out = self.tally(
            '2026-10-30 10:00:00 ask: gate=Q q=A rec=x session=s1 qn=1',
            '2026-10-30 10:00:00 ask: gate=Q q=B rec=y session=s1 qn=2',
            '2026-10-30 10:01:00 answer: gate=Q choice=x session=s1 qn=1',
            '2026-10-30 10:01:01 answer: gate=Q choice=x session=s1 qn=1',
            '2026-10-30 10:01:02 answer: gate=Q choice=y session=s1 qn=2')
        notes = [r[6] for r in self.rows(out)]
        self.assertEqual(notes, ['', '', 'answered twice'])

    def test_sessions_interleaved_at_one_gate(self):
        out = self.tally(
            '2026-10-30 10:00:00 ask: gate=G3 q=A rec=x session=s1',
            '2026-10-30 10:00:01 ask: gate=G3 q=B rec=y session=s2',
            '2026-10-30 10:01:00 answer: gate=G3 choice=y session=s2',
            '2026-10-30 10:01:01 answer: gate=G3 choice=q session=s1')
        self.assertEqual(self.rows(out), [['1', 'G3', 'A', 'x', 'q', 'no', ''], ['2', 'G3', 'B', 'y', 'y', 'yes', '']])

    def test_pre_prose_delegated_rows(self):
        out = self.tally(
            '2026-10-30 10:00:00 ask: gate=Q q=A rec=x',
            '2026-10-30 10:00:01 answer: gate=Q choice=x pre=1',
            '2026-10-30 10:00:02 ask: gate=Q q=B rec=y',
            '2026-10-30 10:00:03 answer: gate=Q choice=y prose=1',
            '2026-10-30 10:00:04 ask: gate=Q q=C rec=y',
            '2026-10-30 10:00:05 answer: gate=Q choice=y by=L1',
            '2026-10-30 10:00:06 ask: gate=Q q=D rec=y',
            '2026-10-30 10:00:07 answer: gate=Q choice=w other=1')
        self.assertEqual([r[5] for r in self.rows(out)], ['in advance', 'prose reply', 'delegated', 'typed (Other)'])

    def test_plan_review_runs_from_start_lines(self):
        out = self.tally('2026-10-30 10:00:00 start: agent=my-agent:plan-reviewer id=p1 configured=opus',
                         '2026-10-30 10:00:09 start: agent=my-agent:plan-reviewer id=p2 configured=opus',
                         '2026-10-30 10:00:10 start: agent=my-agent:coder id=c1 configured=sonnet')
        self.assertIn('| Plan Review runs | 2 |', out)
        out = self.tally('2026-10-30 10:00:00 step: n=4 name=Plan-Review model=- session=s1')
        self.assertIn('| Plan Review runs | 0 |', out)

    def test_old_run_log_has_no_new_rows(self):
        out = self.tally('2026-10-26 23:00:09 fix: what=x', '2026-10-26 23:00:10 ask: gate=G1a q=Q rec=A',
                         '2026-10-26 23:00:11 answer: gate=G1a choice=A')
        for word in ('Delegated', 'Profile changes', 'Plan edits by L1'):
            self.assertNotIn(word, out)
        self.assertIn('| L1 small fixes | 1 |', out)
        self.assertEqual(self.rows(out)[0][1:], ['G1a', 'Q', 'A', 'A', 'yes', ''])

    def test_cost_stretches_and_tokens(self):
        out = self.tally(
            '2026-10-26 23:00:00 step: n=1 name=Intake',
            '2026-10-26 23:00:01 cost: session=s1 usd=1.00',
            '2026-10-26 23:10:00 step: n=3 name=Plan',
            '2026-10-26 23:10:30 stop: id=a1 tokens=1000',
            '2026-10-26 23:20:00 cost: session=s1 usd=3.50',
            '2026-10-26 23:20:10 step: n=5 name=Execute',
            '2026-10-26 23:30:00 stop: id=a2 tokens=2500',
            '2026-10-26 23:40:00 cost: session=s2 usd=0.30',
            '2026-10-26 23:50:00 step: n=7 name=Verify',
            '2026-10-26 23:55:00 cost: session=s1 usd=4.00',
            '2026-10-26 23:56:00 stop: id=a3 tokens=7')
        self.assertIn('| 23:00–23:00 | 1 Intake | not recorded | 0 |', out)
        self.assertIn('| 23:00–23:20 | 3 Plan | 2.50 | 1,000 |', out)
        self.assertIn('| 23:20–23:40 | 5 Execute | not recorded | 2,500 |', out)
        self.assertIn('| 23:40–23:55 | 7 Verify | 0.50 | 0 |', out)
        self.assertIn('| 23:55– | - | not recorded | 7 |', out)

    def test_no_cost_lines(self):
        out = self.tally('2026-10-26 23:00:00 step: n=1 name=Intake',
                         '2026-10-26 23:01:00 stop: id=a1 tokens=1234')
        self.assertIn('| 23:00– | 1 Intake | not recorded | 1,234 |', out)

    def test_no_decisions_and_no_log(self):
        r = self.run_gr('tally')   # no run-log at all
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'run-log: docs/agent/{TASK}/run-log.md missing', r.stdout)
        self.assertIn('No decisions (no ask/answer lines)', r.stdout)
        self.assertIn('| Model mismatches | 0 (main session 0 · by step lines, subagents 0) |', r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith('## Cost and tokens per stretch\nNot recorded'))
        out = self.tally('2026-10-26 23:00:00 fix: what=x')
        self.assertIn('No decisions', out)

    def test_no_active_task(self):
        other = self.root / 'other'
        (other / '.git').mkdir(parents=True)
        for command in ('tally', 'copy'):
            r = self.run_gr(command, cwd=other)
            self.assertEqual(r.returncode, 1)
            self.assertIn('no active my-agent task', r.stdout)

    def test_bad_arguments(self):
        self.assertEqual(run_script(SCRIPT, 'bogus', env=self.env).returncode, 2)
        self.assertEqual(run_script(SCRIPT, env=self.env).returncode, 2)

    def test_recommended_suffix_is_stripped_before_comparing(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=G3 q=x rec="Commit (recommended)"',
                         '2026-10-26 23:00:30 answer: gate=G3 choice="Commit (Recommended)"')
        self.assertIn('| 1 | G3 | x | Commit | Commit | yes | |', out)

    def test_saved_to_task_folder(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q=x rec=a', '2026-10-26 23:00:30 answer: gate=Q choice=a')
        saved = self.task / 'gate-tally.md'
        self.assertIn(f'saved: docs/agent/{TASK}/gate-tally.md', out)
        text = saved.read_text(encoding='utf-8')
        self.assertIn(f'gate-report tally: {TASK}', text)
        self.assertIn('| 1 | Q | x | a | a | yes | |', text)
        self.assertNotIn('saved:', text)
        self.assertFalse((self.task / 'work').exists())

    def test_other_task_run_log_is_not_read(self):
        other = self.proj / 'docs' / 'agent' / '261025-other'
        other.mkdir()
        (other / 'run-log.md').write_text('2026-10-26 23:00:00 ask: gate=Q q=elsewhere rec=a\n', encoding='utf-8')
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q=mine rec=a')
        self.assertIn('mine', out)
        self.assertNotIn('elsewhere', out)

    def test_old_run_log_fixture_parses(self):
        """Lines from before rec=/other=1 (run-log.py's own output) read as 'unknown'."""
        run_script(L4 / 'scripts' / 'run-log.py', 'ask', 'gate=G1b', 'q=Approve the plan?', '--cwd', str(self.proj),
                   env=self.env)
        run_script(L4 / 'scripts' / 'run-log.py', 'answer', 'gate=G1b', 'choice=Approve', '--cwd', str(self.proj),
                   env=self.env)
        r = self.run_gr('tally')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows(r.stdout), [['1', 'G1b', 'Approve the plan?', '(not recorded)', 'Approve', 'unknown', '']])

    def test_new_fields_keep_the_monitor_parsing(self):
        from helpers import events
        r = run_script(L4 / 'scripts' / 'run-log.py', 'ask', 'gate=G3', 'q=Commit approval', 'rec=Commit', '--cwd', str(self.proj),
                       env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        run_script(L4 / 'scripts' / 'run-log.py', 'answer', 'gate=G3', 'choice=Commit', 'other=1', '--cwd', str(self.proj),
                   env=self.env)
        last = (self.task / 'run-log.md').read_text(encoding='utf-8').splitlines()
        self.assertEqual(parse(last[0])['rec'], 'Commit')
        self.assertEqual(parse(last[-1])['other'], '1')
        self.assertEqual(events(self.task).answered['G3'], 'Commit')

    def test_copy_makes_folder_and_numbers_names(self):
        (self.task / 'gate-report.md').write_text('# Gate report\n', encoding='utf-8')
        self.assertFalse(self.reports.exists())
        r = self.run_gr('copy')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f'copied docs/agent/{TASK}/gate-report.md -> {self.reports / (TASK + ".md")}')
        self.assertEqual((self.reports / f'{TASK}.md').read_text(encoding='utf-8'), '# Gate report\n')
        (self.task / 'gate-report.md').write_text('# second\n', encoding='utf-8')
        self.assertEqual(self.run_gr('copy').returncode, 0)
        self.assertEqual((self.reports / f'{TASK}-2.md').read_text(encoding='utf-8'), '# second\n')
        r = self.run_gr('copy')
        self.assertIn(f'{TASK}-3.md', r.stdout)
        self.assertEqual((self.reports / f'{TASK}.md').read_text(encoding='utf-8'), '# Gate report\n')

    def test_copy_without_report_copies_nothing(self):
        r = self.run_gr('copy')
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.reports.exists())

    def test_tally_write_failure_exits_3(self):
        (self.task / 'gate-tally.md').mkdir()   # a directory in the way: the file cannot be written
        self.log('2026-10-26 23:00:00 ask: gate=Q q=x rec=a')
        r = self.run_gr('tally')
        self.assertEqual(r.returncode, 3)
        self.assertIn('cannot write', r.stdout)
        self.assertIn('gate-tally.md', r.stdout)

    def test_copy_write_failure_exits_3(self):
        (self.task / 'gate-report.md').write_text('# Gate report\n', encoding='utf-8')
        self.reports.write_text('a file where the folder should be', encoding='utf-8')
        r = self.run_gr('copy')
        self.assertEqual(r.returncode, 3)
        self.assertIn('cannot copy', r.stdout)

    def test_copy_with_data_dir(self):
        (self.task / 'gate-report.md').write_text('# Gate report\n', encoding='utf-8')
        data = self.root / 'data'
        env = dict(self.env, MA_GATE_REPORT_DIR='', MA_TASKS_DIR='')
        r = run_script(SCRIPT, 'copy', '--cwd', str(self.proj), '--data-dir', str(data), env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((data / 'gate-report' / f'{TASK}.md').is_file())

    def test_report_dir_default_and_env(self):
        import ma_gate_report
        names = ('MA_GATE_REPORT_DIR', 'MA_TASKS_DIR', 'CLAUDE_PLUGIN_OPTION_DATA_DIR', 'HOME')
        saved = {k: os.environ.get(k) for k in names}
        try:
            for k in names[:3]:
                os.environ.pop(k, None)
            os.environ['HOME'] = str(self.root)
            self.assertEqual(ma_gate_report.report_dir(), self.root / 'dev/log/my-agent/gate-report')
            os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = str(self.root / 'X')
            self.assertEqual(ma_gate_report.report_dir(), self.root / 'X/gate-report')
            os.environ['MA_GATE_REPORT_DIR'] = str(self.reports)
            self.assertEqual(ma_gate_report.report_dir(), self.reports)
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


if __name__ == '__main__':
    unittest.main()

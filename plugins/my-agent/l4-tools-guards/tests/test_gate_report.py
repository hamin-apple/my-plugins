"""gate-report.py: the decision tally and the report copy (architecture 4.11 "회고")."""
import os
import tempfile
import unittest
from pathlib import Path

from helpers import L4, make_task, parse, run_script

SCRIPT = L4 / 'scripts' / 'gate-report.py'
TASK = '261025-probe-task'
DEFAULT_COPY = Path.home() / 'dev/skills'


class GateReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root / 'proj', task=TASK)
        self.proj = self.root / 'proj'
        self.reports = self.root / 'reports'
        self.env = {'MA_GATE_REPORT_DIR': str(self.reports), 'MA_TASKS_DIR': str(self.root / 'none')}
        # no test may copy into the real my-surrogate folder
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
        out = self.tally('2026-10-26 23:00:00 ask: gate=G1a q="범위 확정" rec=확정',
                         '2026-10-26 23:01:00 answer: gate=G1a choice="수정 요청"',
                         '2026-10-26 23:02:00 ask: gate=G1a q="범위 확정" rec=확정',
                         '2026-10-26 23:03:00 answer: gate=G1a choice=확정')
        self.assertEqual(self.rows(out), [['1', 'G1a', '범위 확정', '확정', '수정 요청', '아니오', ''],
                                          ['2', 'G1a', '범위 확정', '확정', '확정', '예', '']])

    def test_old_ask_without_rec(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q="모니터를 열지"',
                         '2026-10-26 23:01:00 answer: gate=Q choice=별도')
        self.assertEqual(self.rows(out), [['1', 'Q', '모니터를 열지', '(기록 없음)', '별도', '알 수 없음', '']])

    def test_rec_dash_and_other(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q="위치" rec=-',
                         '2026-10-26 23:01:00 answer: gate=Q choice=그냥',
                         '2026-10-26 23:02:00 ask: gate=Q q="위치2" rec=A',
                         '2026-10-26 23:03:00 answer: gate=Q choice="plugins/my-agent만" other=1')
        self.assertEqual(self.rows(out), [['1', 'Q', '위치', '없음', '그냥', '알 수 없음', ''],
                                          ['2', 'Q', '위치2', 'A', 'plugins/my-agent만', '직접 입력', '']])

    def test_unpaired_lines_are_noted(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=E q="같은 slice"',
                         '2026-10-26 23:01:00 answer: gate=Q choice=혼자',
                         '2026-10-26 23:02:00 ask: gate=G3 q="커밋 승인" rec=커밋',
                         '2026-10-26 23:03:00 answer: gate=G3 choice=커밋',
                         '2026-10-26 23:04:00 answer: gate=G3 choice=재작업')
        self.assertEqual(self.rows(out), [['1', 'E', '같은 slice', '(기록 없음)', '-', '알 수 없음', '답 없음'],
                                          ['2', 'Q', '-', '(기록 없음)', '혼자', '알 수 없음', '답만 있음'],
                                          ['3', 'G3', '커밋 승인', '커밋', '커밋', '예', ''],
                                          ['4', 'G3', '커밋 승인', '커밋', '재작업', '아니오', '답 두 번']])

    def test_g2_lines_are_left_out(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=G2 tool=Bash',
                         '2026-10-26 23:00:05 answer: gate=G2 result=allow',
                         '2026-10-26 23:01:00 ask: gate=Q q=x rec=a',
                         '2026-10-26 23:01:30 answer: gate=Q choice=a')
        self.assertEqual(len(self.rows(out)), 1)
        self.assertIn('L1 줄 2, hook 줄 0, G2 줄 2 제외', out)

    def test_metrics(self):
        out = self.tally(
            '2026-10-26 23:00:00 step: n=7 name=Verify model=claude-opus-4-8 session=s1',
            '2026-10-26 23:00:01 step: n=7 name=Verify model=claude-sonnet-5-5 session=s1',
            '2026-10-26 23:00:02 step: n=4 name=Plan-Review model=- session=s1',
            '2026-10-26 23:00:03 call: agent=my-agent:coder model=opus effort=-',
            '2026-10-26 23:00:04 call: agent=my-agent:coder model=- effort=-',
            '2026-10-26 23:00:05 start: agent=my-agent:coder id=a1 configured=sonnet',
            '2026-10-26 23:00:06 start: agent=my-agent:coder id=a2 configured=sonnet',
            '2026-10-26 23:00:07 stop: id=a1 actual=claude-opus-4-8 tokens=10 mismatch=1',
            '2026-10-26 23:00:08 stop: id=a2 actual=claude-sonnet-5-5 tokens=5',
            '2026-10-26 23:00:09 fix: what=x', '2026-10-26 23:00:10 fix: what=y',
            '2026-10-26 23:00:11 fix: what="Scope change: 기준 2 직접 확인은 사용자가 나중에 함" files=plan.md',
            '2026-10-26 23:00:12 revision: rev=0 before=G1b why=x archive=a',
            '2026-10-26 23:00:13 revision: rev=1 why=x archive=b state=pending',
            '2026-10-26 23:00:14 revision: rev=1 state=done')
        for row in ('| Verify 횟수 | 2 |', '| Plan Review 횟수 | 1 |', '| 서브에이전트 수 | 2 |',
                    '| 모델 불일치 수 | 2 (주 세션 1 · step 줄 기준, 서브에이전트 1) |',
                    '| L1 작은 수정 수 | 2 |', '| 승인 범위 안 조정 수 | 1 |', '| 승인 전 계획 다시 쓰기 수 | 1 |',
                    '| 작업 중 수정 수 | 1 |',
                    '| opus로 올린 호출 수 | 1 (재시도와 명시 호출을 구별하지 않음) |'):
            self.assertIn(row, out)

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
        self.assertIn('| 23:00–23:00 | 1 Intake | 기록 없음 | 0 |', out)
        self.assertIn('| 23:00–23:20 | 3 Plan | 2.50 | 1,000 |', out)
        self.assertIn('| 23:20–23:40 | 5 Execute | 기록 없음 | 2,500 |', out)
        self.assertIn('| 23:40–23:55 | 7 Verify | 0.50 | 0 |', out)
        self.assertIn('| 23:55– | - | 기록 없음 | 7 |', out)

    def test_no_cost_lines(self):
        out = self.tally('2026-10-26 23:00:00 step: n=1 name=Intake',
                         '2026-10-26 23:01:00 stop: id=a1 tokens=1234')
        self.assertIn('| 23:00– | 1 Intake | 기록 없음 | 1,234 |', out)

    def test_no_decisions_and_no_log(self):
        r = self.run_gr('tally')   # no run-log at all
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'run-log: docs/agent/{TASK}/run-log.md 없음', r.stdout)
        self.assertIn('결정 없음 (ask/answer 줄이 없습니다)', r.stdout)
        self.assertIn('| 모델 불일치 수 | 0 (주 세션 0 · step 줄 기준, 서브에이전트 0) |', r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith('## 단계별 비용·토큰\n기록 없음'))
        out = self.tally('2026-10-26 23:00:00 fix: what=x')
        self.assertIn('결정 없음', out)

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
        out = self.tally('2026-10-26 23:00:00 ask: gate=G3 q=x rec="커밋 (recommended)"',
                         '2026-10-26 23:00:30 answer: gate=G3 choice="커밋 (Recommended)"')
        self.assertIn('| 1 | G3 | x | 커밋 | 커밋 | 예 | |', out)

    def test_saved_to_task_folder(self):
        out = self.tally('2026-10-26 23:00:00 ask: gate=Q q=x rec=a', '2026-10-26 23:00:30 answer: gate=Q choice=a')
        saved = self.task / 'gate-tally.md'
        self.assertIn(f'saved: docs/agent/{TASK}/gate-tally.md', out)
        text = saved.read_text(encoding='utf-8')
        self.assertIn(f'gate-report tally: {TASK}', text)
        self.assertIn('| 1 | Q | x | a | a | 예 | |', text)
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
        """Lines from before rec=/other=1 (run-log.py's own output) read as '알 수 없음'."""
        run_script(L4 / 'scripts' / 'run-log.py', 'ask', 'gate=G1b', 'q=계획을 승인할까요?', '--cwd', str(self.proj),
                   env=self.env)
        run_script(L4 / 'scripts' / 'run-log.py', 'answer', 'gate=G1b', 'choice=승인', '--cwd', str(self.proj),
                   env=self.env)
        r = self.run_gr('tally')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows(r.stdout), [['1', 'G1b', '계획을 승인할까요?', '(기록 없음)', '승인', '알 수 없음', '']])

    def test_new_fields_keep_the_monitor_parsing(self):
        from helpers import events
        r = run_script(L4 / 'scripts' / 'run-log.py', 'ask', 'gate=G3', 'q=커밋 승인', 'rec=커밋', '--cwd', str(self.proj),
                       env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        run_script(L4 / 'scripts' / 'run-log.py', 'answer', 'gate=G3', 'choice=커밋', 'other=1', '--cwd', str(self.proj),
                   env=self.env)
        last = (self.task / 'run-log.md').read_text(encoding='utf-8').splitlines()
        self.assertEqual(parse(last[0])['rec'], '커밋')
        self.assertEqual(parse(last[-1])['other'], '1')
        self.assertEqual(events(self.task).answered['G3'], '커밋')

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

    def test_report_dir_default_and_env(self):
        import ma_gate_report
        old = os.environ.pop('MA_GATE_REPORT_DIR', None)
        try:
            self.assertEqual(ma_gate_report.report_dir(), DEFAULT_COPY / 'my-surrogate/gate-report')
            os.environ['MA_GATE_REPORT_DIR'] = str(self.reports)
            self.assertEqual(ma_gate_report.report_dir(), self.reports)
        finally:
            os.environ.pop('MA_GATE_REPORT_DIR', None)
            if old is not None:
                os.environ['MA_GATE_REPORT_DIR'] = old


if __name__ == '__main__':
    unittest.main()

"""Usage, cost and main-model reader for Codex sessions (u6): the same output fields and run-log format as Claude.

A Codex session record is `<sessions>/YYYY/MM/DD/rollout-*.jsonl` ($MA_CODEX_SESSIONS); the fixture
`fixtures/codex/session-with-subagent.jsonl` is split into a main record and a subagent record under a temp folder.
"""
import json
import re
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

from helpers import L4, log_lines, make_task, records, run_script

import ma_host
import ma_models
import ma_prices
import ma_schema
import ma_usage

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'codex' / 'session-with-subagent.jsonl'
SESSION = '019a0000-0000-7000-8000-000000000001'
SUB = '019a0000-0000-7000-8000-0000000000b2'
SNAP = L4 / 'scripts' / 'usage-snapshot.py'
GATE = L4 / 'scripts' / 'gate-report.py'
ARCHIVE = L4 / 'scripts' / 'archive-tasks.py'
RUNLOG = L4 / 'scripts' / 'run-log.py'


def local(stamp):
    """Run-log time of a UTC fixture stamp."""
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M:%S')


T0, T_END = local('2026-01-01T00:00:00Z'), local('2026-01-01T00:00:09Z')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.codex = self.root / 'codex-sessions'
        (self.root / 'statusline-empty').mkdir()
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'MA_CODEX_SESSIONS': str(self.codex),
                    'MA_CLAUDE_PROJECTS': str(self.root / 'claude'),
                    'MA_STATUSLINE_DIR': str(self.root / 'statusline-empty')}
        patch = mock.patch.dict('os.environ', {'MA_CODEX_SESSIONS': str(self.codex)})   # in-process calls
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def records(self, model=None, role=None, nested=False):
        """Main and subagent record of the fixture as two files under YYYY/MM/DD (`nested`: one file, as the fixture)."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        if model:
            lines = [l.replace('gpt-6-luna', model) if '"turn_context"' in l else l for l in lines]
        if role:
            lines = [l.replace('"agent_role": null', f'"agent_role": "{role}"') for l in lines]
        day = self.codex / '2026' / '01' / '01'
        day.mkdir(parents=True, exist_ok=True)
        if nested:
            (day / 'rollout-1-main.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return
        (day / 'rollout-1-main.jsonl').write_text('\n'.join(lines[:5] + lines[7:]) + '\n', encoding='utf-8')
        (day / 'rollout-2-sub.jsonl').write_text('\n'.join(lines[5:7]) + '\n', encoding='utf-8')

    def task(self, proj='proj', task='261001-codex', status='done', log=None):
        d = make_task(self.root / proj, task=task, session=SESSION)
        (d / 'intake.md').write_text(f'Status: {status}\nProfile: general\nRequest: probe\n', encoding='utf-8')
        log = log if log is not None else [f'{T0} step: n=1 name=Intake rev=0 session={SESSION}',
                                           f'{T_END} answer: gate=G3 choice=Accept']
        (d / 'run-log.md').write_text('\n'.join(log) + '\n', encoding='utf-8')
        return d


class ConstantsTest(unittest.TestCase):
    def test_claude_families_unchanged(self):
        self.assertEqual(ma_models.MODELS, ('opus', 'sonnet', 'haiku', 'fable'))
        self.assertEqual(ma_schema.FAMILY.pattern, '(opus|sonnet|haiku|fable)')
        for model in ('gpt-6-luna', 'gpt-5.6-terra', 'codex-auto-review', 'gpt-reserve'):
            self.assertIsNone(ma_schema.family(model), model)
            self.assertIsNotNone(ma_schema.codex_family(model), model)
        self.assertIsNone(ma_schema.codex_family('claude-opus-5-5'))

    def test_expected_main_model_per_host(self):
        self.assertEqual(ma_host.main_family('claude-opus-5-5'), 'opus')
        self.assertEqual(ma_host.main_family('gpt-5.6-terra'), ma_schema.CODEX_DEFAULT)
        self.assertEqual(ma_schema.CODEX_DEFAULT, 'gpt-6-luna')
        self.assertFalse(ma_host.main_mismatch('claude-opus-5-5'))
        self.assertTrue(ma_host.main_mismatch('claude-sonnet-5-5'))
        self.assertFalse(ma_host.main_mismatch('gpt-6-luna'))
        self.assertTrue(ma_host.main_mismatch('gpt-5.6-terra'))

    def test_no_codex_price_row(self):
        prices = ma_prices.load_prices(ma_prices.BUNDLED)
        self.assertFalse([k for k in prices if not k.startswith('claude-')])
        self.assertIsNone(ma_prices.cost(prices, 'gpt-6-luna', {'input_tokens': 5}))


class LocatorTest(Base):
    def test_main_and_subagent_records(self):
        self.records()
        main = ma_host.codex_record(SESSION)
        self.assertEqual(main.name, 'rollout-1-main.jsonl')
        subs = ma_host.codex_subagents(SESSION)
        self.assertEqual([(i, p.name) for i, p, _ in subs], [(SUB, 'rollout-2-sub.jsonl')])
        self.assertIsNone(subs[0][2])   # agent_role is null in the capture
        self.assertIsNone(ma_host.codex_record(SUB.replace('b2', 'ff')))

    def test_subagent_in_the_main_file(self):
        self.records(nested=True)
        subs = ma_host.codex_subagents(SESSION)
        self.assertEqual([(i, p.name) for i, p, _ in subs], [(SUB, 'rollout-1-main.jsonl')])

    def test_unsafe_session_ids(self):
        self.records()
        for bad in ('', None, '*', '../x', 'a/b'):
            self.assertIsNone(ma_host.codex_record(bad))


class UsageTest(Base):
    def test_measure_main_thread_only(self):
        self.records()
        d = self.task()
        sessions, missing, usage = ma_usage.measure(d, self.root / 'claude')
        self.assertEqual((sessions, missing), ([SESSION], []))
        self.assertEqual(usage, {(0, 1): {'gpt-6-luna': {'input_tokens': 400, 'output_tokens': 40,
                                                         'cache_creation_input_tokens': 0,
                                                         'cache_read_input_tokens': 800}}})

    def test_main_thread_only_when_nested(self):
        self.records(nested=True)
        d = self.task()
        usage = ma_usage.measure(d, self.root / 'claude')[2]
        self.assertEqual(usage[(0, 1)]['gpt-6-luna']['output_tokens'], 40)

    def test_each_response_record_is_counted(self):
        self.records()
        main = ma_host.codex_record(SESSION)
        lines = main.read_text(encoding='utf-8').splitlines()
        main.write_text('\n'.join(lines + [lines[3].replace('"ordinal": 3', '"ordinal": 8')]) + '\n', encoding='utf-8')
        usage = ma_usage.measure(self.task(), self.root / 'claude')[2]
        self.assertEqual(usage[(0, 1)]['gpt-6-luna']['output_tokens'], 80)

    def test_missing_record(self):
        d = self.task()
        code, message = ma_usage.write_snapshot(d, self.root / 'claude', datetime(2026, 1, 2))
        self.assertEqual(code, 3)
        self.assertIn(f'no transcript for session {SESSION}', message)

    def test_snapshot_script_unpriced_model(self):
        self.records()
        d = self.task()
        r = run_script(SNAP, '--task-folder', str(d), env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), f'saved: {d / ma_usage.SNAPSHOT} (1 rows)')   # no price: no cost shown
        self.assertEqual(ma_usage.read_snapshot(d)[(0, 1)]['gpt-6-luna']['cache_read_input_tokens'], 800)

    def test_snapshot_with_a_price_row(self):
        self.records()
        d = self.task()
        prices = {'gpt-6-luna': {'input': 1.0, 'output': 2.0, 'cache_write': 1.0, 'cache_read': 0.5}}
        code, message = ma_usage.write_snapshot(d, self.root / 'claude', datetime(2026, 1, 2), prices)
        self.assertEqual(code, 0, message)
        self.assertTrue(message.endswith('(1 rows, ≈ $0.00)'), message)   # (400 + 80 + 400) / 1M

    def test_archive_writes_main_usage(self):
        self.records()
        proj = self.root / 'proj'
        self.task(task='261001-done')
        self.task(task='261001-current', status='active')
        projects = self.root / 'projects.txt'
        projects.write_text(f'{proj}\n', encoding='utf-8')
        r = run_script(ARCHIVE, '--days', '7', env=dict(self.env, MA_PROJECTS_FILE=str(projects)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((records(proj) / '.archived' / '261001-done' / ma_usage.SNAPSHOT).is_file())
        self.assertIn('saved: ', r.stdout)

    def test_claude_snapshot_unchanged(self):
        d = self.task(task='261001-claude', log=['2026-10-01 10:00:00 step: n=1 name=Intake rev=0 session=s-1',
                                                 '2026-10-01 10:20:00 answer: gate=G3 choice=Accept'])
        stamp = datetime.strptime('2026-10-01 10:01:00', '%Y-%m-%d %H:%M:%S').astimezone().isoformat()
        tr = self.root / 'claude' / '-x-proj' / 's-1.jsonl'
        tr.parent.mkdir(parents=True)
        tr.write_text(json.dumps({'type': 'assistant', 'timestamp': stamp, 'message': {
            'id': 'a', 'model': 'claude-opus-5-5', 'usage': {'input_tokens': 10, 'output_tokens': 5}}}) + '\n')
        r = run_script(SNAP, '--task-folder', str(d), env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r'^saved: .*main-usage\.json \(1 rows, ≈ \$\d+\.\d\d\)$')
        self.assertEqual(ma_usage.read_snapshot(d)[(0, 1)]['claude-opus-5-5']['input_tokens'], 10)


class RunLogTest(Base):
    def setUp(self):
        super().setUp()
        self.proj = self.root / 'proj'
        self.d = self.task()
        (self.d / 'run-log.md').write_text('', encoding='utf-8')

    def run_log(self, *args, env=None):
        return run_script(RUNLOG, *args, '--cwd', str(self.proj), env=dict(self.env, **(env or {})))

    def test_step_model_from_the_record(self):
        self.records()
        r = self.run_log('step', 'n=2', 'name=Explore', f'session={SESSION}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('model=gpt-6-luna', log_lines(self.d)[-1])
        self.assertNotIn('MISMATCH', r.stdout)

    def test_mismatch_once_per_task_and_model(self):
        self.records(model='gpt-5.6-terra')
        r = self.run_log('step', 'n=2', 'name=Explore', f'session={SESSION}')
        self.assertIn('MISMATCH: main session configured gpt-6-luna, actual gpt-5.6-terra', r.stdout)
        r = self.run_log('step', 'n=3', 'name=Plan', f'session={SESSION}')
        self.assertNotIn('MISMATCH', r.stdout)

    def test_cost_unpriced_model_writes_nothing(self):
        self.records()
        r = self.run_log('cost')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('run-log: no cost line (gpt-6-luna not in prices.json)', r.stdout)
        self.assertEqual(log_lines(self.d), [])

    def test_cost_from_tokens_and_prices(self):
        self.records()
        data = self.root / 'data'
        data.mkdir()
        (data / 'prices.json').write_text(json.dumps({'models': {'gpt-6-luna': {
            'input': 1000000.0, 'output': 2000000.0, 'cache_write': 0.0, 'cache_read': 500000.0}}}), encoding='utf-8')
        r = self.run_log('cost', env={'MA_TASKS_DIR': str(data)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(log_lines(self.d)[-1], rf'cost: session={SESSION} usd=880(\.0)?$')

    def test_claude_session_cost_source_unchanged(self):
        r = self.run_log('cost', env={'CLAUDE_CODE_SESSION_ID': 's-9'})
        self.assertIn('run-log: no cost line (', r.stdout)
        self.assertNotIn('prices.json', r.stdout)


class GateReportTest(Base):
    def setUp(self):
        super().setUp()
        self.proj = self.root / 'proj'
        self.d = self.task()

    def gate(self, command):
        return run_script(GATE, command, '--cwd', str(self.proj), env=self.env)

    def log(self, *lines):
        with open(self.d / 'run-log.md', 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    def mismatches(self, model):
        self.log(f'2026-10-26 23:00:00 step: n=3 name=X model={model} session={SESSION}')
        r = self.gate('tally')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return re.search(r'\| Model mismatches \| (\d+)', r.stdout).group(1)

    def test_model_check(self):
        self.assertEqual(self.mismatches('gpt-6-luna'), '0')
        self.assertEqual(self.mismatches('gpt-5.6-terra'), '1')

    def test_model_check_claude(self):
        self.assertEqual(self.mismatches('claude-opus-5-5'), '0')
        self.assertEqual(self.mismatches('claude-sonnet-5-5'), '1')

    def test_check_finds_subagent_records(self):
        self.records(role='my_agent_coder')
        self.log(f'2026-01-01 05:00:00 start: agent=my-agent:coder id={SUB} session={SESSION}',
                 f'2026-01-01 05:01:00 stop: id={SUB} mode=auto')
        r = self.gate('check')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('summary: transcripts 1 (other 0, untyped 0), start lines 1, missing 0, non-auto stops 0', r.stdout)

    def test_check_missing_start(self):
        self.records(role='my_agent_coder')
        r = self.gate('check')
        self.assertRegex(r.stdout, rf'missing start: id={SUB} agent=my-agent:coder transcript=.*rollout-2-sub\.jsonl')
        self.assertIn('summary: transcripts 1 (other 0, untyped 0), start lines 0, missing 1, non-auto stops 0', r.stdout)

    def test_check_untyped_subagent(self):
        self.records()
        r = self.gate('check')
        self.assertIn(f'missing start: id={SUB} agent=unknown', r.stdout)
        self.assertIn('untyped 1', r.stdout)

    def test_check_other_agent_is_counted(self):
        self.records(role='explorer')
        self.assertIn('transcripts 1 (other 1, untyped 0)', self.gate('check').stdout)


if __name__ == '__main__':
    unittest.main()

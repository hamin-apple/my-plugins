"""run-log.py: the L1 Recorder's CLI (architecture 4.7.2 "who records what", P9)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import L4, events, log_lines, make_task, parse, run_script

SCRIPT = L4 / 'scripts' / 'run-log.py'


class RunLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.task = make_task(self.root, session='s-active')
        (self.root / 'statusline-empty').mkdir()   # no test reads the real ~/.cache statusline file
        self.env = {'MA_TASKS_DIR': str(self.root / 'none'), 'CLAUDE_CODE_SESSION_ID': 's-9',
                    'MA_CLAUDE_PROJECTS': str(self.root / 'projects'),
                    'MA_STATUSLINE_DIR': str(self.root / 'statusline-empty')}

    def tearDown(self):
        self.tmp.cleanup()

    def run_log(self, *args, env=None):
        return run_script(SCRIPT, *args, '--cwd', str(self.root), env=dict(self.env, **(env or {})))

    def test_step_fills_rev_and_session(self):
        (self.task / 'run-log.md').write_text('2026-10-25 09:00:00 revision: rev=1 why=x\n')
        r = self.run_log('step', 'n=3', 'name=Plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['n'], f['name'], f['rev'], f['session']), ('3', 'Plan', '1', 's-9'))
        self.assertEqual(events(self.task).step_enter[-1][1], 3)
        self.assertIn(log_lines(self.task)[-1], r.stdout)

    def test_task_dir_option_finds_docs_agent_task(self):
        other = self.root / 'other'
        task = make_task(other, sub='docs/agent')
        drop = ('MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_TASK_DIR')
        r = run_script(SCRIPT, 'step', 'n=1', 'name=Intake', '--cwd', str(other), env=self.env, drop=drop)
        self.assertEqual(r.returncode, 1, r.stdout)
        r = run_script(SCRIPT, 'step', 'n=1', 'name=Intake', '--task-dir', 'docs/agent', '--cwd', str(other),
                       env=self.env, drop=drop)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(log_lines(task)), 1)

    def test_step_session_from_active_without_env(self):
        r = self.run_log('step', 'n=1', 'name=Intake', env={'CLAUDE_CODE_SESSION_ID': ''})
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['rev'], f['session']), ('0', 's-active'))

    def test_step_needs_n_and_name(self):
        r = self.run_log('step', 'n=3')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(log_lines(self.task), [])

    def test_ask_answer_pair(self):
        self.assertEqual(self.run_log('ask', 'gate=G1b', 'q=Approve the plan?').returncode, 0)
        ev = events(self.task)
        self.assertEqual(ev.gates.get('G1b'), 'wait')
        self.assertEqual(self.run_log('answer', 'gate=G1b', 'choice=Approve').returncode, 0)
        ev = events(self.task)
        self.assertEqual(ev.answered['G1b'], 'Approve')
        self.assertNotEqual(ev.gates.get('G1b'), 'wait')

    def test_ask_answer_get_session(self):
        self.run_log('ask', 'gate=G3', 'q=x')
        self.run_log('answer', 'gate=G3', 'choice=Accept')
        self.assertEqual([parse(l)['session'] for l in log_lines(self.task)], ['s-9', 's-9'])
        self.run_log('ask', 'gate=G3', 'q=x', env={'CLAUDE_CODE_SESSION_ID': ''})
        self.assertEqual(parse(log_lines(self.task)[-1])['session'], 's-active')
        self.run_log('answer', 'gate=G3', 'choice=Accept', 'session=given')
        self.assertEqual(parse(log_lines(self.task)[-1])['session'], 'given')

    def test_qn_prose_pre_pass_through(self):
        self.run_log('ask', 'gate=Q', 'qn=2', 'q=x', 'rec=-')
        self.run_log('answer', 'gate=Q', 'qn=2', 'choice=a', 'prose=1')
        self.run_log('answer', 'gate=Q', 'choice=b', 'pre=1')
        a, b, c = (parse(l) for l in log_lines(self.task))
        self.assertEqual(a['qn'], '2')
        self.assertEqual((b['qn'], b['prose']), ('2', '1'))
        self.assertEqual(c['pre'], '1')

    def statusline(self, name, text):
        d = self.root / 'statusline'
        d.mkdir(exist_ok=True)
        (d / f'{name}.json').write_text(text)
        return {'MA_STATUSLINE_DIR': str(d)}

    def test_cost_reads_statusline_file(self):
        env = self.statusline('s-active', '{"cost_usd": 1.25}')
        r = self.run_log('cost', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['session'], f['usd']), ('s-active', '1.25'))
        self.assertNotIn('reset', f)

    def test_cost_session_from_env_without_active_session(self):
        make_task(self.root, session='')
        env = self.statusline('s-9', '{"cost_usd": 2}')
        self.assertEqual(self.run_log('cost', env=env).returncode, 0)
        self.assertEqual(parse(log_lines(self.task)[-1])['session'], 's-9')

    def test_cost_reset_when_lower(self):
        env = self.statusline('s-active', '{"cost_usd": 3.0}')
        self.run_log('cost', env=env)
        self.statusline('s-active', '{"cost_usd": 0.5}')
        self.run_log('cost', env=env)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['usd'], f['reset']), ('0.5', '1'))
        self.statusline('s-active', '{"cost_usd": 0.7}')
        self.run_log('cost', env=env)
        self.assertNotIn('reset', parse(log_lines(self.task)[-1]))

    def test_cost_skips_missing_and_bad_file(self):
        env = {'MA_STATUSLINE_DIR': str(self.root / 'nodir')}
        r = self.run_log('cost', env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn('run-log: no cost line (', r.stdout)
        for text in ('{oops', '{"cost_usd": "x"}', '{}', '[1]', '{"cost_usd": true}'):
            r = self.run_log('cost', env=self.statusline('s-active', text))
            self.assertEqual(r.returncode, 0, text)
            self.assertIn('run-log: no cost line (', r.stdout, text)
        self.assertEqual(log_lines(self.task), [])

    def test_cost_rejects_typed_values(self):
        env = self.statusline('s-active', '{"cost_usd": 1}')
        for arg in ('usd=5', 'session=s-x'):
            r = self.run_log('cost', arg, env=env)
            self.assertEqual(r.returncode, 2, arg)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertEqual(log_lines(self.task), [])

    def test_cost_rejects_baseline(self):
        env = self.statusline('s-active', '{"cost_usd": 1}')
        r = self.run_log('cost', 'baseline=1', env=env)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertEqual(log_lines(self.task), [])

    def test_step_1_writes_baseline_cost_line(self):
        env = self.statusline('s-active', '{"cost_usd": 0.4}')
        r = self.run_log('step', 'n=1', 'name=Intake', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = log_lines(self.task)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1].split()[2], 'cost:')
        f = parse(lines[1])
        self.assertEqual((f['session'], f['usd'], f['baseline']), ('s-active', '0.4', '1'))
        self.assertEqual(r.stdout.splitlines()[:2], lines)

    def test_step_1_without_statusline_file_writes_one_line(self):
        r = self.run_log('step', 'n=1', 'name=Intake')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(log_lines(self.task)), 1)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)
        r = self.run_log('step', 'n=1', 'name=Intake', env=self.statusline('s-active', '{oops'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(log_lines(self.task)), 2)

    def test_other_steps_never_write_baseline(self):
        env = self.statusline('s-active', '{"cost_usd": 0.4}')
        self.assertEqual(self.run_log('step', 'n=3', 'name=Plan', env=env).returncode, 0)
        self.assertEqual(len(log_lines(self.task)), 1)

    def test_second_step_1_after_a_cost_line_writes_no_baseline(self):
        env = self.statusline('s-active', '{"cost_usd": 0.4}')
        self.run_log('step', 'n=1', 'name=Intake', env=env)
        self.run_log('step', 'n=1', 'name=Intake', env=env)
        self.assertEqual([l.split()[2] for l in log_lines(self.task)], ['step:', 'cost:', 'step:'])

    def test_ask_rejects_answer_only_fields(self):
        for field in ('prose=1', 'other=1', 'pre=1'):
            r = self.run_log('ask', 'gate=Q', 'q=Change kind', field)
            self.assertEqual(r.returncode, 1, field)
            self.assertIn('prose=, other= and pre= go on the answer line, not on ask', r.stderr)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1)
            self.assertEqual(log_lines(self.task), [], field)

    def test_ask_rejection_comes_before_the_task_lookup(self):
        r = run_script(SCRIPT, 'ask', 'gate=Q', 'q=x', 'pre=1', '--cwd', str(self.root / 'nowhere'), env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn('go on the answer line', r.stderr)

    def test_answer_still_takes_prose(self):
        r = self.run_log('answer', 'gate=Q', 'choice=a', 'prose=1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(parse(log_lines(self.task)[-1])['prose'], '1')

    def test_value_with_quotes(self):
        self.run_log('fix', 'what=say "hi" \\ there')
        self.assertEqual(parse(log_lines(self.task)[-1])['what'], 'say "hi" \\ there')

    def test_delegate_and_profile_kinds(self):
        self.assertEqual(self.run_log('delegate', 'state=on', 'how=flag').returncode, 0)
        self.assertEqual(self.run_log('profile', 'from=dev', 'to=general', 'back=2', 'archive=-').returncode, 0)
        d, p = (parse(l) for l in log_lines(self.task)[-2:])
        self.assertEqual((d['state'], d['how']), ('on', 'flag'))
        self.assertEqual((p['from'], p['to'], p['back']), ('dev', 'general', '2'))

    def test_delegate_and_profile_need_their_fields(self):
        for args in (('delegate', 'how=flag'), ('delegate', 'state=maybe'), ('profile', 'from=dev'), ('profile', 'to=dev')):
            self.assertEqual(self.run_log(*args).returncode, 2, args)
        self.assertEqual(log_lines(self.task), [])

    def inline(self, *args):
        return self.run_log('inline', *args, '--model', 'claude-opus-5-5')

    def test_inline_verifier_takes_result_from_file(self):
        vf = self.task / 'verify.md'
        vf.write_text('Verdict: ALL PASS\nmore\n')
        r = self.inline('agent=my-agent:verifier', f'file={vf}')
        self.assertEqual(r.returncode, 0, r.stderr)
        line = log_lines(self.task)[-1]
        f = parse(line)
        self.assertEqual((f['agent'], f['unit'], f['file'], f['result'], f['model']),
                         ('my-agent:verifier', '-', str(vf), 'Verdict: ALL PASS', 'claude-opus-5-5'))
        self.assertEqual(list(f)[:5], ['agent', 'unit', 'file', 'result', 'model'])
        self.assertIn(' inline: agent=my-agent:verifier unit=- file=', line)

    def test_inline_result_is_cut_to_200_characters(self):
        vf = self.task / 'review.md'
        vf.write_text('x' * 300 + '\n')
        self.assertEqual(self.inline('agent=my-agent:reviewer', f'file={vf}').returncode, 0)
        self.assertEqual(len(parse(log_lines(self.task)[-1])['result']), 200)

    def test_inline_coder_has_no_file_and_gives_result(self):
        r = self.inline('agent=my-agent:coder', 'unit=u2', 'file=-', 'result=DONE')
        self.assertEqual(r.returncode, 0, r.stderr)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['agent'], f['unit'], f['file'], f['result']), ('my-agent:coder', 'u2', '-', 'DONE'))

    def test_inline_refusals(self):
        vf = self.task / 'verify.md'
        vf.write_text('Verdict: ALL PASS\n')
        cases = [(('file=-',), 2), (('agent=my-agent:verifier',), 2),
                 (('agent=my-agent:main', f'file={vf}'), 2), (('agent=my-agent:nobody', f'file={vf}'), 2),
                 (('agent=my-agent:verifier', 'file=-'), 2), (('agent=my-agent:coder', 'file=-'), 2),
                 (('agent=my-agent:verifier', f'file={vf}', 'result=Verdict: ALL PASS'), 2),
                 (('agent=my-agent:verifier', f'file={self.task / "missing.md"}'), 1)]
        for args, code in cases:
            r = self.inline(*args)
            self.assertEqual(r.returncode, code, (args, r.stdout, r.stderr))
        self.assertEqual(log_lines(self.task), [])
        self.assertIn('inline needs the result file', r.stderr + r.stdout)
        self.assertIn('(missing)', r.stderr + r.stdout)

    def test_models_kind(self):
        self.assertEqual(self.run_log('models', 'preset=economy', 'source=file').returncode, 0)
        f = parse(log_lines(self.task)[-1])
        self.assertEqual((f['preset'], f['source']), ('economy', 'file'))
        self.assertIn('models: preset=economy source=file', log_lines(self.task)[-1])

    def test_models_needs_preset_and_source(self):
        for args in (('models', 'source=file'), ('models', 'preset=economy'), ('models',)):
            r = self.run_log(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertEqual(len(r.stderr.splitlines()), 1, r.stderr)
        self.assertEqual(log_lines(self.task), [])

    def test_unknown_kind(self):
        r = self.run_log('bogus', 'a=1')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(log_lines(self.task), [])

    def test_bad_field(self):
        r = self.run_log('fix', 'noequals')
        self.assertEqual(r.returncode, 2)

    def test_main_mismatch(self):
        r = self.run_log('step', 'n=1', 'name=Intake', '--model', 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')
        r = self.run_log('step', 'n=2', 'name=Explore', '--model', 'claude-opus-5-5')
        self.assertNotIn('MISMATCH', r.stdout)

    def test_main_model_read_from_transcript(self):
        # live run: the skill's `model: opus` held for the first turn only (F13); later turns ran on Sonnet,
        # yet L1 kept passing --model claude-opus-5-5, so the check never fired
        t = self.root / 'projects' / '-x-proj' / 's-9.jsonl'
        t.parent.mkdir(parents=True)
        rows = [{'type': 'assistant', 'isSidechain': False, 'message': {'model': 'claude-opus-5-5'}},
                {'type': 'user', 'message': {'content': 'x'}},
                {'type': 'assistant', 'isSidechain': False, 'message': {'model': 'claude-sonnet-5-5'}},
                {'type': 'assistant', 'isSidechain': True, 'message': {'model': 'claude-opus-5-5'}},
                {'type': 'assistant', 'isSidechain': False, 'message': {'model': '<synthetic>'}}]
        t.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        r = self.run_log('step', 'n=3', 'name=Plan', '--model', 'claude-opus-5-5')
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        r = self.run_log('ask', 'gate=G3', 'q=x')     # only step lines (or an explicit --model) carry the model
        self.assertNotIn('model', parse(log_lines(self.task)[-1]))
        self.assertNotIn('MISMATCH', r.stdout)

    def test_main_mismatch_reported_once_per_model(self):
        r = self.run_log('step', 'n=2', 'name=Explore-Scope', '--model', 'claude-sonnet-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-sonnet-5-5', r.stdout)
        r = self.run_log('step', 'n=3', 'name=Plan', '--model', 'claude-sonnet-5-5')
        self.assertNotIn('MISMATCH', r.stdout)
        self.assertEqual(parse(log_lines(self.task)[-1])['model'], 'claude-sonnet-5-5')   # still recorded
        r = self.run_log('step', 'n=4', 'name=Plan-Review', '--model', 'claude-haiku-5-5')
        self.assertIn('MISMATCH: main session configured opus, actual claude-haiku-5-5', r.stdout)

    def test_reports_subagent_mismatch_once(self):
        (self.task / 'run-log.md').write_text(
            '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=s\n'
            '2026-10-25 09:00:01 start: agent=my-agent:coder id=a1 configured=sonnet effort=medium\n'
            '2026-10-25 09:00:09 stop: id=a1 actual=claude-opus-5-5 tokens=10 in=1 out=1 cw=1 cr=7 secs=8 '
            'result=DONE end=ok mismatch=1\n')
        r = self.run_log('step', 'n=6', 'name=Merge')
        self.assertIn('MISMATCH: my-agent:coder configured sonnet, actual claude-opus-5-5', r.stdout)
        r = self.run_log('step', 'n=7', 'name=Verify')
        self.assertNotIn('MISMATCH', r.stdout)

    def test_guard_line_does_not_hide_subagent_mismatch(self):
        (self.task / 'run-log.md').write_text(
            '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=s\n'
            '2026-10-25 09:00:01 start: agent=my-agent:coder id=a1 configured=sonnet effort=medium\n'
            '2026-10-25 09:00:09 stop: id=a1 actual=claude-opus-5-5 tokens=10 in=1 out=1 cw=1 cr=7 secs=8 '
            'result=DONE end=ok mismatch=1\n'
            '2026-10-25 09:00:10 guard: hook=scope-guard agent=my-agent:coder id=a2 tool=Bash decision=deny why=x\n')
        r = self.run_log('step', 'n=6', 'name=Merge')
        self.assertIn('MISMATCH: my-agent:coder configured sonnet, actual claude-opus-5-5', r.stdout)

    def test_data_dir_finds_run_index(self):
        """A run folder outside git is found through <data folder>/active-index.json."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            task = make_task(base / 'loc', session='s-x')
            data, run = base / 'data', base / 'run'
            data.mkdir()
            run.mkdir()
            (data / 'active-index.json').write_text(json.dumps({str(run): str(base / 'loc')}), encoding='utf-8')
            env = dict(self.env, MA_TASKS_DIR='')
            r = run_script(SCRIPT, 'ask', 'gate=G1', '--cwd', str(run), '--data-dir', str(data), env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('ask:', log_lines(task)[-1])

    def test_no_active(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_script(SCRIPT, 'step', 'n=1', 'name=Intake', '--cwd', d, env=self.env)
            self.assertEqual(r.returncode, 1)
            self.assertIn('run-log: no active my-agent task under', r.stdout)
            self.assertEqual(list(Path(d).iterdir()), [])


if __name__ == '__main__':
    unittest.main()

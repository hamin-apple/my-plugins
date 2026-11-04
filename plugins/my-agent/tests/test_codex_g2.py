"""Codex G2 (criterion 7): a gate hook's ask is exit 2, and one `answer gate=G2` line releases exactly one call.

The real hook scripts run with Codex-shaped inputs on a temp task; the answer is written by the real `run-log.py` from
the command the hook's stderr prints."""
import os
import re
import shlex
import subprocess
import time
import unittest

from helpers import log_lines, parse, run_hook
from test_codex_guards import Base, fixture, patch

import ma_logline

SID = '019a0000-0000-7000-8000-000000000001'
OUTSIDE = 'src/x.py'


def command_of(stderr: str) -> str:
    m = re.search(r'record the answer with (.*?) \(result=denied for Deny\)', stderr, re.S)
    assert m, stderr
    return m.group(1)


class G2Base(Base):
    def setUp(self):
        super().setUp()
        self.t0 = time.time() - 1000

    def gate(self, payload):
        return self.run_it('plan-approved-check.py', payload)

    def vfc(self, payload):
        return self.run_it('verdict-fresh-check.py', payload)

    def bash(self, cmd, **over):
        return fixture('hook-pre-tool-use-bash.json', tool_input={'command': cmd}, **over)

    def patch_in(self, path=OUTSIDE):
        return self.main_file(patch(f'*** Add File: {path}', '+x'))

    def lines(self, kind):
        return [parse(x) for x in log_lines(self.T) if f' {kind}: ' in x]

    def kinds(self):
        return [x.split(' ', 2)[2].split(':')[0] for x in log_lines(self.T)]

    def answer(self, stderr, result='allowed'):
        """Run the printed answer command as an argument list, from a folder that is not the task's."""
        argv = [a.replace('result=allowed', f'result={result}') for a in shlex.split(command_of(stderr))]
        r = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=dict(os.environ, **self.env))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def write_answer(self, *fields):
        with open(self.T / 'run-log.md', 'a', encoding='utf-8') as f:
            f.write(ma_logline.format_line('answer', [('gate', 'G2'), *fields]) + '\n')

    def blocked(self, r, hook='plan-approved-check'):
        self.assertEqual((r.returncode, r.stdout), (2, ''), r.stderr)
        self.assertTrue(r.stderr.startswith(f'my-agent G2 ({hook}): '), r.stderr)
        return r.stderr

    def passed(self, r):
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def file(self, path, text, at):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        os.utime(path, (self.t0 + at, self.t0 + at))

    def stale_verdicts(self):
        self.file(self.T / 'verify.md', 'Verdict: ALL PASS\n', 10)
        self.file(self.T / 'review.md', 'BLOCKER 0\n', 10)
        self.file(self.L / 'src/a.py', 'x', 30)


class AskIsExit2Test(G2Base):
    def test_apply_patch_outside_before_approval(self):
        r = self.gate(self.patch_in())
        err = self.blocked(r)
        for text in ('G2 popup', 'Allow once', 'Deny', 'plan gate: write outside the task folder',
                     'gate=G2 tool=apply_patch q=src/x.py key=', f'--cwd "{self.L}"', '--data-dir "', '--task-dir ".my-agent"',
                     'retry the same call unchanged'):
            self.assertIn(text, err)
        ask = self.lines('ask')
        self.assertEqual(len(ask), 1)
        self.assertEqual((ask[0]['gate'], ask[0]['agent'], ask[0]['id'], ask[0]['tool'], ask[0]['q'], ask[0]['hook'],
                          ask[0]['session']), ('G2', 'main', '-', 'apply_patch', 'src/x.py', 'plan-approved-check', SID))
        self.assertRegex(ask[0]['key'], r'^[0-9a-f]{16}$')
        self.assertIn(f'key={ask[0]["key"]} result=allowed', err)

    def test_bash_write_outside_and_main_session_shape(self):
        err = self.blocked(self.gate(self.bash('echo x > src/y.txt')))
        self.assertIn('tool=Bash q=\'echo x > src/y.txt\' key=', err)
        ask = self.lines('ask')
        self.assertEqual((ask[0]['tool'], ask[0]['q'], ask[0]['hook']), ('Bash', 'echo x > src/y.txt', 'plan-approved-check'))
        shaped = self.bash('echo x > src/y.txt')
        self.assertNotIn('agent_id', shaped)
        self.assertNotIn('agent_type', shaped)
        self.assertIn('turn_id', shaped)

    def test_quoted_multiline_command_round_trips(self):
        cmd = 'echo "a b" > \'src/it\'"\'"\'s.txt\'\necho done'
        err = self.blocked(self.gate(self.bash(cmd)))
        self.answer(err)
        ask, ans = self.lines('ask')[0], self.lines('answer')[0]
        self.assertEqual(ask['q'], ans['q'])
        self.assertEqual(ask['key'], ans['key'])
        self.assertNotIn('\n', ask['q'])
        self.passed(self.gate(self.bash(cmd)))
        self.assertEqual(len(self.lines('release')), 1)

    def test_long_command_cut_but_keyed_by_full_text(self):
        head = 'echo ' + 'a' * 210
        e1 = self.blocked(self.gate(self.bash(head + ' > src/one.txt')))
        e2 = self.blocked(self.gate(self.bash(head + ' > src/two.txt')))
        a, b = self.lines('ask')
        self.assertTrue(a['q'].endswith('…'))
        self.assertEqual(len(a['q']), 200)
        self.assertEqual(a['q'], b['q'])
        self.assertNotEqual(a['key'], b['key'])
        self.assertNotEqual(command_of(e1), command_of(e2))

    def test_deny_stays_deny(self):
        self.stale_verdicts()
        r = self.vfc(self.main_file(patch(f'*** Add File: {self.T}/deliverable/out.md', '+x')))
        self.assertEqual((r.returncode, r.stdout), (2, ''))
        self.assertIn('G3', r.stderr)
        self.assertFalse(r.stderr.startswith('my-agent G2'))
        spawn = fixture('hook-pre-tool-use-spawn-agent.json')
        spawn['tool_input']['agent_type'] = 'my-agent-coder'
        d = self.gate(spawn)
        self.assertEqual(d.returncode, 0)
        self.assertIn('"permissionDecision": "deny"', d.stdout)
        self.assertEqual(self.lines('ask'), [])

    def test_no_active_task_passes_and_writes_nothing(self):
        (self.T.parent / '.active').unlink()
        self.passed(self.gate(self.patch_in()))
        self.passed(self.gate(self.bash('echo x > src/y.txt')))
        self.assertEqual(log_lines(self.T), [])

    def test_claude_shape_keeps_json_ask_and_writes_no_line(self):
        env = dict(self.env, MA_HOST='claude')
        claude = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'session_id': SID,
                  'tool_input': {'command': 'echo x > src/y.txt'}}
        r = run_hook('plan-approved-check.py', None, claude, self.L, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"permissionDecision": "ask"', r.stdout)
        self.assertIn('"permissionDecisionReason": "my-agent plan gate:', r.stdout)
        self.assertEqual(r.stderr, '')
        self.assertEqual(log_lines(self.T), [])


class OneAnswerOneCallTest(G2Base):
    def test_answer_releases_exactly_one_call(self):
        err = self.blocked(self.gate(self.patch_in()))
        self.answer(err)
        self.passed(self.gate(self.patch_in()))
        self.assertEqual(self.kinds(), ['ask', 'answer', 'release'])
        rel = self.lines('release')[0]
        self.assertEqual((rel['gate'], rel['hook'], rel['tool'], rel['session']),
                         ('G2', 'plan-approved-check', 'apply_patch', SID))
        self.assertEqual(rel['key'], self.lines('ask')[0]['key'])
        again = self.gate(self.patch_in())
        self.blocked(again)
        self.assertEqual(self.kinds(), ['ask', 'answer', 'release', 'ask'])

    def test_q_is_not_compared(self):
        err = self.blocked(self.gate(self.bash('echo x > src/y.txt')))
        key = self.lines('ask')[0]['key']
        for fields in ((('tool', 'Bash'), ('q', 'something else'), ('key', key), ('result', 'allowed')),
                       (('tool', 'Bash'), ('key', key), ('result', 'allowed'))):
            with self.subTest(fields=fields):
                self.write_answer(*fields)
                self.passed(self.gate(self.bash('echo x > src/y.txt')))
                self.blocked(self.gate(self.bash('echo x > src/y.txt')))
        self.assertIn('Allow once', err)

    def test_other_target_or_tool_is_blocked_and_first_still_passes_once(self):
        err = self.blocked(self.gate(self.patch_in()))
        self.answer(err)
        other = self.blocked(self.gate(self.patch_in('src/other.py')))
        self.assertNotEqual(command_of(err), command_of(other))
        as_bash = self.blocked(self.gate(self.bash('echo x > src/x.py')))
        self.assertIn('tool=Bash', as_bash)
        keys = [a['key'] for a in self.lines('ask')]
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(self.lines('release'), [])
        self.passed(self.gate(self.patch_in()))
        self.blocked(self.gate(self.patch_in()))

    def test_newest_ask_only(self):
        ex = self.blocked(self.gate(self.bash('echo x > src/x.txt')))
        ey = self.blocked(self.gate(self.bash('echo y > src/y.txt')))
        self.answer(ex)
        again = self.blocked(self.gate(self.bash('echo x > src/x.txt')))
        keys = {a['q']: a['key'] for a in self.lines('ask')}
        self.assertRegex(again, r'The G2 answer line of \d\d:\d\d:\d\d was not used: it answers Bash '
                         + keys['echo x > src/x.txt'] + ', but the newest open ask is Bash '
                         + keys['echo y > src/y.txt'] + r'\.$')
        # the answer for the newest ask (the retried X was asked again after it, so answer that one)
        self.answer(again)
        self.passed(self.gate(self.bash('echo x > src/x.txt')))
        self.assertIn('tool=Bash', ey)

    def test_answer_for_newest_passes_older_stays_open(self):
        ex = self.blocked(self.gate(self.bash('echo x > src/x.txt')))
        ey = self.blocked(self.gate(self.bash('echo y > src/y.txt')))
        self.answer(ey)
        self.passed(self.gate(self.bash('echo y > src/y.txt')))
        self.blocked(self.gate(self.bash('echo y > src/y.txt')))
        self.assertIn('Allow once', ex)

    def test_malformed_answers_are_ignored_with_a_reason(self):
        self.blocked(self.gate(self.bash('echo x > src/y.txt')))
        key = self.lines('ask')[0]['key']
        for fields, why in (
                ((('tool', 'Bash'), ('result', 'allowed')), 'it has no key='),
                ((('tool', 'Bash'), ('key', 'abc123'), ('result', 'allowed')), 'its key is not 16 hex digits'),
                ((('key', key), ('result', 'allowed')), 'it has no tool='),
                ((('tool', 'Bash'), ('key', key), ('result', 'maybe')), 'its result is maybe')):
            with self.subTest(why=why):
                self.write_answer(*fields)
                err = self.blocked(self.gate(self.bash('echo x > src/y.txt')))
                self.assertRegex(err, r'The G2 answer line of \d\d:\d\d:\d\d was not used: ' + re.escape(why) + r'\.$')
        self.assertEqual(self.lines('release'), [])

    def test_denied_closes_the_ask_and_releases_nothing(self):
        err = self.blocked(self.gate(self.patch_in()))
        self.answer(err, 'denied')
        self.assertEqual(self.lines('answer')[0]['result'], 'denied')
        again = self.blocked(self.gate(self.patch_in()))
        self.assertNotIn('was not used', again)
        self.assertEqual(self.kinds(), ['ask', 'answer', 'ask'])

    def test_answer_without_open_ask_is_not_used(self):
        self.write_answer(('tool', 'Bash'), ('key', '0123456789abcdef'), ('result', 'allowed'))
        err = self.blocked(self.gate(self.patch_in()))
        self.assertNotIn('was not used', err)

    def test_verdict_fresh_check_asks_and_one_answer_releases(self):
        self.stale_verdicts()
        cmd = self.bash('git commit -m x')
        err = self.blocked(self.vfc(cmd), 'verdict-fresh-check')
        self.assertIn('my-agent verdict gate: review.md is older than src/a.py', err)
        self.assertEqual(self.lines('ask')[0]['hook'], 'verdict-fresh-check')
        self.answer(err)
        self.passed(self.vfc(cmd))
        self.blocked(self.vfc(cmd), 'verdict-fresh-check')

    def test_both_hooks_on_one_call(self):
        self.stale_verdicts()
        cmd = self.bash('git commit -m x')
        ea = self.blocked(self.gate(cmd))
        eb = self.blocked(self.vfc(cmd), 'verdict-fresh-check')
        self.assertEqual([a['hook'] for a in self.lines('ask')], ['plan-approved-check', 'verdict-fresh-check'])
        self.assertEqual(self.lines('ask')[0]['key'], self.lines('ask')[1]['key'])
        self.answer(eb)
        self.passed(self.gate(cmd))
        self.passed(self.vfc(cmd))
        self.assertEqual([x['hook'] for x in self.lines('release')], ['plan-approved-check', 'verdict-fresh-check'])
        self.blocked(self.gate(cmd))
        self.blocked(self.vfc(cmd), 'verdict-fresh-check')
        self.assertIn('Allow once', ea)

    def test_unwritable_run_log_blocks(self):
        err = self.blocked(self.gate(self.patch_in()))
        self.answer(err)
        log = self.T / 'run-log.md'
        log.chmod(0o444)
        try:
            if os.access(log, os.W_OK):
                self.skipTest('run-log stays writable (root)')
            r = self.gate(self.patch_in())
            self.assertEqual((r.returncode, r.stdout), (2, ''))
            self.assertIn('my-agent G2 (plan-approved-check): ', r.stderr)
            self.assertIn('Permission', r.stderr)
        finally:
            log.chmod(0o644)
        self.assertEqual(self.lines('release'), [])

    def test_unreadable_run_log_blocks(self):
        (self.T / 'run-log.md').mkdir()
        r = self.gate(self.patch_in())
        self.assertEqual((r.returncode, r.stdout), (2, ''))
        self.assertTrue(r.stderr.startswith('my-agent G2 (plan-approved-check): '), r.stderr)
        self.assertIn('Is a directory', r.stderr)


if __name__ == '__main__':
    unittest.main()

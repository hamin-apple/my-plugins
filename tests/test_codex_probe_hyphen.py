"""tools/codex-probe/probe-hyphen.py: run and outcome with a fake codex, every outcome class, no write outside <dir>."""
import importlib.util
import json
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / 'tools' / 'codex-probe' / 'probe-hyphen.py'

spec = importlib.util.spec_from_file_location('probe_hyphen', PROBE)
hyphen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hyphen)

FAKE = '''#!{py}
import json, os, sys
with open({log!r}, 'a') as f:
    f.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}) + '\\n')
if sys.argv[1:2] == ['--version']:
    print('codex-cli 9.9.9')
elif sys.argv[1:2] == ['exec']:
    with open({events!r}) as f:
        sys.stdout.write(f.read())
    sys.stderr.write('some stderr\\n')
'''
THREAD = 'thread-12345678'


def spawn_lines(agent, output, call_id='c1'):
    call = {'type': 'response_item', 'payload': {
        'type': 'function_call', 'name': 'spawn_agent', 'call_id': call_id,
        'arguments': json.dumps({'agent_type': agent, 'task_name': 'hyphen_probe', 'message': 'x'})}}
    result = {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': call_id, 'output': output}}
    return [json.dumps({'type': 'session_meta', 'payload': {'id': THREAD}}), json.dumps(call), json.dumps(result)]


def snapshot(root: Path):
    return sorted((str(p.relative_to(root)), p.read_bytes() if p.is_file() else None) for p in root.rglob('*'))


class HyphenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / 'codex-home'
        (self.home / 'agents').mkdir(parents=True)
        (self.home / 'agents' / 'keep.toml').write_text('name = "keep"\n', encoding='utf-8')
        (self.home / 'sessions' / '2026' / '01').mkdir(parents=True)
        self.other = self.home / 'sessions' / '2026' / '01' / 'rollout-other-aaaaaaaa.jsonl'
        self.other.write_text('{"unrelated": true}\n', encoding='utf-8')
        self.events_file = self.tmp / 'events.jsonl'
        self.events_file.write_text('', encoding='utf-8')
        self.log = self.tmp / 'fake-calls.jsonl'
        self.fake = self.tmp / 'fake-codex'
        self.fake.write_text(FAKE.format(py=sys.executable, log=str(self.log), events=str(self.events_file)),
                             encoding='utf-8')
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.out = self.tmp / 'out'

    def session(self, lines):
        path = self.home / 'sessions' / '2026' / '01' / f'rollout-2026-01-01T00-00-00-{THREAD}.jsonl'
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def events(self, lines=None):
        lines = [json.dumps({'type': 'thread.started', 'thread_id': THREAD})] if lines is None else lines
        self.events_file.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')

    def run_probe(self, *extra, codex=None):
        code = hyphen.main(['--codex', str(codex or self.fake), '--codex-home', str(self.home),
                            'run', str(self.out)] + list(extra))
        hyphen.main(['--codex', str(codex or self.fake), '--codex-home', str(self.home), 'outcome', str(self.out)])
        return code

    def first_line(self):
        return (self.out / 'outcome.md').read_text(encoding='utf-8').splitlines()[0]

    def test_accepted(self):
        self.events()
        self.session(spawn_lines('my-explorer', json.dumps({'agent_id': 'a1'})))
        self.assertEqual(self.run_probe(), 0)
        self.assertEqual(self.first_line(), 'Outcome: accepted')
        text = (self.out / 'outcome.md').read_text(encoding='utf-8')
        self.assertIn('Agent type: my-explorer', text)
        self.assertIn('Codex: codex-cli 9.9.9', text)
        self.assertIn('Evidence: sessions/rollout-2026-01-01T00-00-00-thread-12345678.jsonl line 2', text)

    def test_refused(self):
        self.events()
        self.session(spawn_lines('my-explorer', 'unknown agent_type my-explorer'))
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: refused')

    def test_task_name_rejected(self):
        self.events()
        self.session(spawn_lines('my-explorer', 'agent_name must use only lowercase letters, digits, and underscores'))
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: not run task_name rejected')

    def test_other_spawn_error(self):
        self.events()
        self.session(spawn_lines('my-explorer', 'Error: too many agents\nsecond line'))
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: not run spawn error: Error: too many agents second line')

    def test_no_spawn_call(self):
        self.events()
        self.session(spawn_lines('worker', '{"agent_id": "a1"}'))
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: not run no spawn call')

    def test_events_only_without_session_record(self):
        self.events([json.dumps({'type': 'thread.started', 'thread_id': THREAD})] + spawn_lines('my-explorer', 'unknown agent'))
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: refused')
        self.assertIn('Evidence: captures/hyphen-events.jsonl line 3 (spawn call)', (self.out / 'outcome.md').read_text(encoding='utf-8'))

    def test_missing_codex_binary(self):
        code = self.run_probe(codex=self.tmp / 'no-such-codex')
        self.assertEqual(code, 1)
        self.assertTrue(self.first_line().startswith('Outcome: not run codex: '))

    def test_exec_with_no_events(self):
        self.events([])
        self.run_probe()
        self.assertEqual(self.first_line(), 'Outcome: not run codex: exec with no events')

    def test_agent_option_selects_the_probed_type(self):
        self.events()
        self.session(spawn_lines('other-agent', json.dumps({'agent_id': 'a1'})))
        self.run_probe('--agent', 'other-agent')
        self.assertEqual(self.first_line(), 'Outcome: accepted')
        self.assertIn('Agent type: other-agent', (self.out / 'outcome.md').read_text(encoding='utf-8'))
        prompt = json.loads(self.log.read_text(encoding='utf-8').splitlines()[1])['argv'][-1]
        self.assertIn('agent_type `other-agent`', prompt)
        self.assertIn('task_name `hyphen_probe`', prompt)

    def test_default_prompt_and_command(self):
        self.events()
        self.run_probe()
        call = json.loads(self.log.read_text(encoding='utf-8').splitlines()[1])
        self.assertEqual(call['argv'][:6], ['exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check', '-C'])
        self.assertEqual(call['argv'][6], str((self.out / 'work').resolve()))
        self.assertIn('agent_type `my-explorer`', call['argv'][-1])
        self.assertIn('task_name `hyphen_probe`', call['argv'][-1])
        self.assertEqual(Path(call['cwd']).resolve(), (self.out / 'work').resolve())

    def test_copies_only_the_throwaway_session(self):
        self.events()
        self.session(spawn_lines('my-explorer', '{}'))
        self.run_probe()
        names = sorted(p.name for p in (self.out / 'sessions').glob('*.jsonl'))
        self.assertEqual(names, [f'rollout-2026-01-01T00-00-00-{THREAD}.jsonl'])
        for name in ('codex-version.txt', 'run.log', 'captures/hyphen-events.jsonl', 'captures/hyphen-stderr.txt'):
            self.assertTrue((self.out / name).is_file(), name)

    def test_codex_home_unchanged(self):
        self.events()
        self.session(spawn_lines('my-explorer', '{}'))
        before = snapshot(self.home)
        self.run_probe()
        self.assertEqual(snapshot(self.home), before)

    def test_refuses_inside_repository(self):
        target = REPO / 'tests' / 'zz-hyphen-probe'
        with self.assertRaises(SystemExit):
            hyphen.main(['--codex', str(self.fake), 'run', str(target)])
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()

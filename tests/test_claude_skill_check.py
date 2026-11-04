"""tools/claude-skill-check.py: run with a fake claude, every outcome class, no write outside <dir>."""
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / 'tools' / 'claude-skill-check.py'

spec = importlib.util.spec_from_file_location('claude_skill_check', TOOL)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

FAKE = '''#!{py}
import json, os, stat, sys, time
argv = sys.argv[1:]
st0, null = os.fstat(0), os.stat(os.devnull)
stdin_null = stat.S_ISCHR(st0.st_mode) and st0.st_rdev == null.st_rdev
with open({log!r}, 'a') as f:
    f.write(json.dumps({{'argv': argv, 'cwd': os.getcwd(), 'env': dict(os.environ), 'stdin_null': stdin_null}}) + '\\n')
if argv[:1] == ['--version']:
    print('9.9.9 (Claude Code)')
elif argv[:1] == ['--help']:
    print('  --no-session-persistence  x\\n  --strict-mcp-config  y')
elif argv[:2] == ['plugin', 'validate']:
    if {validate_fail!r}:
        print('Validation failed: bad manifest')
        sys.exit(1)
    print('Validation passed')
elif '-p' in argv:
    if {sleep!r}:
        time.sleep({sleep!r})
    if {refuse!r}:
        sys.stderr.write('Error: nested session not allowed\\nmore\\n')
        sys.exit(1)
    with open({stdout!r}) as f:
        sys.stdout.write(f.read())
'''

GOOD = ['my-agent:my-agent', 'my-agent:monitor', 'my-agent:mock-up', 'other:thing']


def init_event(plugin, skills, plugins=None, slash=None, drop=()):
    plugins = [{'name': 'my-agent', 'path': str(plugin)}] if plugins is None else plugins
    event = {'type': 'system', 'subtype': 'init', 'plugins': plugins,
             'skills': skills, 'slash_commands': skills if slash is None else slash}
    for key in drop:
        event.pop(key)
    return json.dumps(event)


class SkillCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.parent = self.tmp / 'parent'
        self.parent.mkdir()
        self.plugin = self.tmp / 'plugin'
        self.plugin.mkdir()
        self.stdout_file = self.tmp / 'stdout.jsonl'
        self.stdout_file.write_text('', encoding='utf-8')
        self.log = self.tmp / 'fake-calls.jsonl'
        self.out = self.parent / 'out'

    def fake(self, validate_fail=False, refuse=False, sleep=0):
        path = self.tmp / 'fake-claude'
        path.write_text(FAKE.format(py=sys.executable, log=str(self.log), stdout=str(self.stdout_file),
                                    validate_fail=validate_fail, refuse=refuse, sleep=sleep), encoding='utf-8')
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    def emit(self, *lines):
        self.stdout_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def run_tool(self, claude=None, *extra):
        claude = claude or self.fake()
        return check.main(['--claude', str(claude), 'run', str(self.out), '--plugin', str(self.plugin)] + list(extra))

    def outcome(self):
        return (self.out / 'outcome.md').read_text(encoding='utf-8')

    def calls(self):
        return [json.loads(x) for x in self.log.read_text(encoding='utf-8').splitlines()]

    def test_listed(self):
        self.emit('not json', init_event(self.plugin, GOOD))
        self.assertEqual(self.run_tool(), 0)
        text = self.outcome()
        self.assertEqual(text.splitlines()[0], 'Outcome: listed')
        self.assertIn('Claude Code: 9.9.9', text)
        self.assertIn('Skills: my-agent:my-agent, my-agent:monitor, my-agent:mock-up', text)
        self.assertIn('Validate: passed', text)
        self.assertIn('Evidence: stdout.jsonl line 2 (system init)', text)
        self.assertTrue((self.out / 'init.json').is_file())
        self.assertTrue((self.out / 'work').is_dir())
        self.assertTrue((self.out / 'run.log').is_file())
        self.assertTrue((self.out / 'claude-version.txt').is_file())

    def test_listed_bare_form(self):
        self.emit(init_event(self.plugin, ['my-agent', 'my-agent:monitor', 'my-agent:mock-up']))
        self.assertEqual(self.run_tool(), 0)
        self.assertIn('Skills: my-agent, my-agent:monitor', self.outcome())

    def problem(self, line, event):
        self.emit(event)
        self.assertEqual(self.run_tool(), 1)
        text = self.outcome()
        self.assertEqual(text.splitlines()[0], 'Outcome: problem')
        self.assertIn(line, text.splitlines())

    def test_missing_skill(self):
        self.problem('my-agent:mock-up not listed', init_event(self.plugin, ['my-agent:my-agent', 'my-agent:monitor']))

    def test_extra_skill(self):
        self.problem('my-agent:extra listed', init_event(self.plugin, GOOD + ['my-agent:extra']))

    def test_duplicate_skill(self):
        self.problem('my-agent:monitor listed 2 times',
                     init_event(self.plugin, GOOD + ['my-agent:monitor'], slash=GOOD))

    def test_two_paths(self):
        other = self.tmp / 'installed'
        plugins = [{'name': 'my-agent', 'path': str(self.plugin)}, {'name': 'my-agent', 'path': str(other)}]
        self.problem(f'my-agent loaded from {self.plugin}, {other}', init_event(self.plugin, GOOD, plugins=plugins))

    def test_other_path(self):
        other = self.tmp / 'installed'
        self.problem(f'my-agent loaded from {other}',
                     init_event(self.plugin, GOOD, plugins=[{'name': 'my-agent', 'path': str(other)}]))

    def test_not_loaded(self):
        self.problem('my-agent not loaded', init_event(self.plugin, GOOD, plugins=[{'name': 'x', 'path': '/x'}]))

    def test_validate_fails(self):
        self.emit(init_event(self.plugin, GOOD))
        self.assertEqual(self.run_tool(self.fake(validate_fail=True)), 1)
        text = self.outcome()
        self.assertEqual(text.splitlines()[0], 'Outcome: problem')
        self.assertIn('Validate: failed: Validation failed: bad manifest', text)

    def assert_not_run(self, reason, code):
        self.assertEqual(code, 3)
        first = self.outcome().splitlines()[0]
        self.assertTrue(first.startswith('Outcome: not run ' + reason), first)

    def test_no_init_event(self):
        self.emit(json.dumps({'type': 'result'}))
        self.assert_not_run('no init event', self.run_tool())

    def test_init_without_plugins(self):
        self.emit(init_event(self.plugin, GOOD, drop=['plugins']))
        self.assert_not_run('init event lacks plugins', self.run_tool())

    def test_init_without_skills(self):
        self.emit(init_event(self.plugin, GOOD, drop=['skills', 'slash_commands']))
        self.assert_not_run('init event lacks skills', self.run_tool())

    def test_no_binary(self):
        self.assert_not_run('no claude binary', self.run_tool(self.tmp / 'missing'))

    def test_start_refusal(self):
        self.assert_not_run('claude refused to start: Error: nested session not allowed',
                            self.run_tool(self.fake(refuse=True)))

    def test_plugins_not_a_list_is_not_run(self):
        for value in (None, {}, 'my-agent'):
            with self.subTest(plugins=value):
                event = {'type': 'system', 'subtype': 'init', 'plugins': value, 'skills': GOOD, 'slash_commands': GOOD}
                self.emit(json.dumps(event))
                code = self.run_tool()
                self.assert_not_run('init event plugins is not a list', code)
                self.assertEqual(self.outcome().splitlines()[0], 'Outcome: not run init event plugins is not a list')

    def test_timeout_is_not_run(self):
        self.emit(init_event(self.plugin, GOOD))
        with mock.patch.object(check, 'TIMEOUT', 1):
            code = self.run_tool(self.fake(sleep=5))
        self.assertEqual(code, 3)
        self.assertEqual(self.outcome().splitlines()[0], 'Outcome: not run timeout after 1 s')

    def test_claude_gets_no_stdin(self):
        self.emit(init_event(self.plugin, GOOD))
        pipe_r, pipe_w = os.pipe()
        saved = os.dup(0)

        def restore():
            os.dup2(saved, 0)
            for fd in (saved, pipe_r, pipe_w):
                os.close(fd)
        self.addCleanup(restore)
        os.dup2(pipe_r, 0)
        self.assertEqual(self.run_tool(), 0)
        calls = self.calls()
        self.assertTrue(calls)
        for call in calls:
            self.assertTrue(call['stdin_null'], call['argv'])

    def test_inside_repo_refused(self):
        target = REPO / 'tmp-claude-skill-check-refused'
        code = check.main(['--claude', str(self.fake()), 'run', str(target), '--plugin', str(self.plugin)])
        self.assertEqual(code, 2)
        self.assertFalse(target.exists())

    def test_command_line_and_env(self):
        self.emit(init_event(self.plugin, GOOD))
        for name in ('CLAUDECODE', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_PROJECT_DIR',
                     'CLAUDE_PLUGIN_ROOT'):
            os.environ[name] = 'x'
            self.addCleanup(os.environ.pop, name, None)
        self.run_tool()
        run = [c for c in self.calls() if '-p' in c['argv']][0]
        argv = run['argv']
        self.assertEqual(Path(argv[argv.index('--plugin-dir') + 1]), self.plugin.resolve())
        self.assertEqual(argv[argv.index('--max-turns') + 1], '1')
        self.assertEqual(argv[argv.index('--model') + 1], 'haiku')
        self.assertEqual(argv[argv.index('--output-format') + 1], 'stream-json')
        self.assertIn('--verbose', argv)
        self.assertIn('--no-session-persistence', argv)
        self.assertIn('--strict-mcp-config', argv)
        settings = json.loads(argv[argv.index('--settings') + 1])
        self.assertEqual(settings, {'enabledPlugins': {'my-agent@my-plugins': False}})
        self.assertEqual(Path(run['cwd']).resolve(), (self.out / 'work').resolve())
        for name in ('CLAUDECODE', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_PROJECT_DIR',
                     'CLAUDE_PLUGIN_ROOT'):
            self.assertNotIn(name, run['env'])
        validate = [c for c in self.calls() if c['argv'][:2] == ['plugin', 'validate']][0]
        self.assertEqual(validate['argv'], ['plugin', 'validate', '--strict', str(self.plugin.resolve())])

    def test_disable_option(self):
        self.emit(init_event(self.plugin, GOOD))
        self.run_tool(None, '--disable', 'a@b', '--disable', 'c@d')
        run = [c for c in self.calls() if '-p' in c['argv']][0]['argv']
        settings = json.loads(run[run.index('--settings') + 1])
        self.assertEqual(settings, {'enabledPlugins': {'a@b': False, 'c@d': False}})

    def test_writes_only_inside_dir(self):
        self.emit(init_event(self.plugin, GOOD))
        claude = self.fake()
        self.log.write_text('', encoding='utf-8')
        before = sorted(p.name for p in self.tmp.iterdir())
        self.run_tool(claude)
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ['out'])
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), before)


if __name__ == '__main__':
    unittest.main()

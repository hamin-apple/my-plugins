"""tools/codex-probe/probe.py: kit layout, dump script, run/snapshot with a fake codex, summary of sample dumps."""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / 'tools' / 'codex-probe' / 'probe.py'
SAMPLE = REPO / 'tests' / 'fixtures' / 'codex-probe' / 'sample'
SAMPLE_AGENTS = REPO / 'tests' / 'fixtures' / 'codex-probe' / 'sample-agents'

spec = importlib.util.spec_from_file_location('codex_probe', PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

FAKE = '''#!{py}
import json, os, sys
with open({log!r}, 'a') as f:
    f.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}) + '\\n')
if sys.argv[1:2] == ['--version']:
    print('codex-cli 9.9.9')
elif sys.argv[1:2] == ['exec']:
    print(json.dumps({{'type': 'thread.started'}}))
else:
    print('listing ' + ' '.join(sys.argv[1:]))
'''


def make_fake(tmp: Path):
    log = tmp / 'fake-calls.jsonl'
    script = tmp / 'fake-codex'
    script.write_text(FAKE.format(py=sys.executable, log=str(log)), encoding='utf-8')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, log


def calls(log: Path):
    return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]


def all_commands(hooks_json):
    out = []
    for entries in hooks_json['hooks'].values():
        for entry in entries:
            for hook in entry['hooks']:
                out.append(hook['command'])
    return out


class KitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def kit(self, bump=False):
        probe.main(['kit', str(self.tmp)] + (['--bump'] if bump else []))
        plugin = self.tmp / 'kit' / 'plugins' / 'ma-probe'
        return json.loads((plugin / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))

    def test_layout(self):
        hooks = self.kit()
        kit = self.tmp / 'kit'
        market = json.loads((kit / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(market['name'], 'ma-probe')
        self.assertEqual(market['plugins'][0]['name'], 'ma-probe')
        manifest = json.loads((kit / 'plugins' / 'ma-probe' / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], 'ma-probe')
        self.assertEqual(
            set(hooks['hooks']),
            {'PreToolUse', 'PostToolUse', 'PermissionRequest', 'SessionStart', 'SubagentStart', 'SubagentStop', 'Stop'})

    def test_commands_pass_absolute_dump_and_plugin_root(self):
        dump = self.tmp / 'kit' / 'dump.py'
        hooks = self.kit()
        self.assertTrue(dump.is_file())
        for command in all_commands(hooks):
            self.assertIn(str(dump), command)
            self.assertIn('"${CLAUDE_PLUGIN_ROOT}"', command)

    def test_marker_hooks(self):
        commands = all_commands(self.kit())
        for mode in ('deny', 'exit2', 'bad'):
            self.assertEqual(len([c for c in commands if c.endswith(' ' + mode)]), 1, mode)

    def test_bump_changes_exactly_one_command(self):
        before = all_commands(self.kit())
        after = all_commands(self.kit(bump=True))
        self.assertEqual(len(before), len(after))
        self.assertEqual(len([1 for a, b in zip(before, after) if a != b]), 1)

    def test_kit_prints_codex_commands_with_real_paths(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            probe.main(['kit', str(self.tmp)])
        self.assertIn('codex plugin marketplace add ' + str((self.tmp / 'kit').resolve()), out.getvalue())
        self.assertIn('codex plugin add ma-probe@ma-probe', out.getvalue())


class DumpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        probe.main(['kit', str(self.tmp)])
        self.dump = self.tmp / 'kit' / 'dump.py'

    def run_dump(self, args, stdin, env_extra):
        env = {'PATH': os.environ['PATH']}
        env.update(env_extra)
        return subprocess.run([sys.executable, str(self.dump)] + args, input=stdin, env=env,
                              capture_output=True, text=True)

    def records(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.tmp / 'captures').glob('*.json'))]

    def test_env_values_only_for_allowed_names(self):
        self.run_dump(['PreToolUse', '/root'], '{"tool_name": "Bash"}', {
            'CODEX_HOME': '/h', 'CLAUDE_PLUGIN_ROOT': '/r', 'MA_PROBE_SCENARIO': 'hooks',
            'CODEX_API_KEY': 'k-secret', 'OTHER_VAR': 'plain-value', 'CLAUDE_AUTH_X': 'a-secret'})
        rec = self.records()[0]
        self.assertIn('OTHER_VAR', rec['env_names'])
        self.assertIn('CODEX_API_KEY', rec['env_names'])
        self.assertEqual(rec['env_values'], {'CODEX_HOME': '/h', 'CLAUDE_PLUGIN_ROOT': '/r', 'MA_PROBE_SCENARIO': 'hooks'})
        self.assertEqual(rec['scenario'], 'hooks')
        text = json.dumps(rec)
        for secret in ('k-secret', 'plain-value', 'a-secret'):
            self.assertNotIn(secret, text)

    def test_secret_named_stdin_fields_removed(self):
        self.run_dump(['PreToolUse', '/root'], json.dumps({'tool_input': {'api_key': 'zz', 'command': 'ls'}}), {})
        text = json.dumps(self.records()[0])
        self.assertNotIn('zz', text)
        self.assertIn('ls', text)

    def test_marker_modes(self):
        deny = self.run_dump(['marker-deny', '/root', 'deny'], '{"tool_input": {"command": "echo ma-probe-deny"}}', {})
        self.assertEqual(deny.returncode, 0)
        self.assertEqual(json.loads(deny.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        exit2 = self.run_dump(['marker-exit2', '/root', 'exit2'], '{"tool_input": {"command": "echo ma-probe-exit2"}}', {})
        self.assertEqual(exit2.returncode, 2)
        bad = self.run_dump(['marker-bad', '/root', 'bad'], '{"tool_input": {"command": "echo ma-probe-bad"}}', {})
        self.assertEqual(bad.returncode, 0)
        with self.assertRaises(ValueError):
            json.loads(bad.stdout)
        other = self.run_dump(['marker-deny', '/root', 'deny'], '{"tool_input": {"command": "ls"}}', {})
        self.assertEqual((other.returncode, other.stdout), (0, ''))


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.work = self.tmp / 'probe'
        probe.main(['kit', str(self.work)])

    def test_run_uses_only_fake_codex_in_throwaway_folder(self):
        code = probe.main(['--codex', str(self.fake), 'run', str(self.work), 'hooks'])
        self.assertEqual(code, 0)
        made = calls(self.log)
        scenario_dir = self.work / 'work-hooks'
        self.assertTrue(scenario_dir.is_dir())
        self.assertFalse((scenario_dir / '.git').exists())
        execs = [c for c in made if c['argv'][:1] == ['exec']]
        self.assertEqual(len(execs), 1)
        self.assertEqual(os.path.realpath(execs[0]['cwd']), os.path.realpath(scenario_dir))
        self.assertNotEqual(os.path.realpath(execs[0]['cwd']), os.path.realpath(REPO))
        self.assertIn('read-only', execs[0]['argv'])
        self.assertIn('--json', execs[0]['argv'])
        for c in made:
            self.assertIn(c['argv'][0], ('--version', 'exec'))
        run_log = (self.work / 'run.log').read_text(encoding='utf-8')
        self.assertIn('exit 0', run_log)
        self.assertTrue((self.work / 'captures' / 'hooks-events.jsonl').is_file())

    def test_run_refuses_folder_inside_repo(self):
        with self.assertRaises(SystemExit):
            probe.main(['--codex', str(self.fake), 'run', str(REPO / 'tests' / 'zz-probe'), 'hooks'])
        self.assertFalse((REPO / 'tests' / 'zz-probe').exists())

    def test_run_rejects_unknown_scenario(self):
        with self.assertRaises(SystemExit):
            probe.main(['--codex', str(self.fake), 'run', str(self.work), 'nope'])

    def test_snapshot_read_only_subcommands(self):
        out = self.tmp / 'snap'
        code = probe.main(['--codex', str(self.fake), 'snapshot', '--out', str(out)])
        self.assertEqual(code, 0)
        argvs = [c['argv'] for c in calls(self.log)]
        self.assertEqual(argvs, [['--version'], ['plugin', 'list'], ['plugin', 'marketplace', 'list']])
        self.assertIn('9.9.9', (out / 'codex-version.txt').read_text(encoding='utf-8'))
        self.assertIn('listing plugin list', (out / 'plugin-list.txt').read_text(encoding='utf-8'))
        self.assertTrue((out / 'marketplace-list.txt').is_file())


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir = self.tmp / 'probe'
        shutil.copytree(SAMPLE, self.dir)
        (self.dir / 'codex-version.txt').write_text('codex-cli 1.2.3\n', encoding='utf-8')
        self.out = self.tmp / 'out'
        code = probe.main(['summary', str(self.dir), '--out', str(self.out), '--config', str(SAMPLE / 'config.toml')])
        self.assertEqual(code, 0)
        self.summary = json.loads((self.out / 'summary-hooks.json').read_text(encoding='utf-8'))

    def test_events_and_fields(self):
        s = self.summary
        self.assertEqual(s['codex_version'], 'codex-cli 1.2.3')
        self.assertEqual(set(s['events_seen']), {'PreToolUse', 'SessionStart', 'Stop', 'marker-deny'})
        self.assertEqual(s['fields']['PreToolUse']['session_id'], 'str')
        self.assertEqual(s['fields']['PreToolUse']['tool_input'], 'dict')
        self.assertEqual(s['tool_names'], ['Bash', 'apply_patch'])
        self.assertEqual(s['tool_input_shapes']['Bash'], {'command': 'str'})
        self.assertIn('session_id', s['id_fields'])
        self.assertIn('cwd', s['id_fields'])

    def test_env_and_root(self):
        s = self.summary
        self.assertIn('PATH', s['env_var_names'])
        self.assertEqual(s['env_values']['CODEX_HOME'], '/home/x/.codex')
        self.assertEqual(s['plugin_root']['expanded'], True)
        self.assertEqual(s['plugin_root']['values'], ['/kit/plugins/ma-probe'])

    def test_marker_and_trust(self):
        s = self.summary
        self.assertTrue(s['markers']['deny']['hook_fired'])
        self.assertFalse(s['markers']['exit2']['hook_fired'])
        self.assertFalse(s['markers']['deny']['output_seen'])
        self.assertTrue(s['markers']['exit2']['output_seen'])
        self.assertTrue(s['trust']['hooks_ran_in_hooks_scenario'])
        self.assertTrue(s['trust']['bumped_hook_ran_in_stale'])
        self.assertEqual(s['trust']['config_entries'][0]['trusted_hash'], 'sha256:abc')
        self.assertEqual(len(s['trust']['config_entries']), 1)
        self.assertIsNone(s['trust']['hash_recomputed_by'])

    def test_reduced_copies(self):
        self.assertTrue((self.out / 'run.log').is_file())
        self.assertEqual(len(list((self.out / 'captures').glob('*.json'))), 5)
        events = (self.out / 'captures' / 'hooks-events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('zzz', events)
        self.assertIn('echo ma-probe-deny', events)


class KitScenarioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        probe.main(['kit', str(self.tmp)])
        self.kit = self.tmp / 'kit'
        self.plugin = self.kit / 'plugins' / 'ma-probe'

    def load(self, path):
        return json.loads(path.read_text(encoding='utf-8'))

    def test_two_manifests_and_two_marketplace_files_tell_apart(self):
        claude = self.load(self.plugin / '.claude-plugin' / 'plugin.json')
        codex = self.load(self.plugin / '.codex-plugin' / 'plugin.json')
        self.assertNotEqual(claude['description'], codex['description'])
        self.assertIn('probe_opt', claude['userConfig'])
        m_claude = self.load(self.kit / '.claude-plugin' / 'marketplace.json')
        m_codex = self.load(self.kit / '.agents' / 'plugins' / 'marketplace.json')
        self.assertNotEqual(m_claude['plugins'][0]['description'], m_codex['plugins'][0]['description'])

    def test_skills_and_agents_in_every_candidate_location(self):
        self.assertIn('${CLAUDE_SKILL_DIR}', (self.plugin / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('$ARGUMENTS', (self.plugin / 'skills' / 'ma-probe-dir' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(self.load(self.plugin / '.claude-plugin' / 'plugin.json')['skills'][0], './')
        self.assertTrue((self.plugin / 'agents' / 'ma_probe_agent_claude.md').is_file())
        self.assertTrue((self.plugin / 'agents' / 'ma_probe_agent_plugin_toml.toml').is_file())
        self.assertTrue((self.plugin / '.codex' / 'agents' / 'ma_probe_agent_plugin_codexdir.toml').is_file())
        self.assertTrue((self.plugin / 'codex-agents' / 'ma_probe_agent_manifest_toml.toml').is_file())
        self.assertTrue((self.tmp / 'kit-dup' / '.agents' / 'plugins' / 'marketplace.json').is_file())

    def test_change_market_rewrites_only_marketplace_files(self):
        before = (self.plugin / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')
        hooks_before = (self.plugin / 'hooks' / 'hooks.json').read_text(encoding='utf-8')
        probe.main(['kit', str(self.tmp), '--change-market'])
        for path in (self.kit / '.claude-plugin' / 'marketplace.json', self.kit / '.agents' / 'plugins' / 'marketplace.json'):
            self.assertEqual(self.load(path)['plugins'][0]['description'], 'ma-probe-market-changed')
        self.assertEqual((self.plugin / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'), before)
        self.assertEqual((self.plugin / 'hooks' / 'hooks.json').read_text(encoding='utf-8'), hooks_before)


class ScenarioRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.work = self.tmp / 'probe'
        probe.main(['kit', str(self.work)])
        self.home = self.tmp / 'codex-home'

    def run_scenario(self, name):
        return probe.main(['--codex', str(self.fake), '--codex-home', str(self.home), 'run', str(self.work), name])

    def test_agents_writes_project_agents_only_in_work_folder(self):
        self.assertEqual(self.run_scenario('agents'), 0)
        agents = self.work / 'work-agents' / '.codex' / 'agents'
        self.assertTrue((agents / 'ma_probe_agent_project.toml').is_file())
        self.assertFalse(self.home.exists())
        argvs = [c['argv'][:2] for c in calls(self.log)]
        self.assertIn(['debug', 'prompt-input'], argvs)
        self.assertIn(['debug', 'models'], argvs)

    def test_skills_runs_exec_with_skill_prompt(self):
        self.assertEqual(self.run_scenario('skills'), 0)
        execs = [c for c in calls(self.log) if c['argv'][:1] == ['exec']]
        self.assertIn('MA-PROBE-EXPAND', execs[0]['argv'][-1])

    def test_install_uses_read_only_commands_and_prints_settings_commands(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out), unittest.mock.patch('builtins.input', side_effect=EOFError):
            self.assertEqual(self.run_scenario('install'), 0)
        argvs = [c['argv'] for c in calls(self.log)]
        for argv in argvs:
            self.assertEqual(argv[0], 'plugin')
            self.assertFalse({'add', 'remove', 'upgrade'} & set(argv) - {'--help'} and '--help' not in argv, argv)
        self.assertIn('codex plugin add ma-probe@ma-probe', out.getvalue())
        self.assertIn('--change-market', out.getvalue())
        self.assertTrue((self.work / 'captures' / 'install-added-plugin-list.txt').is_file())

    def test_session_copy_picks_only_given_ids(self):
        root = self.tmp / 'sessions'
        (root / '2026' / '01').mkdir(parents=True)
        mine = root / '2026' / '01' / 'rollout-aaaaaaaa-1.jsonl'
        other = root / '2026' / '01' / 'rollout-zzzzzzzz-9.jsonl'
        mine.write_text('{}\n', encoding='utf-8')
        other.write_text('{}\n', encoding='utf-8')
        names = probe.copy_sessions({'aaaaaaaa-1'}, set(), root, self.tmp / 'dest')
        self.assertEqual(names, ['rollout-aaaaaaaa-1.jsonl'])
        self.assertEqual([p.name for p in (self.tmp / 'dest').iterdir()], ['rollout-aaaaaaaa-1.jsonl'])

    def test_run_copies_sessions_of_the_exec_thread_only(self):
        sessions = self.home / 'sessions'
        sessions.mkdir(parents=True)
        (sessions / 'rollout-thread-12345678.jsonl').write_text('{}\n', encoding='utf-8')
        (sessions / 'rollout-unrelated-99999999.jsonl').write_text('{}\n', encoding='utf-8')
        fake = self.tmp / 'fake2'
        fake.write_text('#!%s\nimport json, sys\nif sys.argv[1:2] == ["exec"]:\n    print(json.dumps({"type": "thread.started", "thread_id": "thread-12345678"}))\nelse:\n    print("x")\n' % sys.executable, encoding='utf-8')
        fake.chmod(0o755)
        probe.main(['--codex', str(fake), '--codex-home', str(self.home), 'run', str(self.work), 'skills'])
        copied = sorted(p.name for p in (self.work / 'sessions' / 'skills').iterdir())
        self.assertEqual(copied, ['rollout-thread-12345678.jsonl'])


class AgentsSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir = self.tmp / 'probe'
        shutil.copytree(SAMPLE_AGENTS, self.dir)
        self.out = self.tmp / 'work' / 'probe'
        code = probe.main(['summary', str(self.dir), '--out', str(self.out), '--config', str(SAMPLE_AGENTS / 'config.toml')])
        self.assertEqual(code, 0)
        self.s = json.loads((self.out / 'summary-agents.json').read_text(encoding='utf-8'))

    def test_agents_skills_tools(self):
        a = self.s['agents']
        self.assertEqual(a['spawn_tool_names'], ['spawn_agent'])
        self.assertEqual(a['per_call_model_or_effort'], ['model'])
        self.assertTrue(a['names_seen']['ma_probe_agent_project'])
        self.assertTrue(a['parallel_overlap'])
        self.assertIn('parent_session_id', a['identity_fields']['SubagentStart'])
        self.assertIn('result', a['handback_fields'])
        sk = self.s['skills']['expansions']
        self.assertEqual(sk['skill_dir']['value_kind'], 'expanded')
        self.assertEqual(sk['plugin_root']['value_kind'], 'literal')
        self.assertEqual(self.s['main_tools']['question_tool'], ['request_user_input'])

    def test_session_record_reduced_and_located(self):
        rec = self.s['session_record']
        self.assertIn('session_meta', rec['line_types'])
        self.assertIn('session_meta:payload.id', rec['id_paths'])
        self.assertEqual(rec['model_ids'], ['model-a'])
        self.assertIn('input_tokens', rec['token_fields'])
        self.assertIn('reasoning_output_tokens', rec['token_fields'])
        self.assertEqual(rec['cost_paths'], [])
        self.assertEqual(rec['default_model_setting'], 'model-a')
        reduced = (self.out / 'captures' / 'session-agents-1.reduced.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('zzz', reduced)

    def test_install(self):
        inst = self.s['install']
        self.assertEqual(inst['manifest_read'], 'codex')
        self.assertEqual(inst['market_file_read'], 'codex')
        self.assertTrue(inst['reread_at_plugin_add'])
        self.assertFalse(inst['refreshed_by_upgrade'])
        self.assertIsNone(inst['dup_marketplace_count'])


class FindingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir = self.tmp / 'probe'
        shutil.copytree(SAMPLE_AGENTS, self.dir)
        self.work = self.tmp / 'work'
        probe.main(['summary', str(self.dir), '--out', str(self.work / 'probe'), '--config', str(SAMPLE_AGENTS / 'config.toml')])
        self.assertEqual(probe.main(['findings', str(self.dir), '--out', str(self.work)]), 0)
        self.md = self.work / 'codex-findings.md'

    def test_every_section_and_open_row(self):
        text = self.md.read_text(encoding='utf-8')
        for name in probe.SECTIONS:
            self.assertIn('## ' + name, text)
        self.assertIn('| Fact | Capture | Used by unit |', text)
        open_part = text.split('## Open')[1].split('## Fact table')[0]
        self.assertIn('USD cost in the record', open_part)
        self.assertIn('Two marketplaces with the same name', open_part)
        self.assertNotIn('Where the session id is', open_part)
        data = json.loads((self.work / 'codex-findings.json').read_text(encoding='utf-8'))
        self.assertTrue(any(o['fact'] == 'USD cost in the record' for o in data['open']))
        self.assertTrue(all(f['capture'].startswith('probe/captures/') for f in data['facts']))

    def test_check_passes_and_fails(self):
        self.assertEqual(probe.main(['check', 'findings', str(self.md)]), 0)
        text = self.md.read_text(encoding='utf-8')
        no_section = self.work / 'no-section.md'
        no_section.write_text(text.replace('## Skills', '## Other'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(self.md)]), 0)
        self.assertEqual(probe.main(['check', 'findings', str(no_section)]), 1)
        bad_cap = self.work / 'bad-capture.md'
        bad_cap.write_text(text + '\n`probe/captures/nope.json`\n', encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(bad_cap)]), 1)

    def test_check_names_what_is_missing(self):
        import io
        from contextlib import redirect_stdout
        broken = self.work / 'broken.md'
        broken.write_text(self.md.read_text(encoding='utf-8').replace('## Agents', '## X'), encoding='utf-8')
        out = io.StringIO()
        with redirect_stdout(out):
            probe.main(['check', 'findings', str(broken)])
        self.assertIn('missing section: ## Agents', out.getvalue())


SAMPLE_UNKNOWN = REPO / 'tests' / 'fixtures' / 'codex-probe' / 'sample-unknown'


class UnknownAgentsAndTrustTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir = self.tmp / 'probe'
        shutil.copytree(SAMPLE_UNKNOWN, self.dir)
        self.work = self.tmp / 'work'
        cfg = str(SAMPLE_UNKNOWN / 'config.toml')
        self.assertEqual(probe.main(['summary', str(self.dir), '--out', str(self.work / 'probe'), '--config', cfg]), 0)
        self.assertEqual(probe.main(['findings', str(self.dir), '--out', str(self.work)]), 0)
        self.agents = json.loads((self.work / 'probe' / 'summary-agents.json').read_text(encoding='utf-8'))['agents']
        self.md = (self.work / 'codex-findings.md').read_text(encoding='utf-8')

    def test_unknown_agent_type_means_not_loaded(self):
        self.assertTrue(self.agents['names_seen'])
        self.assertFalse(any(self.agents['names_seen'].values()))
        self.assertIn('ma_probe_agent_project_tools', self.agents['unknown_agent_types'])

    def test_trust_section_says_plainly_nothing_loaded(self):
        trust = self.md.split('## Trust and stale trust')[1].split('\n## ')[0]
        self.assertIn('no ma-probe trust entry in hooks.state; hooks did not load or were not trusted', trust)
        self.assertIn('no hook fired in the hooks scenario', trust)

    def test_manifests_declare_hooks_file(self):
        probe.main(['kit', str(self.tmp / 'k')])
        plugin = self.tmp / 'k' / 'kit' / 'plugins' / 'ma-probe'
        for sub in ('.claude-plugin', '.codex-plugin'):
            manifest = json.loads((plugin / sub / 'plugin.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['hooks'], './hooks/hooks.json')
            self.assertTrue((plugin / manifest['hooks']).is_file())

    def test_kit_prints_hooks_listed_step_before_trust(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            probe.main(['kit', str(self.tmp / 'k2')])
        text = out.getvalue()
        self.assertIn('codex plugin list', text)
        self.assertLess(text.index('codex plugin list'), text.index('trust step'))


FIX = REPO / 'tests' / 'fixtures' / 'codex-probe'
ID_VALUES = ['sess-main-0001', 'agent-a-0001', 'agent-b-0001', '/t/main.jsonl', '/t/agent-a.jsonl', 'thread-0001']


class KitIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        probe.main(['kit', str(self.tmp)])
        self.plugin = self.tmp / 'kit' / 'plugins' / 'ma-probe'
        self.hooks = json.loads((self.plugin / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))['hooks']

    def test_agent_names_use_only_lowercase_digits_underscore(self):
        import re
        for name in probe.AGENT_NAMES + list(probe.PROJECT_AGENTS) + ['ma_probe_worker_a', 'ma_probe_worker_b']:
            self.assertRegex(name, r'^[a-z0-9_]+$')
        for path in list((self.plugin / 'agents').iterdir()) + list((self.plugin / '.codex' / 'agents').iterdir()) \
                + list((self.plugin / 'codex-agents').iterdir()):
            self.assertRegex(path.stem, r'^[a-z0-9_]+$')
            self.assertTrue(re.search(r'name\s*[:=]\s*"?ma_probe_agent', path.read_text(encoding='utf-8')), path)

    def test_workers_are_project_level_workspace_write(self):
        import tomllib
        for w in ('a', 'b'):
            path = self.tmp / 'work-identity' / '.codex' / 'agents' / f'ma_probe_worker_{w}.toml'
            data = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['name'], f'ma_probe_worker_{w}')
            self.assertEqual(data['sandbox_mode'], 'workspace-write')

    def test_marker_and_matcher_hooks(self):
        pre = self.hooks['PreToolUse']
        commands = [h['command'] for e in pre for h in e['hooks']]
        self.assertEqual(len([c for c in commands if c.endswith(' deny-file')]), 1)
        exit1 = [h for e in pre for h in e['hooks'] if h['command'].endswith(' exit1')]
        self.assertEqual(len(exit1), 1)
        self.assertEqual(exit1[0]['onFailure'], 'block')
        matchers = {e['matcher'] for e in pre if 'matcher' in e}
        for m in ('Bash', '^Bash$', 'Ba.*', 'Bash|Write', 'Edit|Write', 'apply_patch'):
            self.assertIn(m, matchers)
        self.assertIn('^ma_probe_worker_a$', {e.get('matcher') for e in self.hooks['SubagentStart']})
        for e in pre:
            if 'matcher' in e:
                self.assertEqual(len(e['hooks']), 1)

    def test_deny_file_and_exit1_modes_in_dump(self):
        dump = self.tmp / 'kit' / 'dump.py'
        def run(args, text):
            return subprocess.run([sys.executable, str(dump)] + args, input=text, env={'PATH': os.environ['PATH']},
                                  capture_output=True, text=True)
        denied = run(['marker-deny-file', '/r', 'deny-file'], '{"tool_input": {"input": "Add File: ma-probe-deny-file-a.txt"}}')
        self.assertEqual(json.loads(denied.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(run(['marker-deny-file', '/r', 'deny-file'], '{"tool_input": {"command": "ls"}}').stdout, '')
        self.assertEqual(run(['marker-exit1', '/r', 'exit1'], '{"tool_input": {"command": "echo ma-probe-exit1"}}').returncode, 1)
        self.assertEqual(run(['marker-exit1', '/r', 'exit1'], '{"tool_input": {"command": "ls"}}').returncode, 0)
        # the other deny forms, each on its own file-name marker
        def form(mode, name):
            return run(['marker-' + mode, '/r', mode], '{"tool_input": {"command": "*** Add File: %s-a.txt"}}' % name)
        res = form('fexit2', 'ma-probe-fexit2')
        self.assertEqual((res.returncode, res.stdout), (2, ''))
        self.assertIn('ma-probe', res.stderr)
        self.assertEqual(json.loads(form('fblock', 'ma-probe-fblock').stdout)['decision'], 'block')
        self.assertIn('reason', json.loads(form('fblock', 'ma-probe-fblock').stdout))
        stop = json.loads(form('fstop', 'ma-probe-fstop').stdout)
        self.assertEqual((stop['continue'], bool(stop['stopReason'])), (False, True))
        both = json.loads(form('fboth', 'ma-probe-fboth').stdout)
        self.assertEqual((both['decision'], both['hookSpecificOutput']['permissionDecision']), ('block', 'deny'))
        self.assertEqual(json.loads(form('fmatch', 'ma-probe-fmatch').stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(form('fexit2', 'ma-probe-fblock').returncode, 0)
        self.assertEqual(form('fblock', 'ma-probe-fexit2').stdout, '')

    def test_file_deny_form_hooks_and_prompt(self):
        pre = self.hooks['PreToolUse']
        commands = [h['command'] for e in pre for h in e['hooks']]
        for mode in ('fexit2', 'fblock', 'fstop', 'fboth'):
            self.assertEqual(len([c for c in commands if c.endswith(' ' + mode)]), 1, mode)
        match = [e for e in pre if e['hooks'][0]['command'].endswith(' fmatch')]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]['matcher'], 'apply_patch')
        # file-name markers are distinct and none is contained in another
        names = list(probe.FILE_FORMS.values())
        self.assertEqual(len(set(names)), len(names))
        for a in names:
            for b in names:
                self.assertTrue(a == b or a not in b, (a, b))
        for who in ('main', 'a', 'b'):
            for name in names:
                self.assertIn(f'{name}-{who}.txt', probe.PROMPTS['identity'])


class IdentityRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.work = self.tmp / 'probe'
        probe.main(['kit', str(self.work)])

    def test_run_identity_uses_workspace_write_in_work_identity(self):
        self.assertEqual(probe.main(['--codex', str(self.fake), '--codex-home', str(self.tmp / 'h'), 'run', str(self.work), 'identity']), 0)
        execs = [c for c in calls(self.log) if c['argv'][:1] == ['exec']]
        self.assertEqual(len(execs), 1)
        argv = execs[0]['argv']
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'workspace-write')
        self.assertIn('--skip-git-repo-check', argv)
        self.assertEqual(os.path.realpath(execs[0]['cwd']), os.path.realpath(self.work / 'work-identity'))
        self.assertNotEqual(os.path.realpath(execs[0]['cwd']), os.path.realpath(REPO))
        self.assertFalse((self.work / 'work-identity' / '.git').exists())
        prompt = argv[-1]
        for text in ('ma-probe-main-shell', 'main-note.txt', 'ma-probe-deny-file-main.txt', 'ma_probe_worker_a',
                     'ma_probe_worker_b', 'ma-probe-sub-a-shell', 'sub-b-note.txt', 'echo ma-probe-deny',
                     'echo ma-probe-exit1', 'ma-probe-deny-file-b.txt', 'parallel'):
            self.assertIn(text, prompt)

    def test_no_subcommand_changes_codex_settings(self):
        import io
        from contextlib import redirect_stdout
        h = ['--codex', str(self.fake), '--codex-home', str(self.tmp / 'h')]
        out = io.StringIO()
        with redirect_stdout(out), unittest.mock.patch('builtins.input', side_effect=EOFError):
            for scenario in ('hooks', 'stale', 'agents', 'skills', 'identity', 'install'):
                probe.main(h + ['run', str(self.work), scenario])
            e2e = self.tmp / 'e2e-rc'
            shutil.copytree(E2E / 'repo', e2e / 'repo')
            (e2e / 'repo' / '.my-agent' / '.active').write_text('task: 260101-demo\n', encoding='utf-8')
            (e2e / 'repo' / '.my-agent' / '260101-demo' / 'plan.md').write_text(APPROVED_PLAN, encoding='utf-8')
            probe.main(h + ['role-check', str(e2e)])
        probe.main(h + ['snapshot', '--out', str(self.tmp / 'snap')])
        probe.main(['summary-identity', str(self.work), '--out', str(self.tmp / 'o')])
        probe.main(['findings-identity', str(self.tmp / 'o')])
        for c in calls(self.log):
            argv = c['argv']
            if argv[:2] == ['plugin', 'add'] or argv[:2] == ['plugin', 'remove']:
                self.assertIn('--help', argv)
            if argv[:3] in (['plugin', 'marketplace', 'add'], ['plugin', 'marketplace', 'remove'],
                            ['plugin', 'marketplace', 'upgrade']):
                self.assertIn('--help', argv)

    def test_skills_text_line_found_in_session_records(self):
        base = self.tmp / 'skills'
        (base / 'captures').mkdir(parents=True)
        (base / 'sessions' / 'skills').mkdir(parents=True)
        line = {'type': 'response_item', 'payload': {'text': 'x\nMA-PROBE-EXPAND skill_dir=</s> plugin_root=<${CLAUDE_PLUGIN_ROOT}> '
                                                          'arguments=<arg-one> opt=<probe-default>\ny'}}
        (base / 'sessions' / 'skills' / 'rollout-x.jsonl').write_text(json.dumps(line) + '\n', encoding='utf-8')
        out = self.tmp / 'o'
        probe.main(['summary-identity', str(base), '--out', str(out)])
        sk = json.loads((out / 'probe-identity' / 'summary-identity.json').read_text(encoding='utf-8'))['skills']
        self.assertEqual(sk['expansions']['skill_dir']['value_kind'], 'expanded')
        self.assertEqual(sk['expansions']['plugin_root']['value_kind'], 'literal')
        self.assertEqual(sk['expansions_source'], 'session records')


class IdentitySummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def summarize(self, name):
        src = self.tmp / name
        shutil.copytree(FIX / name, src)
        out = self.tmp / ('out-' + name)
        self.assertEqual(probe.main(['summary-identity', str(src), '--out', str(out)]), 0)
        data = json.loads((out / 'probe-identity' / 'summary-identity.json').read_text(encoding='utf-8'))
        return out, data

    def test_outcome_identity_on_calls(self):
        out, data = self.summarize('sample-identity-i')
        self.assertEqual(data['outcome'], 'Outcome: I file-deny=deny')
        self.assertTrue(data['hooks_ran'])
        self.assertEqual(data['file_change']['worker']['tool_names'], ['apply_patch'])
        self.assertIn('sub-a-note.txt', data['file_change']['worker']['targets'])
        self.assertIn('main-note.txt', data['file_change']['main']['targets'])
        self.assertEqual(data['deny_honored']['main_file_deny'], True)
        self.assertEqual(data['deny_honored']['worker_shell_deny'], True)
        self.assertEqual(data['matchers']['matcher-Bash']['tool_names'], [])
        self.assertTrue((out / 'probe-identity' / 'run.log').is_file())
        self.assertTrue(list((out / 'probe-identity' / 'captures').glob('*identity-PreToolUse.json')))

    def test_outcome_link(self):
        _, data = self.summarize('sample-identity-l')
        self.assertEqual(data['outcome'], 'Outcome: L turn_id=turn_id file-deny=deny')
        self.assertTrue(data['start_before_first_call']['a'])

    def test_outcome_deny_not_honored(self):
        _, data = self.summarize('sample-identity-n')
        self.assertEqual(data['deny_honored']['worker_a_file_deny'], False)
        self.assertTrue(data['outcome'].startswith('Outcome: N '))
        self.assertIn('deny', data['outcome'])

    def variant(self, written=(), forms=None, skip=()):
        """A copy of the identity-on-calls sample whose file-change deny calls are rebuilt: every form (or `forms`)
        is tried by main, a and b; the files in `written` (form, who) exist in the work folder (deny not honored)."""
        self.count = getattr(self, 'count', 0) + 1
        src = self.tmp / f'variant{self.count}'
        shutil.copytree(FIX / 'sample-identity-i', src)
        caps = src / 'captures'
        for path in caps.glob('*-identity-PreToolUse.json'):
            if 'ma-probe-deny-file' in path.read_text(encoding='utf-8'):
                path.unlink()
        template = json.loads((FIX / 'sample-identity-i' / 'captures' / '018-identity-PreToolUse.json').read_text(encoding='utf-8'))
        n = 0
        for form in forms or probe.FILE_FORMS:
            for who in ('main', 'a', 'b'):
                if (form, who) in skip:
                    continue
                n += 1
                rec = json.loads(json.dumps(template))
                rec['time'] = '2026-01-01T00:01:%02d+00:00' % n
                data = rec['stdin_json']
                data['tool_input'] = {'input': '*** Begin Patch\n*** Add File: %s-%s.txt\n+x\n*** End Patch'
                                      % (probe.FILE_FORMS[form], who)}
                if who == 'main':
                    data.pop('agent_id'), data.pop('agent_type')
                else:
                    data['agent_type'] = 'ma_probe_worker_' + who
                    data['agent_id'] = 'agent-%s-0001' % who
                    data['turn_id'] = 't-' + who
                (caps / ('9%02d-identity-PreToolUse.json' % n)).write_text(json.dumps(rec), encoding='utf-8')
        work = src / 'work-identity'
        work.mkdir(exist_ok=True)
        for form, who in written:
            (work / f'{probe.FILE_FORMS[form]}-{who}.txt').write_text('x', encoding='utf-8')
        out = self.tmp / f'out-variant{self.count}'
        self.assertEqual(probe.main(['summary-identity', str(src), '--out', str(out)]), 0)
        return json.loads((out / 'probe-identity' / 'summary-identity.json').read_text(encoding='utf-8'))

    def test_file_deny_honored_per_form(self):
        data = self.variant(written=[('deny', 'a'), ('exit2', 'main'), ('block', 'b'), ('stop', 'main'), ('stop', 'a')])
        forms = data['file_deny']
        self.assertEqual({f: v['honored'] for f, v in forms.items()},
                         {'deny': False, 'exit2': False, 'block': False, 'stop': False, 'both': True, 'matcher': True})
        self.assertIs(data['deny_honored']['worker_a_file_deny'], False)
        self.assertIs(data['deny_honored']['main_file_both'], True)
        self.assertEqual(data['outcome'], 'Outcome: I file-deny=both')

    def test_outcome_names_each_honored_form(self):
        for form in probe.FILE_FORMS:
            others = [(f, w) for f in probe.FILE_FORMS if f != form for w in ('main', 'a', 'b')]
            data = self.variant(written=others)
            self.assertEqual(data['outcome'], f'Outcome: I file-deny={form}', form)

    def test_outcome_n_when_no_form_honored(self):
        data = self.variant(written=[(f, w) for f in probe.FILE_FORMS for w in ('main', 'a', 'b')])
        self.assertTrue(data['outcome'].startswith('Outcome: N deny not honored: '))
        self.assertIn('worker_a_file_matcher', data['outcome'])
        self.assertFalse(any(v['honored'] for v in data['file_deny'].values()))
        # honored by main but not by a worker is not honored
        data = self.variant(forms=['block'], written=[('block', 'b')])
        self.assertEqual(data['outcome'], 'Outcome: N deny not honored: worker_b_file_block')

    def test_untried_form_is_not_honored(self):
        data = self.variant(forms=['exit2'])
        self.assertEqual(data['outcome'], 'Outcome: I file-deny=exit2')
        self.assertIsNone(data['deny_honored']['main_file_block'])
        self.assertFalse(data['file_deny']['block']['honored'])

    def test_post_tool_use_on_file_change_recorded(self):
        _, data = self.summarize('sample-identity-i')
        self.assertFalse(data['post_tool_use_file_change']['seen'])
        src = self.tmp / 'post'
        shutil.copytree(FIX / 'sample-identity-i', src)
        rec = json.loads((src / 'captures' / '019-identity-PostToolUse.json').read_text(encoding='utf-8'))
        rec['stdin_json']['tool_name'] = 'apply_patch'
        rec['stdin_json']['tool_input'] = {'input': '*** Add File: sub-b-note.txt'}
        (src / 'captures' / '019-identity-PostToolUse.json').write_text(json.dumps(rec), encoding='utf-8')
        out = self.tmp / 'out-post'
        probe.main(['summary-identity', str(src), '--out', str(out)])
        post = json.loads((out / 'probe-identity' / 'summary-identity.json').read_text(encoding='utf-8'))['post_tool_use_file_change']
        self.assertTrue(post['seen'])
        self.assertEqual(post['tool_names'], ['apply_patch'])

    def test_outcome_open_without_worker_call(self):
        _, data = self.summarize('sample-identity-open')
        self.assertTrue(data['outcome'].startswith('Outcome: open '))

    def test_no_id_value_stored(self):
        for name in ('sample-identity-i', 'sample-identity-l'):
            out, _ = self.summarize(name)
            for path in (out / 'probe-identity').rglob('*'):
                if path.is_file():
                    text = path.read_text(encoding='utf-8')
                    for value in ID_VALUES:
                        self.assertNotIn(value, text, f'{value} in {path.name}')

    def test_fixtures_hold_no_home_path(self):
        for path in FIX.rglob('*'):
            if path.is_file():
                self.assertNotIn(str(Path.home()), path.read_text(encoding='utf-8'), str(path))


class IdentityFindingsTest(unittest.TestCase):
    SECTIONS = ['Subagent tool calls', 'File-change tool', 'Deny and fail-closed on subagent and file-change calls',
                'Identity link', 'Matcher semantics', 'Agent names and locations', 'Skill text expansion', 'Outcome', 'Open']

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        src = self.tmp / 'src'
        shutil.copytree(FIX / 'sample-identity-i', src)
        self.out = self.tmp / 'out'
        probe.main(['summary-identity', str(src), '--out', str(self.out)])
        self.assertEqual(probe.main(['findings-identity', str(self.out)]), 0)
        self.md = self.out / 'codex-findings-identity.md'

    def test_sections_and_outcome(self):
        text = self.md.read_text(encoding='utf-8')
        for name in self.SECTIONS:
            self.assertIn('## ' + name + '\n', text)
        self.assertIn('| Fact | Capture | Used by unit |', text)
        outcome = text.split('## Outcome')[1].split('\n## ')[0]
        self.assertEqual([l for l in outcome.splitlines() if l.startswith('Outcome:')], ['Outcome: I file-deny=deny'])
        self.assertIn('probe-identity/captures/', text)
        data = json.loads((self.out / 'codex-findings-identity.json').read_text(encoding='utf-8'))
        self.assertEqual(data['outcome'], 'Outcome: I file-deny=deny')

    def test_check_passes_and_fails(self):
        self.assertEqual(probe.main(['check', 'findings', str(self.md)]), 0)
        text = self.md.read_text(encoding='utf-8')
        no_outcome = self.out / 'codex-findings-identity-no-outcome.md'
        no_outcome.write_text(text.replace('Outcome: I', 'nothing'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(no_outcome)]), 1)
        two = self.out / 'codex-findings-identity-two.md'
        two.write_text(text.replace('Outcome: I', 'Outcome: I\nOutcome: I'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(two)]), 1)
        missing = self.out / 'codex-findings-identity-missing.md'
        missing.write_text(text + '\n`probe-identity/captures/nope.json`\n', encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(missing)]), 1)

    def test_check_still_handles_first_findings_kind(self):
        sample = self.tmp / 'probe'
        shutil.copytree(SAMPLE_AGENTS, sample)
        work = self.tmp / 'work'
        probe.main(['summary', str(sample), '--out', str(work / 'probe'), '--config', str(SAMPLE_AGENTS / 'config.toml')])
        probe.main(['findings', str(sample), '--out', str(work)])
        self.assertEqual(probe.main(['check', 'findings', str(work / 'codex-findings.md')]), 0)


E2E = REPO / 'tests' / 'fixtures' / 'codex-probe' / 'sample-e2e'
E2E_PROBE = REPO / 'tests' / 'fixtures' / 'codex-probe' / 'sample-e2e-probe'
CAPS = REPO / 'tools' / 'codex-probe' / 'capabilities.json'
MANIFEST = {'name': 'my-agent', 'version': '0.8.0', 'skills': ['./']}
LIST_FORM = """Marketplace `my-plugins`
{root}/.agents/plugins/marketplace.json

PLUGIN                    STATUS              VERSION  SOURCE
my-agent@my-plugins       {status}  {version}    {root}/plugins/my-agent
my-agent-tray@my-plugins  not installed                {root}/plugins/my-agent-tray

Marketplace `other`
/x/other/.agents/plugins/marketplace.json

PLUGIN       STATUS         VERSION  SOURCE
a@other      not installed  1.0.0    /x
"""


APPROVED_PLAN = '# Plan\n\n## Approval\n- Approved 2026-11-04 00:55 G1b\n'
GUARD_FAKE = '''#!{py}
import glob, json, os, sys
with open({log!r}, 'a') as f:
    f.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd(), 'tasks': os.environ.get('MA_TASKS_DIR')}}) + '\\n')
if sys.argv[1:2] == ['exec']:
    repo = sys.argv[sys.argv.index('-C') + 1]
    for path in glob.glob(repo + '/.my-agent/*/run-log.md'):
        with open(path, 'a') as f:
            f.write('2026-01-01 11:00:00 guard: hook=scope-guard agent=my-agent:coder id=x1 tool=apply_patch '
                    'decision=deny why="read-only role" cwd=-\\n')
    print(json.dumps({{'type': 'thread.started'}}))
'''


class RoleCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake = self.tmp / 'fake-codex'
        self.log = self.tmp / 'fake-calls.jsonl'
        self.fake.write_text(GUARD_FAKE.format(py=sys.executable, log=str(self.log)), encoding='utf-8')
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)
        self.h = ['--codex', str(self.fake), '--codex-home', str(self.tmp / 'home')]
        self.dir = self.tmp / 'e2e'
        shutil.copytree(E2E / 'repo', self.dir / 'repo')
        (self.dir / 'data').mkdir()
        self.agent = self.dir / 'repo' / '.my-agent'
        (self.agent / '.active').write_text('task: 260101-demo\n', encoding='utf-8')
        (self.agent / '260101-demo' / 'plan.md').write_text(APPROVED_PLAN, encoding='utf-8')

    def run_check(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = probe.main(self.h + ['role-check', str(self.dir)])
        return code, out.getvalue(), err.getvalue()

    def refused(self, why):
        code, _, err = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn(why, err)
        self.assertFalse(self.log.exists())

    def test_refuses_without_active(self):
        (self.agent / '.active').unlink()
        self.refused('.active')

    def test_refuses_without_approval(self):
        (self.agent / '260101-demo' / 'plan.md').write_text('# Plan\n', encoding='utf-8')
        self.refused('Approved')

    def test_refuses_with_empty_approval_section(self):
        (self.agent / '260101-demo' / 'plan.md').write_text('# Plan\n\n## Approval\n\n## Other\n', encoding='utf-8')
        self.refused('Approved')

    def test_accepts_bare_approved_line(self):
        (self.agent / '260101-demo' / 'plan.md').write_text(
            '# Plan\n\n## Approval\n\nApproved 2026-01-01 10:00\n', encoding='utf-8')
        code, _, _ = self.run_check()
        self.assertEqual(code, 0)

    def test_refuses_with_two_tasks(self):
        (self.agent / '260102-other').mkdir()
        self.refused('exactly one task')

    def test_refuses_without_repo(self):
        shutil.rmtree(self.dir / 'repo')
        self.refused('repo')

    def test_passes_tasks_dir_and_prompt(self):
        code, out, _ = self.run_check()
        self.assertEqual(code, 0)
        execs = [c for c in calls(self.log) if c['argv'][:1] == ['exec']]
        self.assertEqual(len(execs), 1)
        argv = execs[0]['argv']
        self.assertEqual(execs[0]['tasks'], str((self.dir / 'data').resolve()))
        self.assertEqual(argv[:2], ['exec', '--json'])
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'workspace-write')
        self.assertIn('--skip-git-repo-check', argv)
        self.assertEqual(argv[argv.index('-C') + 1], str((self.dir / 'repo').resolve()))
        target = (self.dir / 'role-check.txt').resolve()
        self.assertEqual(argv[-1], probe.role_check_prompt(self.dir.resolve()))
        self.assertIn('agent_type `my-agent-coder`', argv[-1])
        self.assertNotIn('explorer', argv[-1])
        self.assertIn('task_name `role_check`', argv[-1])
        self.assertIn(f'*** Add File: {target}', argv[-1])
        self.assertIn('apply_patch', argv[-1])
        self.assertFalse(target.is_relative_to((self.dir / 'repo').resolve()))
        self.assertIn('exact result or error', argv[-1])

    def test_prompt_follows_ma_host(self):
        lib = REPO / 'plugins' / 'my-agent' / 'l4-tools-guards' / 'lib'
        sys.path.insert(0, str(lib))
        try:
            import ma_host
            want = ma_host.codex_agent('my-agent:coder')
        finally:
            sys.path.remove(str(lib))
        self.assertIn(f'agent_type `{want}`', probe.role_check_prompt(self.dir.resolve()))

    def test_saves_captures_and_prints_new_guard_lines_only(self):
        log = self.agent / '260101-demo' / 'run-log.md'
        old = log.read_text(encoding='utf-8')
        code, out, _ = self.run_check()
        self.assertEqual(code, 0)
        self.assertTrue((self.dir / 'role-check' / 'events.jsonl').is_file())
        self.assertTrue((self.dir / 'role-check' / 'stderr.txt').is_file())
        printed = [x for x in out.splitlines() if ' guard: ' in x]
        self.assertEqual(len(printed), 1)
        self.assertIn('agent=my-agent:coder', printed[0])
        self.assertTrue(log.read_text(encoding='utf-8').startswith(old))

    def test_changes_nothing_in_repo_but_the_hooks_lines(self):
        def tree():
            return {str(p.relative_to(self.dir / 'repo')): p.read_bytes() for p in (self.dir / 'repo').rglob('*')
                    if p.is_file() and '.git/' not in str(p) and p.name != 'run-log.md'}
        before = tree()
        self.run_check()
        self.assertEqual(tree(), before)
        self.assertEqual((self.agent / '.active').read_text(encoding='utf-8'), 'task: 260101-demo\n')

    def test_refuses_inside_repository(self):
        with self.assertRaises(SystemExit):
            probe.main(self.h + ['role-check', str(REPO / 'tests' / 'zz-rc')])
        self.assertFalse(self.log.exists())


class E2eSetupModelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.h = ['--codex', str(self.fake), '--codex-home', str(self.tmp / 'home')]

    def setup(self, models):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return probe.main(self.h + ['e2e-setup', str(self.tmp / 'e2e'), '--models', str(models)])

    def test_models_file_copied(self):
        src = self.tmp / 'models.json'
        src.write_text('{"codex": {"model": "gpt-6-luna"}}', encoding='utf-8')
        self.assertEqual(self.setup(src), 0)
        self.assertEqual((self.tmp / 'e2e' / 'data' / 'agent-models.json').read_text(encoding='utf-8'),
                         src.read_text(encoding='utf-8'))

    def test_invalid_json_refused(self):
        src = self.tmp / 'models.json'
        src.write_text('{not json', encoding='utf-8')
        self.assertEqual(self.setup(src), 1)
        self.assertFalse((self.tmp / 'e2e' / 'data' / 'agent-models.json').exists())

    def test_missing_file_refused(self):
        self.assertEqual(self.setup(self.tmp / 'nope.json'), 1)

    def test_without_models_no_file(self):
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(self.h + ['e2e-setup', str(self.tmp / 'e2e')]), 0)
        self.assertFalse((self.tmp / 'e2e' / 'data' / 'agent-models.json').exists())


class E2eGuardsTest(unittest.TestCase):
    def test_collect_fills_guards(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        base = tmp / 'e2e'
        shutil.copytree(E2E, base)
        log = base / 'repo' / '.my-agent' / '260101-demo' / 'run-log.md'
        with open(log, 'a', encoding='utf-8') as f:
            f.write('2026-01-01 11:00:00 guard: hook=scope-guard agent=my-agent:explorer id=x1 tool=apply_patch '
                    'decision=deny why="read-only role" cwd=-\n')
        (base / 'role-check').mkdir()
        (base / 'role-check' / 'events.jsonl').write_text('{}\n', encoding='utf-8')
        (base / 'role-check' / 'stderr.txt').write_text('', encoding='utf-8')
        out = tmp / 'out'
        code = probe.main(['--codex-home', str(base / 'codex-home'), 'e2e-collect', str(base), '--out', str(out)])
        self.assertEqual(code, 0)
        summary = json.loads((out / 'summary-e2e.json').read_text(encoding='utf-8'))
        self.assertEqual([(g['hook'], g['agent'], g['decision']) for g in summary['guards']],
                         [('scope-guard', 'my-agent:coder', 'deny'), ('scope-guard', 'my-agent:explorer', 'deny')])
        self.assertEqual(set(summary['guards'][1]), {'hook', 'agent', 'decision', 'line'})
        self.assertIn('guard: hook=scope-guard agent=my-agent:explorer', summary['guards'][1]['line'])
        self.assertTrue((out / 'role-check' / 'events.jsonl').is_file())
        self.assertTrue((out / 'role-check' / 'stderr.txt').is_file())

    def test_collect_without_role_check_folder(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        out = tmp / 'out'
        probe.main(['--codex-home', str(E2E / 'codex-home'), 'e2e-collect', str(E2E), '--out', str(out)])
        self.assertFalse((out / 'role-check').exists())
        self.assertEqual(len(json.loads((out / 'summary-e2e.json').read_text(encoding='utf-8'))['guards']), 1)


HOOKS = REPO / 'plugins' / 'my-agent' / 'l4-tools-guards' / 'hooks'
CODEX_FIX = REPO / 'plugins' / 'my-agent' / 'tests' / 'fixtures' / 'codex'
MAIN_SESSION = '019a0000-0000-7000-8000-000000000001'
FOREIGN_SESSION = '019a0000-0000-7000-8000-0000000000ee'


class RealHookAssumptionsTest(unittest.TestCase):
    """The Assumes lines of the role check, against the real hook scripts on a temp approved task."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp.resolve()
        self.repo = self.root / 'repo'
        self.agent = self.repo / '.my-agent'
        (self.agent / '260101-demo').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.agent / '.active').write_text(
            f'task: 260101-demo\nphase: 5\nsession: {MAIN_SESSION}\nstarted: 2026-01-01 09:00\n', encoding='utf-8')
        self.plan = self.agent / '260101-demo' / 'plan.md'
        self.plan.write_text(APPROVED_PLAN, encoding='utf-8')
        self.env = dict(os.environ, MA_TASKS_DIR=str(self.root / 'data'))

    def fixture(self, name, **over):
        d = json.loads((CODEX_FIX / name).read_text(encoding='utf-8'))
        d.update(over, cwd=str(self.repo))
        return d

    def hook(self, script, payload):
        return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload), capture_output=True,
                              text=True, cwd=self.repo, env=self.env, timeout=30)

    def spawn(self, agent, session):
        d = self.fixture('hook-pre-tool-use-spawn-agent.json', session_id=session)
        d['tool_input'] = dict(d['tool_input'], agent_type=agent)
        return d

    def test_foreign_session_spawn_passes_plan_approved_check(self):
        self.plan.write_text('# Plan\n', encoding='utf-8')   # not approved: the control must be denied
        control = self.hook('plan-approved-check.py', self.spawn('my-agent-coder', MAIN_SESSION))
        self.assertIn('deny', control.stdout)
        r = self.hook('plan-approved-check.py', self.spawn('my-agent-coder', FOREIGN_SESSION))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)
        self.plan.write_text(APPROVED_PLAN, encoding='utf-8')
        r = self.hook('plan-approved-check.py', self.spawn('my-agent-explorer', FOREIGN_SESSION))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_explorer_apply_patch_denied_with_guard_line(self):
        d = self.fixture('hook-pre-tool-use-worker-file-change.json', session_id=FOREIGN_SESSION,
                         agent_type='my-agent-explorer')
        d['tool_input'] = {'command': '*** Begin Patch\n*** Add File: role-check.txt\n+x\n*** End Patch'}
        r = self.hook('scope-guard.py', d)
        self.assertEqual(r.returncode, 2, r.stderr)
        lines = [x for x in (self.agent / '260101-demo' / 'run-log.md').read_text(encoding='utf-8').splitlines()
                 if ' guard: ' in x]
        self.assertEqual(len(lines), 1)
        self.assertIn('hook=scope-guard', lines[0])
        self.assertIn('agent=my-agent:explorer', lines[0])
        self.assertIn('decision=deny', lines[0])

    def coder_patch(self, path):
        d = self.fixture('hook-pre-tool-use-worker-file-change.json', session_id=FOREIGN_SESSION,
                         agent_type='my-agent-coder')
        d['tool_input'] = {'command': f'*** Begin Patch\n*** Add File: {path}\n+x\n*** End Patch'}
        return d

    def guard_lines(self):
        log = self.agent / '260101-demo' / 'run-log.md'
        return [x for x in log.read_text(encoding='utf-8').splitlines() if ' guard: ' in x] if log.is_file() else []

    def test_coder_apply_patch_outside_location_denied_with_guard_line(self):
        r = self.hook('scope-guard.py', self.coder_patch(self.root / 'role-check.txt'))
        self.assertEqual(r.returncode, 2, r.stderr)
        lines = self.guard_lines()
        self.assertEqual(len(lines), 1)
        for part in ('hook=scope-guard', 'agent=my-agent:coder', 'decision=deny'):
            self.assertIn(part, lines[0])

    def test_coder_apply_patch_inside_location_let_through(self):
        r = self.hook('scope-guard.py', self.coder_patch(self.repo / 'src-new.txt'))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)
        self.assertEqual(self.guard_lines(), [])

    def test_session_notice_leaves_active_unchanged(self):
        active = self.agent / '.active'
        before = active.read_bytes()
        r = self.hook('session-notice.py', self.fixture('hook-session-start.json', session_id=FOREIGN_SESSION))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(active.read_bytes(), before)


class E2eToolingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.h = ['--codex', str(self.fake), '--codex-home', str(E2E / 'codex-home')]

    def collect(self, name='out'):
        out = self.tmp / name
        code = probe.main(self.h + ['e2e-collect', str(E2E), '--out', str(out)])
        self.assertEqual(code, 0)
        return out

    def test_setup_layout(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(probe.main(self.h + ['e2e-setup', str(self.tmp / 'e2e')]), 0)
        repo = self.tmp / 'e2e' / 'repo'
        self.assertTrue((repo / '.git').is_dir())
        self.assertTrue((repo / 'calc.py').is_file())
        self.assertTrue((repo / 'test_calc.py').is_file())
        self.assertTrue((self.tmp / 'e2e' / 'data').is_dir())
        text = buf.getvalue()
        self.assertIn(str((self.tmp / 'e2e' / 'data').resolve()), text)
        self.assertIn(str(repo.resolve()), text)
        self.assertNotIn('$my-agent', text)
        self.assertIn('Request text: run probe.py e2e-request <install snapshot folder> after the install', text)
        self.assertFalse(self.log.exists())
        with self.assertRaises(SystemExit):
            probe.main(self.h + ['e2e-setup', str(REPO / 'tests' / 'zz-e2e')])

    def test_collect_picks_only_given_session_ids(self):
        out = self.collect()
        names = sorted(p.name for p in out.glob('session-*.jsonl'))
        self.assertEqual(names, ['session-sess1111-aaaa.jsonl', 'session-sess2222-bbbb.jsonl'])
        self.assertNotIn('other9999', ''.join(p.read_text(encoding='utf-8') for p in out.glob('session-*')))
        self.assertTrue((out / 'run-log.txt').is_file())
        self.assertIn('plan.md', (out / 'files.txt').read_text(encoding='utf-8'))
        self.assertTrue((out / 'task' / 'plan.md').is_file())
        reduced = (out / 'session-sess1111-aaaa.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('secret prose', reduced)
        self.assertNotIn('hello prose', reduced)
        self.assertEqual(len(reduced.splitlines()), 4)

    def test_collect_summary(self):
        summary = json.loads((self.collect() / 'summary-e2e.json').read_text(encoding='utf-8'))
        self.assertEqual([s['n'] for s in summary['steps_reached']], [1, 3, 5])
        self.assertEqual(summary['steps_reached'][2]['line'], 5)
        self.assertEqual(summary['hooks_fired'], {'scope-guard': 1})
        self.assertEqual(summary['subagents'][0]['agent'], 'my-agent:coder')
        self.assertEqual(summary['failures'][0]['source'], 'e2e/session-sess1111-aaaa.jsonl line 2')
        self.assertIn('unknown agent_type', summary['failures'][0]['text'])
        self.assertFalse(self.log.exists())

    def test_collect_refuses_out_inside_repo(self):
        with self.assertRaises(SystemExit):
            probe.main(self.h + ['e2e-collect', str(E2E), '--out', str(REPO / 'tests' / 'zz-out')])
        self.assertFalse((REPO / 'tests' / 'zz-out').exists())

    def test_snapshot_cache_and_skills(self):
        home = self.tmp / 'home'
        ver = home / 'plugins' / 'cache' / 'mk' / 'pl' / '1.2.3'
        (ver / '.codex-plugin').mkdir(parents=True)
        (ver / '.codex-plugin' / 'plugin.json').write_text(json.dumps(MANIFEST), encoding='utf-8')
        (ver / 'SKILL.md').write_text('secret body', encoding='utf-8')
        out = self.tmp / 'snap'
        h = ['--codex', str(self.fake), '--codex-home', str(home)]
        self.assertEqual(probe.main(h + ['snapshot', '--out', str(out), '--skills', str(self.tmp), '--cache', 'mk/pl']), 0)
        files = (out / 'cache-files.txt').read_text(encoding='utf-8').split('\n')
        self.assertIn('1.2.3/SKILL.md', files)
        self.assertIn('1.2.3/.codex-plugin/plugin.json', files)
        self.assertEqual(json.loads((out / 'cache' / '1.2.3' / 'codex-plugin.json').read_text(encoding='utf-8')), MANIFEST)
        self.assertEqual(sorted(str(p.relative_to(out)) for p in (out / 'cache').rglob('*') if p.is_file()),
                         ['cache/1.2.3/codex-plugin.json'])
        self.assertTrue((out / 'skills-list.txt').is_file())
        self.assertEqual([c['argv'] for c in calls(self.log) if c['argv'][:1] == ['exec']], [])
        self.assertEqual(len([c for c in calls(self.log) if c['argv'][:2] == ['debug', 'prompt-input']]), 1)
        self.assertEqual((out / 'skills-source.txt').read_text(encoding='utf-8').strip(), 'none')
        for argv in [c['argv'] for c in calls(self.log)]:
            self.assertNotIn(argv[:1], (['login'], ['logout']))
            self.assertFalse(set(argv) & {'add', 'remove', 'upgrade'}, argv)

    def report(self, e2e, name='report.md'):
        out = self.tmp / name
        code = probe.main(['report', str(e2e), '--findings', str(E2E_PROBE / 'findings.json'),
                           '--findings', str(E2E_PROBE / 'findings-identity.json'), '--out', str(out)])
        self.assertEqual(code, 0)
        return out

    def test_report_sections_and_unlisted(self):
        e2e = self.collect()
        text = self.report(e2e).read_text(encoding='utf-8')
        for head in ('## Run summary', '## Gaps', '## Unlisted failures'):
            self.assertIn(head, text)
        self.assertIn('| Step | Reached | Evidence |', text)
        self.assertIn('| # | Capability | Needed by | What was tried | Result | Effect on the workflow | Evidence |', text)
        self.assertIn('probe/captures/a.json', text)
        self.assertIn('probe-identity/captures/b.json', text)
        self.assertIn('e2e/run-log.txt line 5', text)
        self.assertNotIn('Agent identity on tool calls |', text.split('## Gaps')[1])  # outcome I: not a gap row
        listed = text.split('## Unlisted failures')[1]
        self.assertIn('(none)', listed)
        summary = json.loads((e2e / 'summary-e2e.json').read_text(encoding='utf-8'))
        summary['failures'].append({'step': '5 Execute', 'source': 'e2e/run-log.txt line 3', 'text': 'disk exploded'})
        (e2e / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        text = self.report(e2e, 'report2.md').read_text(encoding='utf-8')
        tail = text.split('## Unlisted failures')[1]
        self.assertIn('Unlisted failure:', tail)
        self.assertIn('disk exploded', tail)
        self.assertNotIn('unknown agent_type', tail)

    def check_report(self, path, e2e, *extra):
        return probe.main(['check', 'report', str(path), '--e2e', str(e2e)] + list(extra))

    def test_check_report(self):
        e2e = self.collect()
        good = self.report(e2e)
        probe_root = self.tmp / 'proot'
        shutil.copytree(E2E_PROBE, probe_root)
        self.assertEqual(self.check_report(good, e2e, '--probe-root', str(probe_root)), 0)
        # default probe root is the report's folder
        self.assertEqual(self.check_report(good, e2e), 1)
        shutil.copytree(E2E_PROBE / 'probe', self.tmp / 'probe')
        self.assertEqual(self.check_report(good, e2e), 1)  # probe-identity/ still missing there
        shutil.copytree(E2E_PROBE / 'probe-identity', self.tmp / 'probe-identity')
        self.assertEqual(self.check_report(good, e2e), 0)
        text = good.read_text(encoding='utf-8')
        bad_line = self.tmp / 'bad-line.md'
        bad_line.write_text(text.replace('e2e/run-log.txt line 5', 'e2e/run-log.txt line 99'), encoding='utf-8')
        self.assertEqual(self.check_report(bad_line, e2e, '--probe-root', str(probe_root)), 1)
        bad_col = self.tmp / 'bad-col.md'
        bad_col.write_text(text.replace('| gap-1 |', '| gap-1 | |', 1), encoding='utf-8')
        self.assertEqual(self.check_report(bad_col, e2e, '--probe-root', str(probe_root)), 1)
        no_section = self.tmp / 'no-section.md'
        no_section.write_text(text.replace('## Gaps', '## Other'), encoding='utf-8')
        self.assertEqual(self.check_report(no_section, e2e, '--probe-root', str(probe_root)), 1)
        summary = json.loads((e2e / 'summary-e2e.json').read_text(encoding='utf-8'))
        summary['failures'].append({'step': '5 Execute', 'source': 'e2e/run-log.txt line 3', 'text': 'disk exploded'})
        (e2e / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        unlisted = self.report(e2e, 'report2.md')
        self.assertEqual(self.check_report(unlisted, e2e, '--probe-root', str(probe_root)), 1)

    def test_ignored_failures(self):
        caps = json.loads(probe.CAPABILITIES.read_text(encoding='utf-8'))
        self.assertIsInstance(caps['ignored_failures'], list)
        self.assertTrue(caps['ignored_failures'])
        for entry in caps['ignored_failures']:
            self.assertTrue(entry['pattern'].strip())
            self.assertTrue(entry['why'].strip())
        e2e = self.collect()
        probe_root = self.tmp / 'proot'
        shutil.copytree(E2E_PROBE, probe_root)
        summary = json.loads((e2e / 'summary-e2e.json').read_text(encoding='utf-8'))
        slip = "run-log: unknown kind 'codex-agents'; one of: ask, answer"
        summary['failures'].append({'step': '2 Intake', 'source': 'e2e/run-log.txt line 3', 'text': slip})
        summary['failures'].append({'step': '2 Intake', 'source': 'e2e/run-log.txt line 4',
                                    'text': "fatal: /h/.codex/plugins/cache/m/p/1: '/h/x' is outside repository at '/tmp/r'"})
        (e2e / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        report = self.report(e2e, 'report-ign.md')
        text = report.read_text(encoding='utf-8')
        ignored = text.split('## Ignored failures')[1].split('## Unlisted failures')[0]
        self.assertIn(f'Ignored failure: step 2 Intake, "{slip}" (e2e/run-log.txt line 3): ', ignored)
        self.assertNotIn('outside repository', ignored)
        self.assertNotIn('codex-agents', text.split('## Unlisted failures')[1])
        self.assertEqual(self.check_report(report, e2e, '--probe-root', str(probe_root)), 0)
        summary['failures'].append({'step': '5 Execute', 'source': 'e2e/run-log.txt line 3', 'text': 'disk exploded'})
        (e2e / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        bad = self.report(e2e, 'report-bad.md')
        self.assertIn('Unlisted failure:', bad.read_text(encoding='utf-8').split('## Unlisted failures')[1])
        self.assertEqual(self.check_report(bad, e2e, '--probe-root', str(probe_root)), 1)

    def spawn_collect(self, name='spawn-out'):
        spawn = E2E.parent / 'sample-e2e-spawn'
        out = self.tmp / name
        code = probe.main(['--codex-home', str(spawn / 'codex-home'), 'e2e-collect', str(spawn), '--out', str(out)])
        self.assertEqual(code, 0)
        return out

    def test_collect_spawns(self):
        out = self.spawn_collect()
        summary = json.loads((out / 'summary-e2e.json').read_text(encoding='utf-8'))
        self.assertEqual([(s['agent_type'], s['ok']) for s in summary['spawns']],
                         [('worker', True), ('my-agent-coder', False), ('my-agent-coder', True)])
        self.assertEqual(summary['spawns'][0]['line'], 'e2e/session-sess4444-dddd.jsonl line 2')
        self.assertEqual(summary['spawns'][1]['error'], 'unknown agent_type my-agent-coder second line')
        texts = [f['text'] for f in summary['failures']]
        self.assertEqual(texts, ['subagent started without a my-agent role: agent_type=worker',
                                 'unknown agent_type my-agent-coder second line'])
        reduced = (out / 'session-sess4444-dddd.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('secret task prose', reduced)
        self.assertEqual(len(reduced.splitlines()), 9)
        self.assertIn('"agent_type": "worker"', reduced)

    def test_check_report_spawns_without_start_line(self):
        out = self.spawn_collect()
        report = self.report(out)
        probe_root = self.tmp / 'proot'
        shutil.copytree(E2E_PROBE, probe_root)
        self.assertEqual(self.check_report(report, out, '--probe-root', str(probe_root)), 0)
        summary = json.loads((out / 'summary-e2e.json').read_text(encoding='utf-8'))
        summary['failures'] = []
        (out / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        self.assertEqual(self.check_report(report, out, '--probe-root', str(probe_root)), 1)
        summary['subagents'] = [{'agent': 'my-agent:coder', 'id': 'x', 'line': 2}]
        (out / 'summary-e2e.json').write_text(json.dumps(summary), encoding='utf-8')
        self.assertEqual(self.check_report(report, out, '--probe-root', str(probe_root)), 0)

    def test_subagent_row_states_the_evidence(self):
        rows = {r['id']: r for r in json.loads(CAPS.read_text(encoding='utf-8'))['rows']}
        row = rows['subagent-start']
        self.assertEqual(row['status'], 'available')
        self.assertIn('e2e', row['how_tried'])
        for text in ('8 start lines', '8 stop lines', 'lines 6, 10, 19, 24 and 28', 'lines 7, 11, 20, 25 and 29',
                     'lines 32, 35 and 38', 'my-agent-<role>'):
            self.assertIn(text, row['result'])
        self.assertIn('scope-guard role checks apply instead', row['effect'])
        for old in ('6 spawn_agent calls', 'other 5'):
            self.assertNotIn(old, row['result'])
        hooks = rows['subagent-hooks']
        self.assertEqual(hooks['status'], 'available')
        for text in ('8 start lines', '8 stop lines', 'guard line 39', 'decision=deny'):
            self.assertIn(text, hooks['result'])
        for old in ('6 spawn_agent calls', 'other 5'):
            self.assertNotIn(old, hooks['result'])
        preset = rows['model-preset']
        self.assertEqual(preset['status'], 'gap')
        self.assertIn('model=-', preset['result'])
        self.assertIn('no codex section', preset['result'])
        self.assertIn('subagent started without a my-agent role', row['failure_patterns'])
        self.assertIn('unknown agent_type', row['failure_patterns'])
        for text in ('subagent started without a my-agent role: agent_type=worker', 'unknown agent_type foo'):
            self.assertTrue(any(re.search(p, text, re.I) for p in row['failure_patterns']))

    def install_folder(self, root='/Users/x/repo', status='installed, enabled', version='0.8.0', cache=True,
                       skills='my-agent:monitor\n', cached=None, cache_version='0.8.0', source='prompt-input'):
        folder = self.tmp / 'install'
        shutil.rmtree(folder, True)
        (folder / 'cache' / cache_version).mkdir(parents=True)
        (folder / 'plugin-list.txt').write_text(LIST_FORM.format(root=root, status=status, version=version), encoding='utf-8')
        (folder / 'skills-list.txt').write_text(skills, encoding='utf-8')
        if source is not None:
            (folder / 'skills-source.txt').write_text(source + '\n', encoding='utf-8')
        if cache:
            (folder / 'cache' / cache_version / 'codex-plugin.json').write_text(json.dumps(cached or MANIFEST), encoding='utf-8')
        return folder

    def repo_root(self, manifest=MANIFEST):
        root = self.tmp / 'repo-root'
        (root / 'plugins' / 'my-agent' / '.codex-plugin').mkdir(parents=True, exist_ok=True)
        (root / 'plugins' / 'my-agent' / '.codex-plugin' / 'plugin.json').write_text(json.dumps(manifest), encoding='utf-8')
        return root

    def check_install(self, folder, root, *extra):
        return probe.main(['check', 'install', str(folder), '--root', str(root)] + list(extra))

    def test_check_install(self):
        root = self.repo_root()
        # the list names a made-up root; --root must equal it, so write the list with the real temp root
        ok = self.install_folder(root=str(root))
        self.assertEqual(self.check_install(ok, root), 0)
        self.assertEqual(self.check_install(ok, root, '--version', '0.8.0'), 0)
        self.assertEqual(self.check_install(ok, '/Users/x/other'), 1)
        self.assertEqual(self.check_install(self.install_folder(root=str(root), status='installed, disabled'), root), 1)
        self.assertEqual(self.check_install(self.install_folder(root=str(root), skills='my-agent\n'), root), 1)
        self.assertEqual(self.check_install(self.install_folder(root=str(root), cache=False), root), 1)
        self.assertEqual(self.check_install(self.install_folder(root=str(root), cached={**MANIFEST, 'description': 'x'}), root), 1)
        old = self.install_folder(root=str(root), version='0.7.0', cache_version='0.7.0', cached={**MANIFEST, 'version': '0.7.0'})
        root = self.repo_root({**MANIFEST, 'version': '0.7.0'})
        self.assertEqual(self.check_install(old, root), 0)
        self.assertEqual(self.check_install(old, root, '--version', '0.8.0'), 1)

    def test_check_install_default_root_is_repository_root(self):
        real = json.loads((REPO / 'plugins' / 'my-agent' / '.codex-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        folder = self.install_folder(root=str(REPO), version=real['version'], cache_version=real['version'], cached=real)
        self.assertEqual(probe.main(['check', 'install', str(folder)]), 0)

    def test_check_install_old_claude_form_copy_fails(self):
        root = self.repo_root()
        folder = self.install_folder(root=str(root), cache=False)
        (folder / 'cache' / '0.8.0' / 'claude-plugin.json').write_text(json.dumps(MANIFEST), encoding='utf-8')
        self.assertEqual(self.check_install(folder, root), 1)

    def test_capabilities_rows(self):
        rows = json.loads(CAPS.read_text(encoding='utf-8'))['rows']
        self.assertGreaterEqual(len(rows), 15)
        ids = set()
        for row in rows:
            for key in ('id', 'capability', 'status', 'needed_by', 'how_tried', 'result', 'effect', 'facts', 'failure_patterns'):
                self.assertTrue(row.get(key), (row.get('id'), key))
            self.assertIn(row['status'], ('available', 'partial', 'gap'))
            self.assertNotIn(row['id'], ids)
            ids.add(row['id'])
            for needed in row['needed_by']:
                self.assertTrue((REPO / needed).is_file(), needed)
        by = {r['id']: r for r in rows}
        self.assertNotEqual(by['agent-identity']['status'], 'gap')
        self.assertIn('Outcome I', by['agent-identity']['result'])
        popup = by['question-popup']
        self.assertEqual(popup['status'], 'available')
        self.assertEqual(popup['effect'], "gates are asked through Codex's question tool with the same choices (hosts.md, D5)")
        self.assertIn('request_user_input_async', popup['result'])
        self.assertIn('options', popup['result'])
        self.assertIn('crash ends in exit 2', by['fail-closed-malformed']['effect'])
        self.assertIn('onFailure', by['on-failure-block']['capability'])

    def test_no_home_path_in_new_files(self):
        for path in list(E2E.rglob('*')) + list(E2E_PROBE.rglob('*')) + [CAPS, PROBE]:
            if path.is_file():
                text = path.read_text(encoding='utf-8')
                self.assertNotIn('jahoon' + 'jin', text, str(path))


# ---- skills diagnosis (u25) ----

import io
import re
from contextlib import redirect_stdout

FIXS = REPO / 'tests' / 'fixtures' / 'codex-probe'
ROOT_SKILL = REPO / 'plugins' / 'my-agent' / 'SKILL.md'
VARIANTS = ['s0', 's1', 's2', 's3', 's4', 's5']


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def run_main(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = probe.main(argv)
    return code, out.getvalue()


class SkillsKitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.code, self.printed = run_main(['kit-skills', str(self.tmp)])
        self.kit = self.tmp / 'kit'

    def plugin(self, v):
        return self.kit / 'plugins' / f'ma-probe-{v}'

    def codex_manifest(self, v):
        return read_json(self.plugin(v) / '.codex-plugin' / 'plugin.json')

    def test_marketplace_and_plugin_names(self):
        self.assertEqual(self.code, 0)
        market = read_json(self.kit / '.agents' / 'plugins' / 'marketplace.json')
        self.assertEqual(market['name'], 'ma-probe')
        names = [p['name'] for p in market['plugins']]
        self.assertEqual(names, [f'ma-probe-{v}' for v in VARIANTS])
        for name in names:
            self.assertRegex(name, r'^ma-probe-s[0-5]$')

    def test_manifest_skills_value_per_variant(self):
        want = {'s0': ['./'], 's1': './alt/', 's3': './', 's4': ['./'], 's5': './codex/skills/'}
        for v in VARIANTS:
            manifest = self.codex_manifest(v)
            if v == 's2':
                self.assertNotIn('skills', manifest)
            else:
                self.assertEqual(manifest['skills'], want[v], v)
            self.assertEqual(manifest['name'], f'ma-probe-{v}')
            self.assertTrue((self.plugin(v) / '.claude-plugin' / 'plugin.json').is_file(), v)

    def test_no_hooks_and_no_agents(self):
        for v in VARIANTS:
            for rel in ('.codex-plugin', '.claude-plugin'):
                manifest = read_json(self.plugin(v) / rel / 'plugin.json')
                self.assertNotIn('hooks', manifest)
                self.assertNotIn('agents', manifest)
            names = [p.name for p in self.plugin(v).rglob('*')]
            self.assertFalse([n for n in names if 'hooks' in n or n == 'agents' or n.endswith('.toml')], v)

    def test_root_bodies(self):
        size = lambda v: (self.plugin(v) / 'SKILL.md').stat().st_size
        for v in ('s0', 's1', 's2', 's3', 's5'):
            self.assertGreaterEqual(size(v), 45000, v)
        self.assertLessEqual(size('s4'), 300)
        root = (self.plugin('s0') / 'SKILL.md').read_text(encoding='utf-8')
        front = root.split('---')[1]
        self.assertIn('name: ma-probe-s0\n', front)
        for key in ('description:', 'argument-hint:', 'model: opus'):
            self.assertIn(key, front)
        s4 = (self.plugin('s4') / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('name: ma-probe-s4-root\n', s4)
        self.assertNotIn('model:', s4)
        sub = (self.plugin('s0') / 'skills' / 'ma-probe-s0-sub' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('argument-hint:', sub)
        self.assertIn('disable-model-invocation:', sub)

    def test_s1_alt_skills(self):
        alt = self.plugin('s1') / 'alt'
        self.assertFalse((self.plugin('s1') / 'skills').exists())
        text = lambda d: (alt / d / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('name: ma-probe-s1-named\n', text('ma-probe-s1-dir'))
        self.assertIn('name: ma-probe-s1\n', text('ma-probe-s1'))
        self.assertGreaterEqual((alt / 'ma-probe-s1-big' / 'SKILL.md').stat().st_size, 45000)
        self.assertLess((alt / 'ma-probe-s1' / 'SKILL.md').stat().st_size, 1000)
        front = text('ma-probe-s1-front')
        self.assertIn('argument-hint:', front)
        self.assertIn('model: opus', front)
        for d in ('ma-probe-s1', 'ma-probe-s1-big'):
            head = text(d).split('---')[1]
            self.assertEqual(sorted(l.split(':')[0] for l in head.strip().splitlines()), ['description', 'name'])

    def test_s5_symlinks_are_relative(self):
        base = self.plugin('s5') / 'codex' / 'skills'
        link = base / 'ma-probe-s5' / 'SKILL.md'
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), '../../../SKILL.md')
        self.assertEqual(link.resolve(), (self.plugin('s5') / 'SKILL.md').resolve())
        sub = base / 'ma-probe-s5-sub'
        self.assertTrue(sub.is_symlink())
        self.assertEqual(os.readlink(sub), '../../skills/ma-probe-s5-sub')
        self.assertTrue((sub / 'SKILL.md').is_file())

    def test_every_description_starts_with_its_unique_marker(self):
        seen = set()
        for v in VARIANTS:
            for path in self.plugin(v).rglob('SKILL.md'):
                if path.is_symlink() or path.parent.is_symlink():
                    continue
                m = re.search(r'^description: (.*)$', path.read_text(encoding='utf-8'), re.M)
                marker = m.group(1).split()[0]
                self.assertRegex(marker, rf'^MA-SKILL-{v}-\w+$')
                self.assertNotIn(marker, seen)
                seen.add(marker)
        specs = probe.kit_skill_specs()
        self.assertEqual({s['marker'] for v in specs.values() for s in v['skills']}, seen)

    def test_no_line_of_the_real_skill_file_in_the_kit(self):
        lines = {l for l in ROOT_SKILL.read_text(encoding='utf-8').splitlines() if len(l) > 40}
        self.assertTrue(lines)
        for path in self.kit.rglob('*'):
            if path.is_file() and not path.is_symlink():
                for line in path.read_text(encoding='utf-8').splitlines():
                    self.assertNotIn(line, lines, str(path))

    def test_prints_commands_and_runs_none(self):
        self.assertIn('codex plugin marketplace add ' + str(self.kit.resolve()), self.printed)
        for v in VARIANTS:
            self.assertIn(f'codex plugin add ma-probe-{v}@ma-probe', self.printed)
            self.assertIn(f'codex plugin remove ma-probe-{v}@ma-probe', self.printed)
        self.assertIn('codex plugin marketplace remove ma-probe', self.printed)

    def test_rerun_overwrites(self):
        self.assertEqual(run_main(['kit-skills', str(self.tmp)])[0], 0)
        self.assertTrue((self.plugin('s5') / 'codex' / 'skills' / 'ma-probe-s5' / 'SKILL.md').is_symlink())


class SkillsRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fake, self.log = make_fake(self.tmp)
        self.base = self.tmp / 'probe'
        self.home = self.tmp / 'h'

    def run_scenario(self, scenario):
        return probe.main(['--codex', str(self.fake), '--codex-home', str(self.home), 'run', str(self.base), scenario])

    def test_live_calls(self):
        self.assertEqual(self.run_scenario('skills-live'), 0)
        got = calls(self.log)
        work = os.path.realpath(self.base / 'work-skills-live')
        argvs = [c['argv'] for c in got]
        for help_argv in (['--help'], ['plugin', '--help'], ['debug', '--help']):
            self.assertIn(help_argv, argvs)
        pi = [c for c in got if c['argv'][:2] == ['debug', 'prompt-input']]
        self.assertEqual(len(pi), 1)
        self.assertEqual(pi[0]['argv'][2], 'Reply with exactly: ok.')
        execs = [c for c in got if c['argv'][:1] == ['exec']]
        self.assertEqual(len(execs), 1)
        argv = execs[0]['argv']
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only')
        self.assertIn('--skip-git-repo-check', argv)
        self.assertEqual(argv[-1], 'Reply with exactly: ok. Do not run any command.')
        for c in pi + execs:
            self.assertEqual(os.path.realpath(c['cwd']), work)
            self.assertNotEqual(os.path.realpath(c['cwd']), os.path.realpath(REPO))
        self.assertFalse((self.base / 'work-skills-live' / '.git').exists())
        raw = self.base / 'raw'
        self.assertTrue((raw / 'skills-live-prompt-input.txt').is_file())
        self.assertTrue((raw / 'skills-live-events.jsonl').is_file())
        self.assertTrue(list(raw.glob('skills-live-help-*.txt')))
        self.assertFalse((self.base / 'out').exists())

    def test_kit_has_no_help_calls(self):
        self.assertEqual(self.run_scenario('skills-kit'), 0)
        got = [c['argv'] for c in calls(self.log)]
        self.assertNotIn(['plugin', '--help'], got)
        self.assertNotIn(['debug', '--help'], got)
        self.assertTrue(any(a[:2] == ['debug', 'prompt-input'] for a in got))
        self.assertEqual(len([a for a in got if a[:1] == ['exec']]), 1)
        self.assertTrue((self.base / 'work-skills-kit').is_dir())
        self.assertTrue((self.base / 'raw' / 'skills-kit-prompt-input.txt').is_file())

    def test_session_record_copied_by_thread_id(self):
        sessions = self.home / 'sessions' / '2026' / '01' / '01'
        sessions.mkdir(parents=True)
        (sessions / 'rollout-x-thr-aaaa1111.jsonl').write_text('{}\n', encoding='utf-8')
        (sessions / 'rollout-y-other-bbbb2222.jsonl').write_text('{}\n', encoding='utf-8')
        script = self.tmp / 'fake-codex-id'
        script.write_text('#!%s\nimport json, sys\nif sys.argv[1:2] == ["exec"]:\n    print(json.dumps({"type": "thread.started", "thread_id": "thr-aaaa1111"}))\n' % sys.executable,
                          encoding='utf-8')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        code = probe.main(['--codex', str(script), '--codex-home', str(self.home), 'run', str(self.base), 'skills-live'])
        self.assertEqual(code, 0)
        copied = sorted(p.name for p in (self.base / 'sessions' / 'skills-live').glob('*.jsonl'))
        self.assertEqual(copied, ['rollout-x-thr-aaaa1111.jsonl'])

    def test_refuses_inside_repo(self):
        with self.assertRaises(SystemExit):
            probe.main(['--codex', str(self.fake), 'run', str(REPO / 'zz-skills-run'), 'skills-live'])
        self.assertFalse((REPO / 'zz-skills-run').exists())

    def test_no_new_subcommand_changes_codex_settings(self):
        self.run_scenario('skills-live')
        self.run_scenario('skills-kit')
        kit = self.tmp / 'k'
        probe.main(['--codex', str(self.fake), '--codex-home', str(self.home), 'kit-skills', str(kit)])
        for name in ('skills-nohard', 'skills-m3'):
            src = self.tmp / name
            shutil.copytree(FIXS / name, src)
            probe.main(['--codex', str(self.fake), '--codex-home', str(FIXS / 'skills-codex-home'), 'summary-skills',
                        str(src), '--out', str(self.tmp / ('o-' + name))])
            probe.main(['findings-skills', str(self.tmp / ('o-' + name))])
        self.assertTrue(calls(self.log))
        for c in calls(self.log):
            argv = c['argv']
            self.assertNotEqual(argv[:2], ['plugin', 'add'])
            self.assertNotEqual(argv[:2], ['plugin', 'remove'])
            self.assertNotEqual(argv[:3], ['plugin', 'marketplace', 'add'])
            self.assertNotEqual(argv[:3], ['plugin', 'marketplace', 'remove'])
            self.assertNotEqual(argv[:3], ['plugin', 'marketplace', 'upgrade'])


ENTRY_TEXT = """## Skills
### Skill roots
- `r0` = `/Users/x/.agents/skills`
- `r6` = `/Users/x/.codex/plugins/cache/ma-probe`
### Available skills
- pdf: Use this skill whenever the user wants to do anything with PDF files. (file: r0/pdf/SKILL.md)
- ma-probe:ma-probe-dir: Probe skill in a skills folder. Use when asked to use ma-probe-dir. (file: r6/ma-probe/0.0.1/skills/ma-probe-dir/SKILL.md)
- other:thing: A description that is
  re-wrapped  across
  lines. (file: r9/thing/SKILL.md)
- plain: Text without a root alias. (file: /abs/plain/SKILL.md)
</skills_instructions>"""
LONG = ('MA-SKILL-s9-sub Probe skill with a rather long description, made-up text, used to test that a listing '
        'entry cut short by Codex still matches the skill when enough of it is left.')


class SkillsListingRuleTest(unittest.TestCase):
    def test_parse_entries_and_aliases(self):
        entries, aliases = probe.parse_listing(ENTRY_TEXT)
        self.assertEqual(aliases['r6'], '/Users/x/.codex/plugins/cache/ma-probe')
        by = {e['name']: e for e in entries}
        self.assertEqual(set(by), {'pdf', 'ma-probe:ma-probe-dir', 'other:thing', 'plain'})
        self.assertEqual(by['ma-probe:ma-probe-dir']['path'],
                         '/Users/x/.codex/plugins/cache/ma-probe/ma-probe/0.0.1/skills/ma-probe-dir/SKILL.md')
        self.assertEqual(by['ma-probe:ma-probe-dir']['raw_path'], 'r6/ma-probe/0.0.1/skills/ma-probe-dir/SKILL.md')
        self.assertEqual(by['other:thing']['path'], 'unresolved')
        self.assertEqual(by['plain']['path'], '/abs/plain/SKILL.md')
        self.assertEqual(by['pdf']['line'], 6)

    def test_rewrapped_description_with_doubled_spaces_matches(self):
        entries, _ = probe.parse_listing(ENTRY_TEXT)
        e = next(x for x in entries if x['name'] == 'other:thing')
        self.assertTrue(probe.description_matches(e['description'], 'A description that is re-wrapped across lines.'))

    def test_cut_description_needs_sixty_characters(self):
        self.assertTrue(probe.description_matches(LONG[:61], LONG))
        self.assertEqual(len(probe.norm_desc(LONG[:60])), 59)   # the space at the cut does not count
        self.assertTrue(probe.description_matches(LONG[:62], LONG))
        self.assertTrue(probe.description_matches('ab' * 30, 'ab' * 30 + ' tail'))
        self.assertFalse(probe.description_matches('ab' * 29 + 'a', 'ab' * 29 + 'ab tail'))
        self.assertTrue(probe.description_matches(LONG[:90] + '…', LONG))
        self.assertTrue(probe.description_matches(LONG[:90] + '...', LONG))
        self.assertTrue(probe.description_matches(LONG, LONG))
        self.assertFalse(probe.description_matches(LONG[:59], LONG))
        self.assertFalse(probe.description_matches(LONG[:50] + '…', LONG))
        self.assertFalse(probe.description_matches('Different text ' + LONG[15:], LONG))
        short = 'Short skill text'
        self.assertTrue(probe.description_matches(short, short))
        self.assertFalse(probe.description_matches(short[:10], short))

    def test_u19_form_sample(self):
        found = probe.find_skill_entries(FIXS / 'skills-u19-form' / 'record.jsonl', {
            'dir': 'Probe skill in a skills folder. Use when asked to use ma-probe-dir.',
            'root': 'Probe skill at the plugin root. Use when asked to use ma-probe-root.'})
        self.assertEqual([e['name'] for e in probe.distinct_entries(found['dir'])], ['ma-probe:ma-probe-dir'])
        self.assertEqual(found['root'], [])
        self.assertTrue(found['dir'][0]['path'].endswith('/ma-probe/0.0.1/skills/ma-probe-dir/SKILL.md'))
        self.assertTrue(found['dir'][0]['path'].startswith('/Users/x/.codex/plugins/cache/ma-probe/'))
        self.assertEqual(probe.listing_found(FIXS / 'skills-u19-form' / 'record.jsonl'), True)

    def test_marker_only_in_tool_output_or_answer_does_not_count(self):
        desc = 'MA-SKILL-sx-root Probe skill, made-up text, use only when asked to use MA-SKILL-sx-root.'
        line = f'- p:p: {desc} (file: /abs/SKILL.md)'
        objs = [
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': 'nothing here'}]}},
            {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'output': 'cat\n' + line}},
            {'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': line}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': line}]}},
            {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {'type': 'agent_message', 'text': line}}},
            {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': line}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                                  'content': [{'type': 'input_text', 'text': 'Reply with exactly: ok. Do not run any command.\n' + line}]}},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'record.jsonl'
            path.write_text('\n'.join(json.dumps(o) for o in objs) + '\n', encoding='utf-8')
            found = probe.find_skill_entries(path, {'root': desc})
            self.assertEqual(found['root'], [])
            objs.append({'type': 'response_item', 'payload': {'type': 'message', 'role': 'developer',
                                                              'content': [{'type': 'input_text', 'text': line}]}})
            path.write_text('\n'.join(json.dumps(o) for o in objs) + '\n', encoding='utf-8')
            self.assertEqual(len(probe.find_skill_entries(path, {'root': desc})['root']), 1)

    def test_json_escaped_em_dash_counts(self):
        desc = 'Use when a request needs several steps — made-up text for the test, long enough to be matched whole.'
        text = '### Available skills\n- a:b: ' + desc + ' (file: /abs/SKILL.md)\n'
        escaped = json.dumps({'input': [{'text': text}]})
        self.assertIn('\\u2014', escaped)
        with tempfile.TemporaryDirectory() as d:
            for name, content in (('prompt-input.txt', escaped + '\n'),
                                  ('record.jsonl', json.dumps({'type': 'response_item', 'payload': {
                                      'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': text}]}}) + '\n')):
                path = Path(d) / name
                path.write_text(content, encoding='utf-8')
                self.assertEqual(len(probe.find_skill_entries(path, {'x': desc})['x']), 1, name)

    def test_distinct_paths_count_and_same_listing_in_two_items_counts_once(self):
        desc = 'MA-SKILL-sx-sub Probe skill, made-up text, use only when asked to use MA-SKILL-sx-sub.'
        text = ('### Available skills\n- p:s: %s (file: /abs/one/SKILL.md)\n- p:s: %s (file: /abs/two/SKILL.md)\n' % (desc, desc))
        item = {'type': 'response_item', 'payload': {'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': text}]}}
        state = {'type': 'world_state', 'payload': {'state': {'host_skills': {'body': text}}}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'record.jsonl'
            path.write_text(json.dumps(item) + '\n' + json.dumps(state) + '\n', encoding='utf-8')
            found = probe.find_skill_entries(path, {'sub': desc})['sub']
            self.assertEqual(len(probe.distinct_entries(found)), 2)

    def test_undefined_alias_is_unresolved_but_counts_by_description(self):
        desc = 'MA-SKILL-sx-sub Probe skill, made-up text, use only when asked to use MA-SKILL-sx-sub.'
        text = '### Skill roots\n- `r1` = `/Users/x/a`\n### Available skills\n- p:s: %s (file: r7/p/SKILL.md)\n' % desc
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'prompt-input.txt'
            path.write_text(text, encoding='utf-8')
            found = probe.find_skill_entries(path, {'sub': desc})['sub']
            self.assertEqual([e['path'] for e in found], ['unresolved'])


class SkillsSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.n = 0

    def prepare(self, name, cache=()):
        self.n += 1
        src = self.tmp / f'src{self.n}'
        shutil.copytree(FIXS / name, src)
        home = self.tmp / f'home{self.n}'
        shutil.copytree(FIXS / 'skills-codex-home', home)
        if cache:
            kitdir = self.tmp / f'kit{self.n}'
            probe.main(['kit-skills', str(kitdir)])
            for v in cache:
                shutil.copytree(kitdir / 'kit' / 'plugins' / f'ma-probe-{v}',
                                home / 'plugins' / 'cache' / 'ma-probe' / f'ma-probe-{v}' / '0.0.1', symlinks=True)
        return src, home

    def summarize(self, name, cache=()):
        src, home = self.prepare(name, cache)
        out = self.tmp / f'out{self.n}'
        code, printed = run_main(['--codex-home', str(home), 'summary-skills', str(src), '--out', str(out)])
        self.assertEqual(code, 0)
        data = read_json(out / 'probe-skills' / 'summary-skills.json')
        return data, out, printed

    def outcome_of(self, name, cache=()):
        data, out, _ = self.summarize(name, cache)
        self.assertEqual(probe.main(['findings-skills', str(out)]), 0)
        text = (out / 'codex-findings-skills.md').read_text(encoding='utf-8')
        body = text.split('## Outcome')[1].split('\n## ')[0]
        lines = [l for l in body.splitlines() if l.startswith('Outcome:')]
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_each_outcome_line(self):
        cases = [('skills-nohard', (), 'Outcome: open no hard source'),
                 ('skills-notinst', (), 'Outcome: open ma-probe-s3 not installed'),
                 ('skills-live', (), 'Outcome: listed-live'),
                 ('skills-notrepro', (), 'Outcome: not-reproduced'),
                 ('skills-m3', (), 'Outcome: fix manifest "./"'),
                 ('skills-m2', (), 'Outcome: fix manifest absent'),
                 ('skills-f-resolved', ('s5',), 'Outcome: fix folder resolved only'),
                 ('skills-f-link', ('s5',), 'Outcome: fix folder link both'),
                 ('skills-dup', (), 'Outcome: none duplicate skill name'),
                 ('skills-nopath', (), 'Outcome: none path not honored')]
        for name, cache, want in cases:
            self.assertEqual(self.outcome_of(name, cache), want, name)

    def test_cache_missing_entry_gives_symlink_reason(self):
        src, home = self.prepare('skills-f-link', ('s5',))
        link = home / 'plugins' / 'cache' / 'ma-probe' / 'ma-probe-s5' / '0.0.1' / 'codex' / 'skills' / 'ma-probe-s5'
        shutil.rmtree(link)
        out = self.tmp / 'o'
        run_main(['--codex-home', str(home), 'summary-skills', str(src), '--out', str(out)])
        probe.main(['findings-skills', str(out)])
        self.assertIn('Outcome: none symlink not followed',
                      (out / 'codex-findings-skills.md').read_text(encoding='utf-8'))

    def test_live_line_printed(self):
        self.assertEqual(self.summarize('skills-live')[2].strip(), 'live: root listed')
        self.assertEqual(self.summarize('skills-m3')[2].strip(), 'live: root not listed')
        self.assertEqual(self.summarize('skills-nohard')[2].strip(), 'live: no hard source')

    def test_live_facts_and_sources(self):
        data, _, _ = self.summarize('skills-m3')
        live = data['live']
        self.assertFalse(live['root_listed'])
        self.assertTrue(live['monitor_listed'])
        self.assertTrue(data['phases']['live']['sources']['prompt-input']['found'])
        self.assertTrue(data['phases']['live']['sources']['session-record']['found'])
        self.assertTrue(data['phases']['kit']['ran'])
        nohard, _, _ = self.summarize('skills-nohard')
        self.assertFalse(nohard['phases']['live']['sources']['prompt-input']['found'])
        self.assertFalse(nohard['phases']['live']['sources']['session-record']['found'])
        self.assertFalse(nohard['phases']['kit']['ran'])
        self.assertIn('help', data)
        self.assertFalse(data['help']['names_skill_listing_command'])

    def test_variant_facts(self):
        data, _, _ = self.summarize('skills-f-link', ('s5',))
        s5 = data['variants']['s5']
        self.assertTrue(s5['installed'])
        self.assertEqual(s5['skills']['root']['count'], 1)
        self.assertEqual(s5['skills']['sub']['count'], 2)
        self.assertEqual(s5['skills']['root']['entries'][0]['name'], 'ma-probe-s5:ma-probe-s5')
        self.assertEqual(s5['skills']['root']['entries'][0]['path'],
                         '<codex-home>/plugins/cache/ma-probe/ma-probe-s5/0.0.1/codex/skills/ma-probe-s5/SKILL.md')
        cache = s5['cache']
        self.assertEqual(cache['codex/skills/ma-probe-s5/SKILL.md'],
                         {'present': True, 'kind': 'symlink', 'target': '../../../SKILL.md'})
        self.assertEqual(cache['codex/skills/ma-probe-s5-sub']['target'], '../../skills/ma-probe-s5-sub')
        self.assertEqual(cache['SKILL.md']['kind'], 'file')
        self.assertFalse(data['variants']['s0']['cache']['SKILL.md']['present'])
        self.assertEqual(data['listed_path']['root'], 'link')
        self.assertEqual(data['listed_path']['sub'], 'both')

    def test_alias_resolution_tells_resolved_from_link(self):
        data, _, _ = self.summarize('skills-f-resolved', ('s5',))
        entry = data['variants']['s5']['skills']['root']['entries'][0]
        self.assertEqual(entry['path'], '<codex-home>/plugins/cache/ma-probe/ma-probe-s5/0.0.1/SKILL.md')
        self.assertEqual(data['listed_path'], {'root': 'resolved', 'sub': 'only'})

    def test_not_installed_variant(self):
        data, _, _ = self.summarize('skills-notinst')
        self.assertFalse(data['variants']['s3']['installed'])
        self.assertTrue(data['variants']['s0']['installed'])

    def test_unresolved_alias_recorded(self):
        src, home = self.prepare('skills-m3')
        rec = next((src / 'sessions' / 'skills-kit').glob('*.jsonl'))
        rec.write_text(rec.read_text(encoding='utf-8').replace('- `r6` = ', '- `r5` = '), encoding='utf-8')
        out = self.tmp / 'ou'
        run_main(['--codex-home', str(home), 'summary-skills', str(src), '--out', str(out)])
        data = read_json(out / 'probe-skills' / 'summary-skills.json')
        paths = {e['path'] for e in data['variants']['s3']['skills']['sub']['entries']}
        self.assertIn('unresolved', paths)
        self.assertEqual(data['variants']['s3']['skills']['sub']['count'] >= 1, True)

    def test_reduced_captures_hold_only_probe_and_my_agent_entries(self):
        _, out, _ = self.summarize('skills-m3')
        caps = out / 'probe-skills' / 'captures'
        files = sorted(caps.glob('*'))
        self.assertTrue(files)
        self.assertTrue((out / 'probe-skills' / 'run.log').is_file())
        other = ('skill-creator', 'find-skills', 'pdf', 'Skill roots', 'Available skills', 'skills_instructions',
                 'Reply with exactly', 'permissions', 'Global')
        total = 0
        for path in files:
            for line in path.read_text(encoding='utf-8').splitlines():
                total += 1
                self.assertNotRegex(line, r'`r\d+`', path.name)
                self.assertNotRegex(line, r'\br\d+/', path.name)
                self.assertNotIn('/Users/', line)
                for word in other:
                    self.assertNotIn(word, line, path.name)
                if ' (file: ' in line:
                    self.assertRegex(line, r'ma-probe-s\d|my-agent:|MA-SKILL')
                    self.assertTrue('(file: <codex-home>/' in line or '(file: unresolved)' in line, line)
        self.assertGreater(total, 5)
        kit_session = (caps / 'skills-kit-session-record.txt').read_text(encoding='utf-8')
        self.assertIn('my-agent:monitor', kit_session)
        self.assertNotIn('ma-probe-s4:ma-probe-s4-root', kit_session)
        self.assertIn('  - ma-probe-s3:ma-probe-s3: ', kit_session)

    def test_home_path_replaced(self):
        src, home = self.prepare('skills-m3')
        out = self.tmp / 'oo'
        run_main(['--codex-home', '/Users/x/.codex', 'summary-skills', str(src), '--out', str(out)])
        text = '\n'.join(p.read_text(encoding='utf-8') for p in (out / 'probe-skills').rglob('*') if p.is_file())
        self.assertNotIn('/Users/', text)
        self.assertIn('<codex-home>/plugins/cache/ma-probe/', text)

    def test_error_items_name_the_probe_skill(self):
        data, _, _ = self.summarize('skills-dup')
        self.assertTrue(any(e['skill'] == 's5' and e['duplicate'] for e in data['errors']))
        clean, _, _ = self.summarize('skills-m3')
        self.assertEqual(clean['errors'], [])

    def test_help_text_naming_a_listing_command(self):
        src, home = self.prepare('skills-live')
        (src / 'raw' / 'skills-live-help-debug.txt').write_text('Commands:\n  skills       List the skills\n', encoding='utf-8')
        out = self.tmp / 'oh'
        run_main(['--codex-home', str(home), 'summary-skills', str(src), '--out', str(out)])
        self.assertTrue(read_json(out / 'probe-skills' / 'summary-skills.json')['help']['names_skill_listing_command'])


class SkillsFindingsTest(unittest.TestCase):
    SECTIONS = ['Sources', 'Live install', 'Variants', 'Names', 'Listed path', 'Outcome', 'Open']

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        src = self.tmp / 'src'
        shutil.copytree(FIXS / 'skills-f-link', src)
        self.out = self.tmp / 'out'
        kitdir = self.tmp / 'kit'
        probe.main(['kit-skills', str(kitdir)])
        home = self.tmp / 'home'
        shutil.copytree(FIXS / 'skills-codex-home', home)
        shutil.copytree(kitdir / 'kit' / 'plugins' / 'ma-probe-s5', home / 'plugins' / 'cache' / 'ma-probe' / 'ma-probe-s5' / '0.0.1',
                        symlinks=True)
        run_main(['--codex-home', str(home), 'summary-skills', str(src), '--out', str(self.out)])
        self.assertEqual(probe.main(['findings-skills', str(self.out)]), 0)
        self.md = self.out / 'codex-findings-skills.md'
        self.text = self.md.read_text(encoding='utf-8')

    def test_sections_table_and_outcome(self):
        for name in self.SECTIONS:
            self.assertRegex(self.text, rf'(?m)^## {name}$')
        self.assertIn('| Variant | Changes | Root entries | Sub entries | Other skills listed | Listed name | Listed paths | Cache | Evidence |',
                      self.text)
        self.assertIn('| Fact | Capture | Used by unit |', self.text)
        body = self.text.split('## Outcome')[1].split('\n## ')[0]
        self.assertEqual([l for l in body.splitlines() if l.startswith('Outcome:')], ['Outcome: fix folder link both'])
        self.assertIn('probe-skills/captures/', self.text)
        listed = self.text.split('## Listed path')[1].split('\n## ')[0]
        self.assertIn('link', listed)
        self.assertIn('both', listed)
        names = self.text.split('## Names')[1].split('\n## ')[0]
        self.assertIn('ma-probe-s1:ma-probe-s1-named', names)
        self.assertIn('frontmatter', names)

    def test_json_facts(self):
        data = read_json(self.out / 'codex-findings-skills.json')
        facts = {f['fact']: f for f in data['facts']}
        self.assertIn('Plugin skill discovery outcome', facts)
        self.assertIn('Skill listing source', facts)
        for f in data['facts']:
            self.assertIn('fact', f)
            self.assertIn('capture', f)
            self.assertTrue((self.out / f['capture']).is_file(), f['capture'])
        self.assertEqual(data['outcome'], 'Outcome: fix folder link both')

    def test_report_reads_the_json_unchanged(self):
        e2e = FIXS / 'sample-e2e'
        out = self.tmp / 'gap.md'
        code = probe.main(['report', str(e2e), '--findings', str(self.out / 'codex-findings-skills.json'), '--out', str(out)])
        self.assertEqual(code, 0)

    def test_check_findings(self):
        self.assertEqual(probe.main(['check', 'findings', str(self.md)]), 0)
        code, printed = run_main(['check', 'findings', str(self.md)])
        self.assertIn('Outcome: fix folder link both', printed)
        self.assertIn('OK:', printed)
        none = self.out / 'codex-findings-skills-none.md'
        none.write_text(self.text.replace('Outcome: fix', 'nothing: fix'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(none)]), 1)
        two = self.out / 'codex-findings-skills-two.md'
        two.write_text(self.text.replace('Outcome: fix folder link both', 'Outcome: fix folder link both\nOutcome: open x'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(two)]), 1)
        gone = self.out / 'codex-findings-skills-gone.md'
        gone.write_text(self.text + '\n`probe-skills/captures/nope.txt`\n', encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(gone)]), 1)
        nosec = self.out / 'codex-findings-skills-nosec.md'
        nosec.write_text(self.text.replace('## Names', '## Nam'), encoding='utf-8')
        self.assertEqual(probe.main(['check', 'findings', str(nosec)]), 1)

    def test_check_still_handles_identity_kind(self):
        src = self.tmp / 'idsrc'
        shutil.copytree(FIXS / 'sample-identity-i', src)
        out = self.tmp / 'idout'
        probe.main(['summary-identity', str(src), '--out', str(out)])
        probe.main(['findings-identity', str(out)])
        self.assertEqual(probe.main(['check', 'findings', str(out / 'codex-findings-identity.md')]), 0)


class SkillsFixtureHomeTest(unittest.TestCase):
    def test_no_home_path_or_user_name_in_new_files(self):
        user = 'jahoon' + 'jin'
        for path in FIXS.glob('skills-*'):
            for f in path.rglob('*'):
                if f.is_file():
                    text = f.read_text(encoding='utf-8')
                    self.assertNotIn('/Users/' + user, text, str(f))
                    self.assertNotIn(user, text, str(f))
        self.assertNotIn(user, PROBE.read_text(encoding='utf-8'))


# ---- install evidence from the hard source (u28) ----

MONITOR_DESC = 'Start, check, or stop the my-agent monitor web page (local, read-only). Run only when called as /my-agent:monitor.'
ROOT_DESC = 'Use when a request needs several steps from plan to review; made-up root skill description for the install test.'
PI_LISTING = """### Skill roots
- `r1` = `/Users/x/.codex/plugins/cache`
### Available skills
- pdf: A made-up other skill. (file: /abs/pdf/SKILL.md)
- {name}: {desc} (file: r1/my-plugins/my-agent/0.7.0/skills/monitor/SKILL.md)
"""
FAKE_PI = '''#!{py}
import json, os, sys
with open({log!r}, 'a') as f:
    f.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}) + '\\n')
if sys.argv[1:2] == ['--version']:
    print('codex-cli 9.9.9')
elif sys.argv[1:3] == ['debug', 'prompt-input']:
    sys.stdout.write(open({pi!r}).read())
else:
    print('listing ' + ' '.join(sys.argv[1:]))
'''
UNKNOWN_SKILL = 'Unknown skill my-agent'
UNLISTED_SKILL = 'skill my-agent is not listed'
NOT_GIT = 'fatal: not a git repository (or any of the parent directories): .git'
NO_ACTIVE = 'run-log: no active my-agent task under /x/repo'
PATH_MISSING = 'cannot read /x/plugins/cache/my-plugins/my-agent/0.7.0/SKILL.md: No such file or directory'


class SkillsInstallEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / 'codex-home'
        ver = self.home / 'plugins' / 'cache' / 'my-plugins' / 'my-agent' / '0.7.0'
        (ver / 'skills' / 'monitor').mkdir(parents=True)
        (ver / '.codex-plugin').mkdir()
        (ver / 'SKILL.md').write_text(f'---\nname: my-agent\ndescription: {ROOT_DESC}\n---\nbody\n', encoding='utf-8')
        (ver / 'skills' / 'monitor' / 'SKILL.md').write_text(
            f'---\nname: monitor\ndescription: {MONITOR_DESC}\n---\nbody\n', encoding='utf-8')
        self.repo = self.tmp / 'repo'
        self.repo.mkdir()

    def snapshot(self, pi_text, name='snap'):
        pi = self.tmp / f'{name}-pi.txt'
        pi.write_text(pi_text, encoding='utf-8')
        log = self.tmp / f'{name}-calls.jsonl'
        fake = self.tmp / f'{name}-fake'
        fake.write_text(FAKE_PI.format(py=sys.executable, log=str(log), pi=str(pi)), encoding='utf-8')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        out = self.tmp / name
        code = probe.main(['--codex', str(fake), '--codex-home', str(self.home), 'snapshot', '--out', str(out),
                           '--skills', str(self.repo), '--cache', 'my-plugins/my-agent'])
        self.assertEqual(code, 0)
        return out, log

    def read(self, out, name):
        return (out / name).read_text(encoding='utf-8')

    def test_monitor_entry_writes_name_and_prompt_input(self):
        out, _ = self.snapshot(PI_LISTING.format(name='my-agent:monitor', desc=MONITOR_DESC))
        self.assertEqual(self.read(out, 'skills-list.txt').split(), ['my-agent:monitor'])
        self.assertEqual(self.read(out, 'skills-source.txt').strip(), 'prompt-input')
        evidence = self.read(out, 'skills-evidence.txt')
        self.assertIn('my-agent:monitor', evidence)
        self.assertIn('<codex-home>/plugins/cache/my-plugins/my-agent/0.7.0/skills/monitor/SKILL.md', evidence)
        self.assertNotIn('pdf', evidence)
        self.assertNotIn('`r1`', evidence)
        self.assertNotIn('/Users/', evidence)

    def test_description_outside_a_listing_entry_does_not_count(self):
        plain = (f'### Skill roots\nNote: {MONITOR_DESC}\n### Available skills\n'
                 '- pdf: A made-up other skill. (file: /abs/pdf/SKILL.md)\n')
        out, _ = self.snapshot(plain)
        self.assertEqual(self.read(out, 'skills-list.txt').split(), [])
        self.assertEqual(self.read(out, 'skills-source.txt').strip(), 'prompt-input')
        out, _ = self.snapshot(f'Plain prompt text. {MONITOR_DESC}\n', 'snap2')
        self.assertEqual(self.read(out, 'skills-list.txt').split(), [])
        self.assertEqual(self.read(out, 'skills-source.txt').strip(), 'none')

    def test_no_listing_entry_is_none(self):
        out, _ = self.snapshot('nothing listed here\n')
        self.assertEqual(self.read(out, 'skills-source.txt').strip(), 'none')
        self.assertEqual(self.read(out, 'skills-list.txt').split(), [])

    def test_prompt_input_not_exec_and_no_extra_files(self):
        out, log = self.snapshot(PI_LISTING.format(name='my-agent:monitor', desc=MONITOR_DESC))
        made = calls(log)
        argvs = [c['argv'] for c in made]
        self.assertEqual(argvs[:3], [['--version'], ['plugin', 'list'], ['plugin', 'marketplace', 'list']])
        debug = [c for c in made if c['argv'][:2] == ['debug', 'prompt-input']]
        self.assertEqual(len(debug), 1)
        self.assertEqual(os.path.realpath(debug[0]['cwd']), os.path.realpath(self.repo))
        for argv in argvs:
            self.assertNotEqual(argv[:1], ['exec'])
            self.assertFalse(set(argv) & {'add', 'remove', 'upgrade'}, argv)
        files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
        self.assertEqual(files, ['cache-files.txt', 'codex-version.txt', 'marketplace-list.txt', 'plugin-list.txt',
                                 'skills-evidence.txt', 'skills-list.txt', 'skills-source.txt'])
        for f in files:
            self.assertNotIn('Available skills', self.read(out, f))

    def test_evidence_is_reduced(self):
        out, _ = self.snapshot(PI_LISTING.format(name='my-agent:monitor', desc=MONITOR_DESC))
        for f in ('skills-evidence.txt', 'skills-list.txt', 'skills-source.txt'):
            text = self.read(out, f)
            self.assertNotIn('/Users/', text)
            self.assertNotIn(str(self.home), text)
            self.assertNotRegex(text, r'`r\d+`')

    # check install

    def helper(self):
        t = E2eToolingTest('test_check_install')
        t.tmp = self.tmp
        return t

    def check(self, **kw):
        t = self.helper()
        root = t.repo_root()
        folder = t.install_folder(root=str(root), **kw)
        return run_main(['check', 'install', str(folder), '--root', str(root)])

    GAP = ('expected gap: my-agent:my-agent not listed (Codex lists no plugin-root SKILL.md; '
           'capability plugin-skill-discovery)')

    def test_check_install_passes_with_monitor_and_prints_gap(self):
        for source in ('prompt-input', 'session-record'):
            code, out = self.check(source=source)
            self.assertEqual(code, 0, out)
            self.assertEqual([l for l in out.splitlines() if l.startswith('expected gap')], [self.GAP])

    def test_check_install_fails(self):
        for kw, text in (({'source': None}, 'skills evidence is not from a hard source'),
                         ({'source': 'none'}, 'skills evidence is not from a hard source'),
                         ({'source': 'model-answer'}, 'skills evidence is not from a hard source'),
                         ({'skills': 'my-agent\nmonitor\n'}, 'my-agent:monitor'),
                         ({'skills': 'other:monitor\n'}, 'my-agent:monitor'),
                         ({'skills': 'my-agent:monitor\nmy-agent:monitor\n'}, '2'),
                         ({'skills': 'my-agent:monitor\nmy-agent:my-agent\n'},
                          'my-agent:my-agent is listed, which contradicts work/codex-findings-skills.md')):
            code, out = self.check(**kw)
            self.assertEqual(code, 1, (kw, out))
            self.assertIn(text, out, kw)
        code, out = self.check(skills='my-agent:monitor\nmy-agent:my-agent\n')
        self.assertNotIn('expected gap', out)

    def test_check_install_missing_skills_list_fails(self):
        t = self.helper()
        root = t.repo_root()
        folder = t.install_folder(root=str(root))
        (folder / 'skills-list.txt').unlink()
        self.assertEqual(run_main(['check', 'install', str(folder), '--root', str(root)])[0], 1)

    # e2e-request

    def request_folder(self, files='0.7.0/SKILL.md\n0.7.0/skills/monitor/SKILL.md', skill=True):
        folder = self.tmp / 'install'
        folder.mkdir(exist_ok=True)
        (folder / 'plugin-list.txt').write_text(LIST_FORM.format(root='/x/repo', status='installed, enabled', version='0.7.0'),
                                                encoding='utf-8')
        (folder / 'cache-files.txt').write_text(files, encoding='utf-8')
        target = self.home / 'plugins' / 'cache' / 'my-plugins' / 'my-agent' / '0.7.0' / 'SKILL.md'
        if skill:
            target.write_text('x', encoding='utf-8')
        elif target.exists():
            target.unlink()
        return folder

    def test_e2e_request_prints_one_line(self):
        folder = self.request_folder()
        before = sorted(self.tmp.rglob('*'))
        code, out = run_main(['--codex-home', str(self.home), 'e2e-request', str(folder)])
        self.assertEqual(code, 0)
        path = f'{self.home}/plugins/cache/my-plugins/my-agent/0.7.0/SKILL.md'
        self.assertEqual(out, f'Read the file {path} and follow it as your instructions, with these arguments: '
                              '--dev add a function add(a, b) in calc.py that returns the sum of two numbers, with a test\n')
        self.assertNotIn('$my-agent', out)
        self.assertEqual(sorted(self.tmp.rglob('*')), before)

    def test_e2e_request_fails_naming_the_gap(self):
        from contextlib import redirect_stderr
        for kw, text in (({'files': '0.7.0/skills/monitor/SKILL.md'}, '0.7.0/SKILL.md'),
                         ({'skill': False}, 'SKILL.md')):
            folder = self.request_folder(**kw)
            err = io.StringIO()
            with redirect_stderr(err):
                code, out = run_main(['--codex-home', str(self.home), 'e2e-request', str(folder)])
            self.assertEqual(code, 1)
            self.assertEqual(out, '')
            self.assertIn(text, err.getvalue())
            self.request_folder()   # restore

    def test_e2e_request_without_my_agent_row_fails(self):
        folder = self.request_folder()
        (folder / 'plugin-list.txt').write_text('nothing\n', encoding='utf-8')
        self.assertEqual(run_main(['--codex-home', str(self.home), 'e2e-request', str(folder)])[0], 1)

    # capabilities row and report

    def test_plugin_skill_discovery_row(self):
        rows = {r['id']: r for r in json.loads(CAPS.read_text(encoding='utf-8'))['rows']}
        row = rows['plugin-skill-discovery']
        self.assertEqual(row['status'], 'gap')
        self.assertEqual(row['facts'], ['Plugin skill discovery outcome', 'Skill listing source'])
        self.assertEqual(row['needed_by'], ['plugins/my-agent/.codex-plugin/plugin.json', 'plugins/my-agent/SKILL.md'])
        self.assertEqual(rows['skill-path-variables']['effect'],
                         'the plugin and skill folders are the folder of the SKILL.md file Codex read (hosts.md)')
        written = set(re.findall(r"add\('[\w ]+', '([^']+)'", PROBE.read_text(encoding='utf-8')))
        for fact in row['facts']:
            self.assertIn(fact, written)
        others = [p for r in rows.values() if r is not row for p in r['failure_patterns']]
        for text in (UNKNOWN_SKILL, UNLISTED_SKILL, PATH_MISSING):
            self.assertTrue(any(re.search(p, text, re.I) for p in row['failure_patterns']), text)
            self.assertFalse(any(re.search(p, text, re.I) for p in others), text)

    def test_unlisted_intake_failures_have_rows(self):
        rows = {r['id']: r for r in json.loads(CAPS.read_text(encoding='utf-8'))['rows']}
        for rid, text, needed in (
                ('plugin-rules-version', NOT_GIT, ['plugins/my-agent/SKILL.md']),
                ('intake-order', NO_ACTIVE, ['plugins/my-agent/SKILL.md', 'plugins/my-agent/l4-tools-guards/scripts/run-log.py'])):
            row = rows[rid]
            self.assertEqual(row['status'], 'gap')
            self.assertEqual(row['needed_by'], needed)
            others = [p for r in rows.values() if r is not row for p in r['failure_patterns']]
            self.assertTrue(any(re.search(p, text, re.I) for p in row['failure_patterns']), text)
            self.assertFalse(any(re.search(p, text, re.I) for p in others), text)
        self.assertFalse(any(re.search(p, 'ordinary text', re.I)
                             for rid in ('plugin-rules-version', 'intake-order') for p in rows[rid]['failure_patterns']))

    def test_report_with_skills_findings_and_check_report(self):
        e2e = self.tmp / 'e2e-out'
        self.assertEqual(probe.main(['--codex-home', str(E2E / 'codex-home'), 'e2e-collect', str(E2E), '--out', str(e2e)]), 0)
        report = self.tmp / 'report.md'
        self.assertEqual(probe.main(['report', str(e2e), '--findings', str(E2E_PROBE / 'findings.json'),
                                     '--findings', str(E2E_PROBE / 'findings-identity.json'),
                                     '--findings', str(E2E_PROBE / 'findings-skills.json'), '--out', str(report)]), 0)
        text = report.read_text(encoding='utf-8')
        row = next(l for l in text.splitlines() if l.startswith('|') and 'Plugin skill discovery' in l)
        self.assertRegex(row, r'probe-skills/captures/skills-live-prompt-input\.txt line \d+')
        root = self.tmp / 'proot'
        shutil.copytree(E2E_PROBE, root)
        self.assertEqual(run_main(['check', 'report', str(report), '--e2e', str(e2e), '--probe-root', str(root)])[0], 0)
        (root / 'probe-skills' / 'captures' / 'skills-live-prompt-input.txt').unlink()
        code, out = run_main(['check', 'report', str(report), '--e2e', str(e2e), '--probe-root', str(root)])
        self.assertEqual(code, 1)
        self.assertIn('probe-skills/captures/skills-live-prompt-input.txt', out)

    def test_no_home_path_in_fixtures(self):
        user = 'jahoon' + 'jin'
        for f in FIXS.rglob('*'):
            if f.is_file():
                self.assertNotIn(user, f.read_text(encoding='utf-8', errors='replace'), str(f))
        self.assertNotIn(user, CAPS.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

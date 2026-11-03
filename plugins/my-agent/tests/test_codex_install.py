"""build-codex.py --install-agents / --check-agents: the nine agent files in `<codex home>/agents/` (task 261103, u3).

Every case uses a temp plugin root and a temp Codex home; the real ~/.codex is never read or written.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO
from test_codex_build import copy_tree

SCRIPT = REPO / 'l4-tools-guards' / 'scripts' / 'build-codex.py'
VERSION = '0.10.0'
PERSON = {'my-code-reviewer.toml': b'person one\n', 'my-explorer.toml': b'person two \xff\n',
          'my-plan-reviewer.toml': b'person three\n', 'my-verifier.toml': b'person four\n'}


def comment(version):
    return f'# my-agent {version} (build-codex.py --install-agents)\n'


class InstallBase(unittest.TestCase):
    def setUp(self):
        self.root = copy_tree()
        self.tmp = Path(tempfile.mkdtemp())
        manifest = self.root / '.claude-plugin' / 'plugin.json'
        data = json.loads(manifest.read_text())
        data['version'] = VERSION
        manifest.write_text(json.dumps(data, indent=2) + '\n')
        self.home = self.tmp / 'codex-home'
        self.agents = self.home / 'agents'
        self.agents.mkdir(parents=True)
        for name, data in PERSON.items():
            (self.agents / name).write_bytes(data)
        self.person_stat = {n: (self.agents / n).stat().st_mtime_ns for n in PERSON}
        self.names = sorted(p.name for p in (self.root / 'codex' / 'agents').glob('*.toml'))
        order = json.loads(manifest.read_text())['agents']
        self.order = []
        for ref in order:
            role = Path(ref).stem
            self.order.append(f'my-agent-{role}.toml')
        self.assertEqual(sorted(self.order), self.names)

    def tearDown(self):
        shutil.rmtree(self.root)
        shutil.rmtree(self.tmp)

    def run_mode(self, mode, home=None, env_home=None):
        env = {k: v for k, v in os.environ.items() if k != 'CODEX_HOME'}
        env['HOME'] = str(self.tmp / 'fake-user-home')
        cmd = [sys.executable, str(SCRIPT), mode, '--root', str(self.root)]
        if env_home is not None:
            env['CODEX_HOME'] = str(env_home)
        else:
            cmd += ['--codex-home', str(home if home is not None else self.home)]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return r, r.stdout.splitlines()

    def generated(self, name):
        return (self.root / 'codex' / 'agents' / name).read_text()

    def put(self, name, version=VERSION, body=None):
        text = self.generated(name) if body is None else body
        (self.agents / name).write_text(comment(version) + text)

    def listing(self, folder):
        return sorted((p.name, p.stat().st_mtime_ns) for p in folder.iterdir())

    def assert_person_intact(self):
        for name, data in PERSON.items():
            self.assertEqual((self.agents / name).read_bytes(), data)
            self.assertEqual((self.agents / name).stat().st_mtime_ns, self.person_stat[name])


class InstallAgents(InstallBase):
    def test_fresh_install(self):
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out[:-1], [f'installed: {n}' for n in self.order])
        self.assertEqual(out[-1], f'Codex agents: installed 9 ({VERSION})')
        for n in self.names:
            text = (self.agents / n).read_text()
            line1, rest = text.split('\n', 1)
            self.assertEqual(line1 + '\n', comment(VERSION))
            self.assertEqual(rest, self.generated(n))
        self.assert_person_intact()
        self.assertEqual(sorted(p.name for p in self.agents.iterdir()), sorted(self.names + list(PERSON)))
        self.assertEqual([p.name for p in self.home.iterdir()], ['agents'])

    def test_generated_files_stay_comment_free(self):
        self.run_mode('--install-agents')
        for n in self.names:
            self.assertFalse(self.generated(n).startswith('#'))

    def test_rerun_is_up_to_date(self):
        self.run_mode('--install-agents')
        before = self.listing(self.agents)
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out[:-1], [f'up to date: {n}' for n in self.order])
        self.assertEqual(out[-1], f'Codex agents: installed 9 ({VERSION})')
        self.assertEqual(self.listing(self.agents), before)
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out[-1], f'Codex agents: installed 9 ({VERSION})')

    def test_stale_version_checked_then_rewritten(self):
        self.run_mode('--install-agents')
        target = self.order[0]
        self.put(target, version='0.9.0')
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'stale: {target} (0.9.0)', out)
        self.assertEqual(out[-1], 'Codex agents: stale (0.9.0)')
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 0)
        self.assertIn(f'installed: {target} (was 0.9.0)', out)
        self.assertEqual((self.agents / target).read_text(), comment(VERSION) + self.generated(target))
        self.assert_person_intact()

    def test_same_version_changed_body(self):
        self.run_mode('--install-agents')
        target = self.order[2]
        self.put(target, body='edited\n')
        r, out = self.run_mode('--check-agents')
        self.assertIn(f'stale: {target} (changed)', out)
        self.assertEqual(out[-1], 'Codex agents: stale (changed)')
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.agents / target).read_text(), comment(VERSION) + self.generated(target))

    def test_file_without_comment_is_skipped(self):
        target = self.order[0]
        (self.agents / target).write_bytes(b'mine\n')
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'skipped: not generated by my-agent: {target}', out)
        self.assertEqual((self.agents / target).read_bytes(), b'mine\n')
        self.assertEqual(out[-1], f'Codex agents: 8 of 9 installed ({VERSION}); 1 skipped')
        self.assert_person_intact()

    def test_symlink_target_is_skipped(self):
        target = self.order[1]
        real = self.tmp / 'elsewhere.toml'
        real.write_text('linked\n')
        (self.agents / target).symlink_to(real)
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'skipped: not generated by my-agent: {target}', out)
        self.assertTrue((self.agents / target).is_symlink())
        self.assertEqual(real.read_text(), 'linked\n')

    def test_folder_target_is_skipped(self):
        target = self.order[1]
        (self.agents / target).mkdir()
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'skipped: not generated by my-agent: {target}', out)
        self.assertTrue((self.agents / target).is_dir())

    def test_missing_home(self):
        home = self.tmp / 'no-such-home'
        for mode in ('--install-agents', '--check-agents'):
            r, out = self.run_mode(mode, home=home)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(out, [f'build-codex: no Codex home at {home}; nothing installed',
                                   f'Codex agents: no Codex home ({home})'])
            self.assertFalse(home.exists())

    def test_home_without_agents_folder(self):
        home = self.tmp / 'bare-home'
        home.mkdir()
        (home / 'config.toml').write_text('x = 1\n')
        before = self.listing(home)
        r, out = self.run_mode('--check-agents', home=home)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[:-1], [f'missing: {n}' for n in self.order])
        self.assertEqual(out[-1], 'Codex agents: not installed')
        self.assertEqual(self.listing(home), before)
        r, out = self.run_mode('--install-agents', home=home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out[-1], f'Codex agents: installed 9 ({VERSION})')
        self.assertEqual(sorted(p.name for p in home.iterdir()), ['agents', 'config.toml'])
        self.assertEqual(sorted(p.name for p in (home / 'agents').iterdir()), self.names)

    def test_agents_is_a_regular_file(self):
        home = self.tmp / 'file-home'
        home.mkdir()
        (home / 'agents').write_bytes(b'not a folder\n')
        before = self.listing(home)
        for mode in ('--install-agents', '--check-agents'):
            r, out = self.run_mode(mode, home=home)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(out, [f'build-codex: {home}/agents is not a folder; nothing installed',
                                   'Codex agents: not installed'])
            self.assertEqual((home / 'agents').read_bytes(), b'not a folder\n')
            self.assertEqual(self.listing(home), before)

    def test_agents_is_a_link_to_a_file(self):
        home = self.tmp / 'link-file-home'
        home.mkdir()
        real = self.tmp / 'plain-file'
        real.write_bytes(b'plain\n')
        (home / 'agents').symlink_to(real)
        r, out = self.run_mode('--install-agents', home=home)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[-1], 'Codex agents: not installed')
        self.assertEqual(real.read_bytes(), b'plain\n')

    def test_agents_is_a_link_to_a_folder(self):
        home = self.tmp / 'link-home'
        home.mkdir()
        elsewhere = self.tmp / 'elsewhere-agents'
        elsewhere.mkdir()
        (home / 'agents').symlink_to(elsewhere)
        r, out = self.run_mode('--install-agents', home=home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((home / 'agents').is_symlink())
        self.assertEqual(sorted(p.name for p in elsewhere.iterdir()), self.names)

    def test_check_writes_nothing(self):
        self.run_mode('--install-agents')
        self.put(self.order[0], version='0.9.0')
        (self.agents / self.order[1]).unlink()
        before = self.listing(self.agents)
        home_before = self.listing(self.home)
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'missing: {self.order[1]}', out)
        self.assertEqual(self.listing(self.agents), before)
        self.assertEqual(self.listing(self.home), home_before)

    def test_codex_home_env_is_the_default(self):
        r, out = self.run_mode('--install-agents', env_home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.agents / self.order[0]).is_file())
        r, out = self.run_mode('--check-agents', env_home=self.home)
        self.assertEqual(out[-1], f'Codex agents: installed 9 ({VERSION})')
        self.assertFalse((self.tmp / 'fake-user-home' / '.codex').exists())

    def test_stale_generated_file_writes_nothing(self):
        stale = self.root / 'codex' / 'agents' / self.order[0]
        stale.write_text(stale.read_text() + '# drift\n')
        before = self.listing(self.agents)
        for mode in ('--install-agents', '--check-agents'):
            r, out = self.run_mode(mode)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(out, ['build-codex: generated files differ; run --write first'])
            self.assertEqual(self.listing(self.agents), before)
        (self.root / 'codex' / 'agents' / self.order[0]).unlink()
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.listing(self.agents), before)


class SummaryRules(InstallBase):
    def test_rule3_check_and_install(self):
        o = self.order
        for n in o[:6]:
            self.put(n)
        (self.agents / o[0]).write_bytes(b'mine\n')   # skipped
        self.put(o[1], version='0.9.0')               # stale
        # o[6:] missing: 6 of 9 up to date after the run? check mode counts o[2:6] = 4 ok + ... see below
        for n in o[7:]:
            self.put(n)                                # o[6] missing, o[7:] ok
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[-1], f'Codex agents: 6 of 9 installed ({VERSION}); 1 skipped')
        r, out = self.run_mode('--install-agents')
        self.assertEqual(r.returncode, 1)
        self.assertIn(f'installed: {o[1]} (was 0.9.0)', out)
        self.assertIn(f'installed: {o[6]}', out)
        self.assertEqual(out[-1], f'Codex agents: 8 of 9 installed ({VERSION}); 1 skipped')
        self.assertEqual((self.agents / o[0]).read_bytes(), b'mine\n')

    def test_rule4_stale_list_in_plugin_order(self):
        o = self.order
        for n in o[:8]:
            self.put(n)
        self.put(o[0], version='0.9.0')
        self.put(o[1], body='edited\n')
        self.put(o[2], version='0.9.0')
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[-1], 'Codex agents: stale (0.9.0, changed)')

    def test_rule7_partial(self):
        for n in self.order[:5]:
            self.put(n)
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[-1], f'Codex agents: 5 of 9 installed ({VERSION})')

    def test_rule6_none_present(self):
        r, out = self.run_mode('--check-agents')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out[-1], 'Codex agents: not installed')
        self.assertEqual(len([l for l in out if l.startswith('missing:')]), 9)


if __name__ == '__main__':
    unittest.main()

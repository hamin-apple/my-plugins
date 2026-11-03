"""plugin.json and both READMEs agree on the my-agent and my-agent-tray versions and on the data folder setting."""
import json
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / 'plugins' / 'my-agent' / '.claude-plugin' / 'plugin.json'
TRAY_MANIFEST = REPO / 'plugins' / 'my-agent-tray' / '.claude-plugin' / 'plugin.json'
READMES = [REPO / 'README.md', REPO / 'README-ko.md']


def install_section(text: str) -> str:
    start = re.search(r'^## (Install|설치)\s*$', text, re.M)
    end = re.search(r'^## ', text[start.end():], re.M)
    return text[start.end():start.end() + end.start()]


def manifest_versions(plugin_dir: Path) -> dict:
    """Map each manifest a plugin folder ships (Claude always, Codex when present) to its version."""
    found = {}
    for sub in ('.claude-plugin', '.codex-plugin'):
        path = plugin_dir / sub / 'plugin.json'
        if path.is_file():
            found[str(path.relative_to(plugin_dir))] = json.loads(path.read_text(encoding='utf-8'))['version']
    return found


def version_mismatches(plugin_dir: Path, row_version: str) -> list:
    return ['%s: %s != %s' % (name, v, row_version) for name, v in manifest_versions(plugin_dir).items() if v != row_version]


def readme_row_version(path: Path, plugin: str) -> str:
    row = re.search(r'^\| `%s` \| ([^ |]+) \|' % re.escape(plugin), path.read_text(encoding='utf-8'), re.M)
    assert row, '%s: no %s row' % (path.name, plugin)
    return row.group(1)


class ManifestVersionTest(unittest.TestCase):
    def make(self, claude, codex=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for sub, v in (('.claude-plugin', claude), ('.codex-plugin', codex)):
            if v is not None:
                (root / sub).mkdir()
                (root / sub / 'plugin.json').write_text(json.dumps({'version': v}), encoding='utf-8')
        return root

    def test_only_claude_manifest(self):
        self.assertEqual(manifest_versions(self.make('1.0.0')), {'.claude-plugin/plugin.json': '1.0.0'})

    def test_codex_mismatch_names_the_file(self):
        out = version_mismatches(self.make('1.0.0', '0.9.0'), '1.0.0')
        self.assertEqual(len(out), 1)
        self.assertIn('.codex-plugin/plugin.json', out[0])

    def test_matching_codex_passes(self):
        self.assertEqual(version_mismatches(self.make('1.0.0', '1.0.0'), '1.0.0'), [])

    def test_repo_plugins_match_readme_rows(self):
        for plugin in ('my-agent', 'my-agent-tray'):
            for readme in READMES:
                self.assertEqual(version_mismatches(REPO / 'plugins' / plugin, readme_row_version(readme, plugin)), [],
                                 '%s %s' % (plugin, readme.name))


class ReadmeVersionTest(unittest.TestCase):
    def test_three_versions_match(self):
        version = json.loads(MANIFEST.read_text(encoding='utf-8'))['version']
        for path in READMES:
            row = re.search(r'^\| `my-agent` \| ([^ |]+) \|', path.read_text(encoding='utf-8'), re.M)
            self.assertIsNotNone(row, path.name)
            self.assertEqual(row.group(1), version, path.name)

    def test_tray_versions_match(self):
        version = json.loads(TRAY_MANIFEST.read_text(encoding='utf-8'))['version']
        for path in READMES:
            row = re.search(r'^\| `my-agent-tray` \| ([^ |]+) \|', path.read_text(encoding='utf-8'), re.M)
            self.assertIsNotNone(row, path.name)
            self.assertEqual(row.group(1), version, path.name)

    def test_install_section_explains_the_data_folder(self):
        for path in READMES:
            section = install_section(path.read_text(encoding='utf-8'))
            self.assertIn('~/dev/log/my-agent', section, path.name)
            self.assertIn('/config', section, path.name)

    def test_archive_tasks_lines_pass_data_dir(self):
        for path in READMES:
            lines = [l for l in path.read_text(encoding='utf-8').splitlines() if 'archive-tasks.py' in l]
            self.assertTrue(lines, path.name)
            for line in lines:
                self.assertIn('--data-dir', line, path.name)

    def test_readmes_name_the_task_folder_setting(self):
        for path in READMES:
            text = path.read_text(encoding='utf-8')
            for token in ('task_dir', '.my-agent', 'docs/agent'):
                self.assertIn(token, text, '%s: %s' % (path.name, token))


if __name__ == '__main__':
    unittest.main()

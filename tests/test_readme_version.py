"""plugin.json and both READMEs agree on the my-agent version and on the data folder setting."""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / 'plugins' / 'my-agent' / '.claude-plugin' / 'plugin.json'
READMES = [REPO / 'README.md', REPO / 'README-ko.md']


def install_section(text: str) -> str:
    start = re.search(r'^## (Install|설치)\s*$', text, re.M)
    end = re.search(r'^## ', text[start.end():], re.M)
    return text[start.end():start.end() + end.start()]


class ReadmeVersionTest(unittest.TestCase):
    def test_three_versions_match(self):
        version = json.loads(MANIFEST.read_text(encoding='utf-8'))['version']
        for path in READMES:
            row = re.search(r'^\| `my-agent` \| ([^ |]+) \|', path.read_text(encoding='utf-8'), re.M)
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


if __name__ == '__main__':
    unittest.main()

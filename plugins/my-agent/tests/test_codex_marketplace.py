"""The Codex marketplace file lists only my-agent, resolves to the Codex manifest, and leaves the Claude marketplace as it was."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class CodexMarketplaceTest(unittest.TestCase):
    def setUp(self):
        self.mp = json.loads((ROOT / '.agents' / 'plugins' / 'marketplace.json').read_text())

    def test_shape(self):
        self.assertEqual(self.mp['name'], 'my-plugins')
        self.assertTrue(self.mp['interface']['displayName'])
        self.assertEqual([p['name'] for p in self.mp['plugins']], ['my-agent'])
        p = self.mp['plugins'][0]
        self.assertEqual(p['source'], {'source': 'local', 'path': './plugins/my-agent'})
        self.assertEqual(set(p['policy']), {'installation', 'authentication'})
        self.assertTrue(p['category'])

    def test_path_resolves_to_codex_manifest(self):
        folder = ROOT / self.mp['plugins'][0]['source']['path']
        codex = json.loads((folder / '.codex-plugin' / 'plugin.json').read_text())
        claude = json.loads((folder / '.claude-plugin' / 'plugin.json').read_text())
        self.assertEqual(codex['name'], 'my-agent')
        self.assertEqual(codex['version'], claude['version'])

    def test_claude_marketplace_lists_both(self):
        cm = json.loads((ROOT / '.claude-plugin' / 'marketplace.json').read_text())
        self.assertEqual([p['name'] for p in cm['plugins']], ['my-agent', 'my-agent-tray'])
        self.assertEqual(cm['plugins'][0]['source'], './plugins/my-agent')


if __name__ == '__main__':
    unittest.main()

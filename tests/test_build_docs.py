"""tools/build-docs.py: the GitHub Pages architecture page (docs/architecture.html) matches the plugin files."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'tools' / 'build-docs.py'
spec = importlib.util.spec_from_file_location('build_docs', SCRIPT)
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)


def page_data(page: str) -> dict:
    raw = page.split('const D = ', 1)[1].split(';\nconst $', 1)[0]
    return json.loads(raw.replace('<\\/', '</'))


class BuildDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = bd.build()
        cls.data = page_data(cls.page)

    def test_committed_page_is_current(self):
        r = subprocess.run([sys.executable, str(SCRIPT), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_output_is_architecture_page(self):
        self.assertEqual(bd.OUT, bd.REPO / 'docs' / 'architecture.html')
        r = subprocess.run([sys.executable, str(SCRIPT), '--check'], capture_output=True, text=True)
        self.assertIn('docs/architecture.html', r.stdout)

    def test_pre_commit_hook_names_architecture_page(self):
        hook = (REPO / '.githooks' / 'pre-commit').read_text(encoding='utf-8')
        self.assertIn('docs/architecture.html', hook)
        self.assertNotIn('docs/index.html', hook)

    def test_every_manifest_agent_is_on_the_page(self):
        manifest = json.loads((bd.PLUGIN / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        names = {Path(p).stem for p in manifest['agents']}
        self.assertEqual({a['id'] for a in self.data['agents']}, names)
        on_levels = {c['id'] for l in self.data['levels'] for c in l['comps']}
        self.assertLessEqual(names, on_levels)

    def test_artifact_list_matches_the_file_layout(self):
        tree = {name for name, _ in bd.tree_files(bd.read(bd.ARCH))}
        self.assertEqual({a[0] for a in bd.ARTIFACTS}, tree)

    def test_four_levels_eight_steps_five_gates(self):
        self.assertEqual([l['id'] for l in self.data['levels']], ['L1', 'L2', 'L3', 'L4'])
        self.assertEqual([s['n'] for s in self.data['steps']], list('12345678'))
        self.assertEqual([g['id'] for g in self.data['gates']], ['G1a', 'G1b', 'G2', 'G3', 'E'])

    def test_scope_comes_from_scope_guard(self):
        coder = next(a for a in self.data['agents'] if a['id'] == 'coder')
        self.assertTrue(coder['scope']['bashWrites'])
        self.assertIn('<task location>/docs/agent', coder['scope']['denyWrite'])
        gate = next(a for a in self.data['agents'] if a['id'] == 'gate-analyst')
        self.assertEqual(gate['scope']['write'], ['<task folder>/gate-report.md'])

    def test_missing_heading_stops_the_build(self):
        with self.assertRaises(bd.SourceError):
            bd.cut('# a\n## b\ntext\n', 'no such heading')

    def test_cut_skips_headings_inside_fences(self):
        text = '## Format\n```text\n# Title\n## Summary\n```\nafter\n## Next\n'
        self.assertIn('after', bd.cut(text, 'Format'))

    def test_markdown_subset(self):
        out = bd.md('| A | B |\n|---|---|\n| `x \\| y` | **b** |\n\n- one\n  - two\n\n```text\n<tag>\n```')
        self.assertIn('<code>x | y</code>', out)
        self.assertIn('<strong>b</strong>', out)
        self.assertIn('<ul><li>one<ul><li>two</li></ul></li></ul>', out)
        self.assertIn('&lt;tag&gt;', out)

    def test_page_has_no_script_breakout(self):
        payload = self.page.split('const D = ', 1)[1].split(';\nconst $', 1)[0]
        self.assertNotIn('</script', payload)


if __name__ == '__main__':
    unittest.main()

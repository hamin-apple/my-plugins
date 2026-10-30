"""The page shows USD only: no token counts, Tokens tile or Tokens column (task 261031-token-display-usd)."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / 'web' / 'index.html'
KO_ESTIMATE = '\ucd94\uc815'
KO_LIST_PRICE = '\uc815\uac00 \ucd94\uc815'
KO_CUMULATIVE = '\uc774 \uc2dc\uc810\uae4c\uc9c0 \ub204\uc801'
KO_TOKEN = '\ud1a0\ud070'


class WebCostTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_no_token_text(self):
        self.assertIsNone(re.search(r'(?i)token', self.html))
        self.assertNotIn(KO_TOKEN, self.html)

    def test_no_token_fields(self):
        for s in ('e.tok', 'x.tok', '.tok +=', 'tokSoFar', 't.tokens', 'maxTok', 'r.tok', 'sd.tok',
                  "cu('tok-'", "cu('mt-'", "=== 'k'"):
            self.assertNotIn(s, self.html, s)

    def test_kpi_tiles(self):
        body = self.html[self.html.index('function renderStatus'):]
        labels = re.findall(r'<div class="kl">(.*?)</div>', body)
        self.assertEqual(labels[:5], ['Now', 'Elapsed', 'Criteria', 'Escalation (E)', 'Cost'])
        cost = body[body.index('<div class="kl">Cost</div>'):]
        cost = cost[:cost.index('</div></div>') + 12]
        self.assertIn(f"L('estimate', '{KO_ESTIMATE}')", cost)
        self.assertIn('statusline', cost)

    def test_models_table(self):
        for s in ('<th>Model</th><th class="n">Calls</th><th class="n">Time</th><th class="n">Cost</th></tr>',
                  'b[1].cost - a[1].cost', 'bar(r.cost, maxCost)', "cu('mc-' + t.id, tot[1], '$')",
                  f"L('list price, estimate', '{KO_LIST_PRICE}')",
                  'done: mv.length', 'priced: mv.filter(c => c != null).length'):
            self.assertIn(s, self.html, s)

    def test_unpriced_row_and_bar(self):
        self.assertIn('r.done && !r.priced', self.html)
        line = next(x for x in self.html.splitlines() if x.lstrip().startswith('const bar ='))
        self.assertIn("v > 0 ?", line)
        # a value that is not above 0 draws no bar: the false branch is the empty string
        self.assertTrue(line.rstrip().endswith(": '';"), line)

    def test_replay_and_step_cards(self):
        for s in ('`cumulative so far ≈ ${money(costSoFar)}`', f'`{KO_CUMULATIVE} ≈ ${{money(costSoFar)}}`',
                  '${fmtMin(num(e.dur))} · ${money(e.c)}', ' · ${money(sd.cost)}`'):
            self.assertIn(s, self.html, s)

    @unittest.skipIf(shutil.which('node') is None, 'node is not installed')
    def test_script_parses(self):
        scripts = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', self.html, re.S)
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'page.js'
            f.write_text('\n'.join(scripts), encoding='utf-8')
            r = subprocess.run(['node', '--check', str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()

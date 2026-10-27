"""The menu bar app's Detail view selects a task through two things web/index.html already has.
Renaming either breaks the app, so this test fails first. Runs without swiftc."""
import re
import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / 'web' / 'index.html'


class WebContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_select_task_is_a_global_async_function(self):
        self.assertIn('async function selectTask(', self.html)

    def test_task_hash_is_read_at_load(self):
        self.assertIn('/^#task=(.+)$/', self.html)
        self.assertIn('decodeURIComponent(hashTask[1])', self.html)


ST = {
    'run': ('#c25e00', '#ffa94d'), 'wait': ('#d1242f', '#ff6b6b'), 'done': ('#2552c9', '#7ea3ff'),
    'stop': ('#4b5563', '#c9d1d9'), 'past': ('#1d7a3e', '#5fd08a'),
}


class WebStatusColorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')
        i = cls.html.index('@media (prefers-color-scheme: dark)')
        cls.light, cls.dark = cls.html[:i], cls.html[i:cls.html.index('* { box-sizing')]

    def rule(self, selector):
        m = re.search(r'(?m)^' + re.escape(selector) + r'\s*\{([^}]*)\}', self.html)
        if m is None:
            m = re.search(r'[\s}]' + re.escape(selector) + r'\s*\{([^}]*)\}', self.html)
        self.assertIsNotNone(m, selector)
        return m.group(1)

    def test_st_variables_in_both_modes(self):
        for name, (lt, dk) in ST.items():
            self.assertRegex(self.light, r'--st-%s:\s*%s;' % (name, lt))
            self.assertRegex(self.dark, r'--st-%s:\s*%s;' % (name, dk))

    def test_old_variables_unchanged(self):
        for s in ('--ok: #1d7a3e;', '--run: #2552c9;', '--gate: #c43d12;'):
            self.assertIn(s, self.light)
        for s in ('--ok: #5fd08a;', '--run: #7ea3ff;', '--gate: #ff8a5c;'):
            self.assertIn(s, self.dark)

    def test_selectors_use_status_variables(self):
        for sel, var in [
            ('.dot.run', 'st-run'), ('.dot.run.wait', 'st-wait'), ('.frow.live .fn::after', 'st-run'),
            ('.res.run', 'st-run'), ('.badge.run', 'st-run'), ('.badge.wait', 'st-wait'),
            ('.badge.done', 'st-done'), ('.badge.stop', 'st-stop'),
            ('.titem .mini-rail i.done', 'st-past'), ('.titem .mini-rail i.cur', 'st-run'),
            ('.titem .mini-rail i.stop', 'st-stop'), ('.titem .mini-rail.t-wait i.cur', 'st-wait'),
            ('.titem .mini-rail.t-done i', 'st-done'), ('.dots3 i', 'st-run'),
            ('.vs.cur', 'st-run'), ('.t-done .vs.done', 'st-done'),
            ('.t-wait .vs.cur', 'st-wait'), ('.t-stop .vs.cur', 'st-stop'),
        ]:
            self.assertIn('var(--%s)' % var, self.rule(sel), sel)
        for t in ('run', 'wait', 'stop', 'done'):
            self.assertIn('.tmin.%s { color: var(--st-%s)' % (t, t), self.html.replace('} .tmin', '}\n.tmin'))

    def test_vsteps_calls_pass_tone(self):
        calls = [m.start() for m in re.finditer(r'(?<!function )vsteps\(', self.html)]
        self.assertEqual(len(calls), 2)
        for c in calls:
            self.assertIn('tone:', self.html[c:c + 400])

    def test_non_status_colors_kept(self):
        self.assertIn('var(--ok)', self.rule('.gate-lamp.ok'))
        self.assertIn('var(--gate)', self.rule('.gate-lamp.wait'))


if __name__ == '__main__':
    unittest.main()

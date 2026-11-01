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

    def test_components_window_contract(self):
        # the menu bar app hosts window.open('', 'ma-components') and tells the page when the window closes
        self.assertIn("window.open('', 'ma-components'", self.html)
        self.assertRegex(self.html, r'\$\(.p-log.\)\.innerHTML = head[^\n]*\n\s*syncCompWin\(\);')
        self.assertRegex(self.html, r'(?m)^function compWinGone\(\) \{ compWin = null; \}$')
        m = re.search(r'function openCompWin\(\) \{\n([^\n]*)\n', self.html)
        self.assertIsNotNone(m)
        self.assertIn("window.webkit?.messageHandlers?.compFocus?.postMessage('')", m.group(1))
        self.assertIn('compWin.focus()', m.group(1))

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


class ReportTabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')
        a = cls.html.index('/* ---------- report tab ---------- */')
        b = cls.html.index('/* ---------- end report tab ---------- */')
        cls.code = cls.html[a:b]

    def test_fifth_tab_and_panel(self):
        self.assertIn('<button data-tab="report" aria-selected="false"><span class="k">5</span>Report</button>', self.html)
        self.assertIn('<section class="panel" data-view="report" id="p-report"></section>', self.html)
        self.assertLess(self.html.index('data-tab="log"'), self.html.index('data-tab="report"'))

    def test_report_endpoint_fetch(self):
        self.assertIn("'/report'", self.code)
        self.assertIn("encodeURIComponent(key).replace(/%2F/g, '/')", self.code)
        self.assertIn("st.tab === 'report'", self.html[self.html.index('async function poll()'):])

    def test_report_in_change_check(self):
        poll = self.html[self.html.index('async function poll()'):]
        self.assertRegex(poll, r'JSON\.stringify\(\[.*RP\[')

    def test_render_all_clears_report_panel(self):
        self.assertRegex(self.html, r"\['p-arch', 'p-files', 'p-log', 'p-report'\]\.forEach")

    def test_three_parts_in_order(self):
        i = [self.code.index(">%s</h3>" % h) for h in ('Overview', 'Takeaway', 'Follow-up')]
        self.assertEqual(i, sorted(i))

    def test_report_code_reads_reduced_motion(self):
        self.assertIn('prefers-reduced-motion', self.code)

    def test_no_key_5_shortcut(self):
        self.assertNotIn("'5'", self.html)
        self.assertNotIn('"5"', self.html)

    def test_no_write_requests(self):
        self.assertNotRegex(self.html, r'method\s*:')
        self.assertNotIn('XMLHttpRequest', self.html)

    def test_missing_source_notes(self):
        for f in ('scope.md', 'plan.md', 'run-log.md', 'verify.md', 'gate-report.md', 'review.md', 'plan-review.md'):
            self.assertIn("NYW('%s')" % f, self.code)
        self.assertIn('Not written yet: ', self.code)
        self.assertIn('not recorded', self.code)

    def test_tray_layouts_hide_tabs_and_report(self):
        self.assertIn('body.lay-b nav.tabs, body.lay-c nav.tabs { display: none; }', self.html)
        self.assertRegex(self.html, r'body\.lay-b #p-report')


if __name__ == '__main__':
    unittest.main()

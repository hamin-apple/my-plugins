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

    def test_theme_button_contract(self):
        # the menu bar app hides #theme-btn in Detail; the page's auto then follows the window (prefers-color-scheme)
        self.assertIn('id="theme-btn"', self.html)
        self.assertIn('@media (prefers-color-scheme: dark) { :root:not([data-theme="light"])', self.html)

    def test_hash_selects_task_and_tab(self):
        self.assertIn('URLSearchParams', self.html)
        self.assertIn(".get('task')", self.html)
        self.assertIn(".get('tab')", self.html)
        self.assertIn("'report'", self.html[self.html.index('URLSearchParams'):])
        self.assertIn("addEventListener('hashchange'", self.html)
        self.assertNotIn('/^#task=(.+)$/', self.html)


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
            ('#p-report .rbanner.run', 'st-run'), ('#p-report .rbanner.wait', 'st-wait'),
            ('#p-report .rbanner.stop', 'st-stop'),
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

    def parts(self):
        a = self.code.index('function rpParts(')
        return self.code[a:]

    def test_report_order(self):
        p = self.parts()
        i = [p.index(x) for x in ('rpBanner(', 'rpOverview(', 'rpTakeaway(', "'rd-crit'", "'rd-units'", "'rd-tl'", "'rd-fu'", "'rd-more'")]
        self.assertEqual(i, sorted(i))

    def test_disclosure_rows_default_open(self):
        self.assertIn('seeded: new Set()', self.code)
        self.assertEqual(len(re.findall(r'rp\.open\.add\(', self.code)), 2)   # the toggle and the one seed
        i = self.code.index('rp.seeded.has(')
        self.assertIn("'|rd-tl'", self.code[i:i + 300])
        self.assertIn('rp.seeded.add(', self.code[i:i + 300])
        self.assertIn('rp.open.has(', self.code)

    def test_review_summary_format(self):
        i = self.code.index('function rpReviewSum(')
        f = self.code[i:i + 700]
        for w in ('BLOCKER', 'SHOULD-FIX', 'NITPICK', '.found', '.fixed'):
            self.assertIn(w, f)
        self.assertIn('review_totals', self.code)

    def test_gate_views(self):
        for g in ("'G1a'", "'G1b'", "'G3'"):
            self.assertIn(g, self.code)
        self.assertIn('target="_blank" rel="noopener"', self.code)
        self.assertIn('gate.prototype', self.code)
        self.assertIn("L('No prototype'", self.code)
        self.assertIn('gate.units', self.code)
        self.assertIn('gate.groups', self.code)
        self.assertIn('gate.summary', self.code)

    def test_report_fonts(self):
        m = re.search(r'--rp-sans:\s*([^;]*);', self.html)
        self.assertTrue(m.group(1).startswith('-apple-system'))
        self.assertIn('Apple SD Gothic Neo', m.group(1))
        self.assertTrue(re.search(r'--rp-mono:\s*ui-monospace', self.html))
        self.assertNotIn('@font-face', self.html)

    def test_no_new_external_resource(self):
        self.assertEqual(len(re.findall(r'<link rel="stylesheet"[^>]*https://', self.html)), 1)
        self.assertNotIn('@import', self.html)
        self.assertNotIn('<script src=', self.html)
        self.assertNotIn('file://', self.html)

    def test_no_token_word(self):
        self.assertNotIn('token', self.html.lower())
        self.assertNotIn('\ud1a0\ud070', self.html)

    def test_count_up_once_per_task(self):
        self.assertIn('counted: new Set()', self.code)
        self.assertIn('rp.counted.has(', self.code)
        self.assertIn('rp.counted.add(', self.code)
        self.assertIn('data-count', self.code)
        self.assertIn('prefers-reduced-motion', self.code)

    def test_new_labels_bilingual(self):
        for lab in ("L('Background'", "L('Purpose'", "L('Key takeaway'", "L('Decisions \u00b7 review \u00b7 cost'", "L('Completion criteria'",
                    "L('Work units'", "L('Phase timeline'", "L('Follow-up'", "L('Waiting for you at'", "L('Open prototype'",
                    "L('Scope'", "L('Delivered'", "L('Next'"):
            self.assertIn(lab, self.code)

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


class TimelineAxisTest(unittest.TestCase):
    """Both timelines (Report phase timeline, Log parallel timeline) share one tick rule and place records by absolute time."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_tick_rule_is_shared_and_bounded(self):
        self.assertIn('function axisTicks(n0, n1)', self.html)
        self.assertIn('span / (m * 60000) <= 4', self.html)           # at most 4 steps, so at most 5 labels
        self.assertIn('p >= 16 && p <= 84', self.html)                # no label closer than 16% to an edge
        self.assertIn("al: 'l'", self.html)
        self.assertIn("al: 'r'", self.html)
        self.assertEqual(self.html.count('axisHtml(axisTicks('), 1)
        self.assertIn('${axisHtml(ticks)}', self.html)

    def test_date_joins_the_time_across_midnight(self):
        self.assertIn('getUTCDate() !== b.getUTCDate()', self.html)
        self.assertIn("p2(d.getUTCMonth() + 1) + '-' + p2(d.getUTCDate())", self.html)

    def test_log_timeline_uses_absolute_minutes(self):
        a = self.html.index('function timeline(t)')
        body = self.html[a:self.html.index('function replay(t)')]
        self.assertIn('tsm(e.ts, e.t)', body)
        self.assertIn('t.nowTs', body)
        self.assertNotIn('mins(', body)                                # time of day wraps at midnight

    def test_axis_labels_never_wrap(self):
        """The right-aligned end label has no room to its right, so without nowrap it breaks into two lines over the first row."""
        self.assertIn('.tl-axis span { position: absolute; transform: translateX(-50%); white-space: nowrap; }', self.html)
        self.assertIn('#p-report .rtl-axis span { position: absolute; transform: translateX(-50%); white-space: nowrap; }', self.html)
        self.assertIn('function thinAxis(root)', self.html)            # a middle label that would touch a neighbour is hidden after render
        self.assertEqual(self.html.count('thinAxis('), 4)             # the definition, the Log and Report renders, and the shown pane in renderAll
        self.assertIn("thinAxis(document.querySelector('.panel.on'))", self.html)   # a pane renders hidden (display: none), so it is measured again once shown
        self.assertIn('!ax.getBoundingClientRect().width) return', self.html)

    def test_stylesheet_braces_balance(self):
        """An unclosed @media block swallows every rule after it (seen once: the Report rows lost their styles above 520px)."""
        a = self.html.index('<style>') + len('<style>')
        css = self.html[a:self.html.index('</style>', a)]
        depth = 0
        for i, ch in enumerate(css):
            depth += (ch == '{') - (ch == '}')
            self.assertGreaterEqual(depth, 0, f'stray }} at css offset {i}')
        self.assertEqual(depth, 0, 'unclosed { in the stylesheet')

    def test_old_tick_code_is_gone(self):
        self.assertNotIn('stepM = W > 90', self.html)
        self.assertNotIn('const tick = 15 * 60000', self.html)


class ThemeSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_storage_key_and_attribute(self):
        self.assertIn("'ma-theme'", self.html)
        self.assertIn('data-theme', self.html)
        self.assertIn('documentElement', self.html)

    def test_three_states_cycle(self):
        self.assertIn("['auto', 'light', 'dark']", self.html)
        for en, ko in (('Auto', '자동'), ('Light', '라이트'), ('Dark', '다크')):
            self.assertIn("L('%s','%s')" % (en, ko), self.html.replace(', ', ','))

    def test_dark_variables_follow_the_switch(self):
        self.assertIn(':root:not([data-theme="light"])', self.html)
        self.assertIn(':root[data-theme="dark"]', self.html)
        # both dark blocks carry the same values
        a = re.search(r'prefers-color-scheme: dark\) \{ :root:not\(\[data-theme="light"\]\) \{([^}]*)\}', self.html)
        b = re.search(r':root\[data-theme="dark"\] \{([^}]*)\}', self.html)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.group(1).split(), b.group(1).split())

    def test_light_forced_keeps_color_scheme(self):
        self.assertIn(':root[data-theme="light"] { color-scheme: light; }', self.html)


class OverviewListFormTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parent.parent / 'web' / 'index.html').read_text(encoding='utf-8')

    def test_list_form_shares_the_paragraph_style(self):
        fn = re.search(r'function rpOverview\(d\) \{.*?\n\}\n', self.html, re.S).group(0)
        self.assertNotIn('ovl', fn)
        self.assertEqual(fn.count('<dl class="ov">'), 2)
        for en in ('Task', 'Profile', 'Status', 'Delivered', 'Follows', 'Request'):
            self.assertIn("L('%s'," % en, fn)
        self.assertNotIn('.ovl', self.html)

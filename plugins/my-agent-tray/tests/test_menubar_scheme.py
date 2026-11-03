"""Menu bar app: the color scheme (auto, light, dark) of the mini window and the Components window.
--print-scheme shows the decision; source checks pin where it is applied. Runs the app build like test_menubar."""
import re
import subprocess
import unittest

import test_menubar as tm

SOURCES = tm.MENUBAR / 'Sources'


def source(name):
    return (SOURCES / name).read_text(encoding='utf-8')


class SchemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not tm.swiftc_works():
            raise unittest.SkipTest('swiftc unavailable')
        r = subprocess.run(['sh', str(tm.MENUBAR / 'build.sh')], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise AssertionError(f'macos/menubar/build.sh failed: {r.stdout}{r.stderr}')

    def scheme(self, *argv):
        r = subprocess.run([str(tm.BINARY), '--print-scheme', *argv], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip('\n').split('\t')

    def test_values(self):
        self.assertEqual(self.scheme('auto'), ['auto', 'light', 'none', 'circle.lefthalf.filled'])
        self.assertEqual(self.scheme('light'), ['light', 'dark', 'aqua', 'sun.max'])
        self.assertEqual(self.scheme('dark'), ['dark', 'auto', 'darkAqua', 'moon'])

    def test_missing_or_unknown_is_auto(self):
        for argv in ((), ('',), ('Dark',), ('system',)):
            with self.subTest(argv=argv):
                self.assertEqual(self.scheme(*argv)[0], 'auto')

    def test_click_cycles_through_all_three(self):
        seen, s = [], 'auto'
        for _ in range(3):
            seen.append(s)
            s = self.scheme(s)[1]
        self.assertEqual(seen, ['auto', 'light', 'dark'])
        self.assertEqual(s, 'auto')


class SchemeSourceTest(unittest.TestCase):
    def test_saved_under_scheme(self):
        s = source('Views.swift')
        self.assertIn('settings.set(scheme.rawValue, forKey: "scheme")', s)
        self.assertIn('Scheme(saved: settings.string(forKey: "scheme"))', s)

    def test_header_button_cycles(self):
        s = source('Views.swift')
        header = s[s.index('struct Header'):s.index('struct ListView')]
        self.assertIn('store.scheme = store.scheme.next', header)
        self.assertIn('store.scheme.symbol', header)

    def test_both_windows_follow(self):
        w = source('Window.swift')
        self.assertIn('win.appearance = windowAppearance(store.scheme)', w)
        self.assertIn('store.$scheme', w)
        c = source('CompWindow.swift')
        self.assertIn('win.appearance = windowAppearance(scheme)', c)
        self.assertIn('window?.appearance = windowAppearance(scheme)', c)
        self.assertIn('detail.comp.scheme = scheme', source('Views.swift'))

    def test_not_set_on_the_app(self):
        # NSApp.appearance would also restyle the menu and the menu bar icon
        for name in ('main.swift', 'Window.swift', 'Views.swift', 'CompWindow.swift'):
            with self.subTest(name=name):
                self.assertIsNone(re.search(r'\b(NSApp|app|NSApplication\.shared)\.appearance\b', source(name)))

    def test_detail_hides_page_theme_button(self):
        self.assertIn('#theme-btn{display:none!important}', source('ListModel.swift'))
        self.assertIn('addUserScript', source('Views.swift'))
        self.assertIn('hidePageThemeButtonJS', source('Views.swift'))

    def test_page_auto_follows_the_web_view(self):
        # the page must still have the button the app hides, and its auto must follow prefers-color-scheme
        html = (tm.CORE / 'web' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="theme-btn"', html)
        self.assertIn('@media (prefers-color-scheme: dark) { :root:not([data-theme="light"])', html)


if __name__ == '__main__':
    unittest.main()

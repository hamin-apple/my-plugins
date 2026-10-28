"""Menu bar app: the Components window (--comp-frame logic and source checks). Runs the app build like test_menubar."""
import subprocess
import unittest

from tests import test_menubar as tm

SOURCES = tm.MENUBAR / 'Sources'


class CompFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not tm.swiftc_works():
            raise unittest.SkipTest('swiftc unavailable')
        r = subprocess.run(['sh', str(tm.MENUBAR / 'build.sh')], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise AssertionError(f'menubar/build.sh failed: {r.stdout}{r.stderr}')

    def comp(self, *argv):
        r = subprocess.run([str(tm.BINARY), '--comp-frame', *argv], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_saved_frame_is_restored_as_is(self):
        self.assertEqual(self.comp('100,120,600,700', '0,0,1512,944'), '100,120,600,700')

    def test_saved_frame_on_missing_screen_is_fitted(self):
        self.assertEqual(self.comp('3000,100,560,640', '0,0,1512,944'), '952,100,560,640')

    def test_no_saved_frame_gives_default_size(self):
        self.assertEqual(self.comp('-', '0,0,1000,800'), '220,80,560,640')

    def test_no_saved_frame_gives_features_size(self):
        self.assertEqual(self.comp('-', '0,0,1000,800', '--features', '400,300'), '300,250,400,300')

    def test_bad_input(self):
        for argv in (['-'], ['1,2,3', '0,0,10,10'], ['-', 'x'], ['-', '0,0,10,10', '--features', 'a,b']):
            with self.subTest(argv=argv):
                r = subprocess.run([str(tm.BINARY), '--comp-frame', *argv], capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 2)


class CompSourceTest(unittest.TestCase):
    def test_views_sets_delegate_and_handler(self):
        s = (SOURCES / 'Views.swift').read_text(encoding='utf-8')
        self.assertIn('web.uiDelegate = self', s)
        self.assertIn('createWebViewWith', s)
        self.assertIn('name: "compFocus"', s)
        self.assertIn('func webViewDidClose', s)

    def test_window_will_close_tells_the_page(self):
        s = (SOURCES / 'CompWindow.swift').read_text(encoding='utf-8')
        body = s[s.index('func windowWillClose'):]
        self.assertIn('compWinGone()', body)
        self.assertIn('"frame.components"', s)
        self.assertIn('Components · my-agent', s)

    def test_main_window_close_closes_components(self):
        s = (SOURCES / 'Window.swift').read_text(encoding='utf-8')
        self.assertIn('comp.closeWindow()', s[s.index('func windowWillClose'):])


if __name__ == '__main__':
    unittest.main()

"""Menu bar app: what counts as covering the mini window, the hover record and the re-raise of the icon click (source checks; no build)."""
import unittest

import test_menubar as tm


class InFrontSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = (tm.MENUBAR / 'Sources' / 'Window.swift').read_text(encoding='utf-8')
        start = s.index('private func isInFront(')
        cls.body = s[start:s.index('\n    }\n', start)]

    def test_own_windows_do_not_cover(self):
        # Detail's web view gets a Writing Tools child window (WTAffordanceWindow) that always sits above the window
        self.assertIn('ProcessInfo.processInfo.processIdentifier', self.body)
        self.assertIn('kCGWindowOwnerPID', self.body)
        self.assertIn('owner != me', self.body)

    def test_only_same_level_counts(self):
        self.assertIn('layer == Int(win.level.rawValue)', self.body)
        self.assertIn('if store.pinned { return true }', self.body)


class ToggleSourceTest(unittest.TestCase):
    def test_hover_handler_has_the_tracking_area_selector(self):
        # NSTrackingArea sends mouseEntered:; a plain @objc func mouseEntered(with:) exports mouseEnteredWith: and never runs
        s = (tm.MENUBAR / 'Sources' / 'main.swift').read_text(encoding='utf-8')
        self.assertIn('@objc(mouseEntered:) func mouseEntered(with event: NSEvent)', s)
        self.assertIn('windows.noteHover()', s)

    def test_show_raises_again_when_covered(self):
        s = (tm.MENUBAR / 'Sources' / 'Window.swift').read_text(encoding='utf-8')
        start = s.index('    func show() {')
        body = s[start:s.index('\n    }\n', start)]
        self.assertIn('for delay in [0.1, 0.4]', body)
        self.assertIn('!self.isInFront(win)', body)
        self.assertEqual(body.count('orderFrontRegardless()'), 2)


if __name__ == '__main__':
    unittest.main()

"""monitor.opener: open mode, default-browser detection, per-browser commands. Nothing here opens a window."""
import functools
import json
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monitor import opener

open_darwin = functools.partial(opener.open_monitor, platform='darwin')

URL = 'http://127.0.0.1:8765/'


def plist_with(handlers):
    return {'LSHandlers': handlers} if handlers is not None else {}


class FakeRun:
    """Records argv; `script` is a list of returncodes or exceptions, one per call (last one repeats)."""

    def __init__(self, *script):
        self.script = list(script) or [0]
        self.argvs = []

    def __call__(self, argv, **kw):
        self.argvs.append(argv)
        step = self.script[min(len(self.argvs), len(self.script)) - 1]
        if isinstance(step, BaseException):
            raise step
        return subprocess.CompletedProcess(argv, step)


class ReadModeTest(unittest.TestCase):
    def mode(self, text):
        with tempfile.TemporaryDirectory() as d:
            if text is not None:
                (Path(d) / 'monitor-config.json').write_text(text)
            return opener.read_mode(d)

    def test_values(self):
        self.assertEqual(self.mode(None), 'window')
        self.assertEqual(self.mode('{"open": "tab"}'), 'tab')
        self.assertEqual(self.mode('{"open": "window"}'), 'window')
        self.assertEqual(self.mode('{"open": "popup"}'), 'window')
        self.assertEqual(self.mode('{not json'), 'window')
        self.assertEqual(self.mode('[]'), 'window')


class ReadBrowserTest(unittest.TestCase):
    def browser(self, text):
        with tempfile.TemporaryDirectory() as d:
            if text is not None:
                (Path(d) / 'monitor-config.json').write_text(text)
            return opener.read_browser(d)

    def test_values(self):
        self.assertEqual(self.browser(None), 'default')
        self.assertEqual(self.browser('{"browser": "safari"}'), 'safari')
        self.assertEqual(self.browser('{"browser": "chrome", "open": "tab"}'), 'chrome')
        self.assertEqual(self.browser('{"browser": "default"}'), 'default')
        self.assertEqual(self.browser('{"browser": "firefox"}'), 'default')
        self.assertEqual(self.browser('{"browser": 3}'), 'default')
        self.assertEqual(self.browser('{"open": "tab"}'), 'default')
        self.assertEqual(self.browser('{not json'), 'default')
        self.assertEqual(self.browser('[]'), 'default')


class WriteBrowserTest(unittest.TestCase):
    def test_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / 'monitor-config.json'
            cfg.write_text('{"open": "tab", "extra": [1]}')
            self.assertTrue(opener.write_browser(d, 'chrome'))
            self.assertEqual(json.loads(cfg.read_text()), {'open': 'tab', 'extra': [1], 'browser': 'chrome'})
            self.assertTrue(opener.write_browser(d, 'default'))
            self.assertEqual(json.loads(cfg.read_text())['browser'], 'default')
            self.assertEqual(json.loads(cfg.read_text())['open'], 'tab')

    def test_creates_file_and_folder(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / 'new' / 'dir'
            self.assertTrue(opener.write_browser(sub, 'safari'))
            self.assertEqual(json.loads((sub / 'monitor-config.json').read_text()), {'browser': 'safari'})

    def test_broken_file_is_replaced_and_bad_value_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / 'monitor-config.json'
            cfg.write_text('{broken')
            self.assertFalse(opener.write_browser(d, 'firefox'))
            self.assertEqual(cfg.read_text(), '{broken')
            self.assertTrue(opener.write_browser(d, 'safari'))
            self.assertEqual(json.loads(cfg.read_text()), {'browser': 'safari'})


class DefaultBrowserTest(unittest.TestCase):
    def browser(self, data=None, raw=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ls.plist'
            if data is not None:
                p.write_bytes(plistlib.dumps(data))
            elif raw is not None:
                p.write_bytes(raw)
            return opener.default_browser(str(p))

    def http(self, bundle):
        return plist_with([{'LSHandlerURLScheme': 'http', 'LSHandlerRoleAll': bundle}])

    def test_http_handler(self):
        self.assertEqual(self.browser(self.http('com.google.Chrome')), 'com.google.chrome')
        self.assertEqual(self.browser(self.http('com.apple.Safari')), 'com.apple.safari')
        self.assertEqual(self.browser(self.http('org.mozilla.firefox')), 'org.mozilla.firefox')

    def test_readable_without_http_means_safari(self):
        self.assertEqual(self.browser(plist_with(None)), 'com.apple.safari')
        self.assertEqual(self.browser(plist_with([])), 'com.apple.safari')
        mail = plist_with([{'LSHandlerURLScheme': 'mailto', 'LSHandlerRoleAll': 'com.apple.mail'}])
        self.assertEqual(self.browser(mail), 'com.apple.safari')

    def test_unknown(self):
        self.assertIsNone(self.browser())
        self.assertIsNone(self.browser(raw=b'not a plist'))
        self.assertIsNone(self.browser(data=['a', 'list']))


class KindTest(unittest.TestCase):
    def test_kind(self):
        self.assertEqual(opener.kind('com.apple.safari'), 'safari')
        for b in ('com.google.chrome', 'com.google.chrome.canary', 'com.microsoft.edgemac', 'com.brave.browser',
                  'org.chromium.chromium', 'com.vivaldi.vivaldi'):
            self.assertEqual(opener.kind(b), 'chromium', b)
        self.assertEqual(opener.kind('org.mozilla.firefox'), 'other')
        self.assertEqual(opener.kind(None), 'other')


class OpenMonitorTest(unittest.TestCase):
    def test_safari_window(self):
        run = FakeRun(0)
        self.assertEqual(open_darwin(URL, 'window', run, 'com.apple.safari'), 'window')
        self.assertEqual(len(run.argvs), 1)
        self.assertEqual(run.argvs[0][0], 'osascript')
        self.assertEqual(run.argvs[0][-1], URL)

    def test_safari_rc1_falls_back_to_tab(self):
        run = FakeRun(1, 0)
        self.assertEqual(open_darwin(URL, 'window', run, 'com.apple.safari'), 'tab')
        self.assertEqual(run.argvs[1], ['open', URL])

    def test_safari_timeout_falls_back_to_tab(self):
        run = FakeRun(subprocess.TimeoutExpired('osascript', 5), 0)
        self.assertEqual(open_darwin(URL, 'window', run, 'com.apple.safari'), 'tab')
        self.assertEqual(run.argvs[1], ['open', URL])

    def test_chromium_app_window(self):
        for bundle in ('com.google.chrome', 'com.microsoft.edgemac'):
            run = FakeRun(0)
            self.assertEqual(open_darwin(URL, 'window', run, bundle), 'window')
            self.assertEqual(run.argvs, [['open', '-n', '-b', bundle, '--args', f'--app={URL}',
                                          '--window-size=1200,800']])

    def test_single_tab_open(self):
        for mode, bundle in (('window', 'org.mozilla.firefox'), ('window', None), ('tab', 'com.google.chrome')):
            run = FakeRun(0)
            self.assertEqual(open_darwin(URL, mode, run, bundle), 'tab')
            self.assertEqual(run.argvs, [['open', URL]])

    def test_oserror_gives_failed(self):
        run = FakeRun(OSError('no open'))
        self.assertEqual(open_darwin(URL, 'window', run, 'com.google.chrome'), 'failed')
        self.assertEqual(open_darwin(URL, 'tab', run, None), 'failed')

    def test_all_nonzero_gives_failed(self):
        self.assertEqual(open_darwin(URL, 'window', FakeRun(1), 'com.google.chrome'), 'failed')

    def test_default_browser_detected_per_call(self):
        with mock.patch.object(opener, 'default_browser', side_effect=['com.google.chrome', 'org.mozilla.firefox']):
            a, b = FakeRun(0), FakeRun(0)
            open_darwin(URL, 'window', a)
            open_darwin(URL, 'window', b)
        self.assertEqual(a.argvs[0][:2], ['open', '-n'])
        self.assertEqual(b.argvs, [['open', URL]])


class ForcedBrowserTest(unittest.TestCase):
    """browser='safari' / 'chrome' ignores the default browser (never even detects it)."""

    def open(self, mode, browser, run, bundle='org.mozilla.firefox'):
        with mock.patch.object(opener, 'default_browser', side_effect=AssertionError('must not detect')):
            return open_darwin(URL, mode, run, bundle if bundle else opener._DETECT, browser=browser)

    def test_safari_window_and_tab(self):
        run = FakeRun(0)
        self.assertEqual(self.open('window', 'safari', run), 'window')
        self.assertEqual(run.argvs[0][0], 'osascript')
        self.assertEqual(run.argvs[0][-1], URL)
        run = FakeRun(0)
        self.assertEqual(self.open('tab', 'safari', run, bundle=None), 'tab')
        self.assertEqual(run.argvs, [['open', '-a', 'Safari', URL]])

    def test_chrome_window_and_tab(self):
        run = FakeRun(0)
        self.assertEqual(self.open('window', 'chrome', run, bundle=None), 'window')
        self.assertEqual(run.argvs, [['open', '-n', '-b', 'com.google.chrome', '--args', f'--app={URL}',
                                      '--window-size=1200,800']])
        run = FakeRun(0)
        self.assertEqual(self.open('tab', 'chrome', run), 'tab')
        self.assertEqual(run.argvs, [['open', '-b', 'com.google.chrome', URL]])

    def test_failure_falls_back_to_default_browser_tab(self):
        for browser, mode in (('safari', 'window'), ('safari', 'tab'), ('chrome', 'window'), ('chrome', 'tab')):
            run = FakeRun(1, 0)
            self.assertEqual(self.open(mode, browser, run), 'tab', (browser, mode))
            self.assertEqual(run.argvs[1], ['open', URL])
            run = FakeRun(OSError('x'), subprocess.TimeoutExpired('open', 5))
            self.assertEqual(self.open(mode, browser, run), 'failed', (browser, mode))

    def test_default_and_unknown_use_detection(self):
        for browser in ('default', 'bogus', None):
            run = FakeRun(0)
            open_darwin(URL, 'window', run, 'com.google.chrome', browser=browser)
            self.assertEqual(run.argvs[0][:2], ['open', '-n'], browser)


class OtherPlatformTest(unittest.TestCase):
    """Not macOS: one tab through webbrowser.open; mode, browser and run are not used."""

    def open(self, web_open, platform='linux', mode='window', **kw):
        run = FakeRun(0)
        with mock.patch.object(opener, 'default_browser', side_effect=AssertionError('must not detect')):
            result = opener.open_monitor(URL, mode, run, platform=platform, web_open=web_open, **kw)
        self.assertEqual(run.argvs, [])
        return result

    def test_true_is_tab_called_once(self):
        seen = []
        self.assertEqual(self.open(lambda u: seen.append(u) or True), 'tab')
        self.assertEqual(seen, [URL])

    def test_false_is_failed(self):
        self.assertEqual(self.open(lambda u: False), 'failed')

    def test_raise_is_failed(self):
        def boom(u):
            raise RuntimeError('no browser')
        self.assertEqual(self.open(boom), 'failed')

    def test_win32_and_window_mode_go_the_tab_path(self):
        self.assertEqual(self.open(lambda u: True, platform='win32'), 'tab')
        self.assertEqual(self.open(lambda u: True, mode='window', browser='chrome'), 'tab')

    def test_default_web_open_is_webbrowser(self):
        with mock.patch('webbrowser.open', return_value=True) as w:
            self.assertEqual(opener.open_monitor(URL, 'window', FakeRun(0), platform='linux'), 'tab')
        w.assert_called_once_with(URL)


if __name__ == '__main__':
    unittest.main()

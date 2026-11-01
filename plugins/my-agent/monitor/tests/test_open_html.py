"""open-html.py: open a local HTML file in the browser the way the monitor opens itself. No real browser is opened."""
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'open-html.py'


class FakeRun:
    """Records argv; `script` is a list of returncodes, one per call (last one repeats)."""

    def __init__(self, *script):
        self.script = list(script) or [0]
        self.argvs = []

    def __call__(self, argv, **kw):
        self.argvs.append(argv)
        return subprocess.CompletedProcess(argv, self.script[min(len(self.argvs), len(self.script)) - 1])


class OpenHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.data = self.dir / 'data'
        self.data.mkdir()
        self.task = self.dir / 'task'
        self.task.mkdir()
        self.page = self.task / 'index.html'
        self.page.write_text('<html></html>')
        spec = importlib.util.spec_from_file_location('open_html_under_test', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        return sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None) for p in self.dir.rglob('*'))

    def config(self, obj):
        (self.data / 'monitor-config.json').write_text(json.dumps(obj))

    def call(self, path=None, **kw):
        """(line, exit code, stdout) of main() with the opener's environment faked."""
        before = self.snapshot()
        out = io.StringIO()
        kw.setdefault('platform', 'darwin')
        kw.setdefault('bundle_id', 'com.apple.safari')
        with redirect_stdout(out):
            code = self.mod.main([str(path or self.page), '--data-dir', str(self.data)], **kw)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.getvalue().splitlines()), 1, out.getvalue())
        self.assertEqual(self.snapshot(), before, 'the call must not write anything')
        return out.getvalue().strip()

    def test_macos_window_command_with_file_url(self):
        run = FakeRun(0)
        self.assertEqual(self.call(run=run), 'window')
        self.assertEqual(run.argvs[0][:2], ['osascript', '-e'])
        self.assertEqual(run.argvs[0][-1], self.page.resolve().as_uri())
        self.assertTrue(run.argvs[0][-1].startswith('file://'))
        run = FakeRun(0)
        self.assertEqual(self.call(run=run, bundle_id='com.google.chrome'), 'window')
        self.assertEqual(run.argvs[0][:4], ['open', '-n', '-b', 'com.google.chrome'])
        self.assertIn('--app=' + self.page.resolve().as_uri(), run.argvs[0])

    def test_window_fails_then_plain_open_is_tab(self):
        run = FakeRun(1, 0)
        self.assertEqual(self.call(run=run), 'tab')
        self.assertEqual(run.argvs[-1], ['open', self.page.resolve().as_uri()])

    def test_config_tab_and_browsers(self):
        self.config({'open': 'tab'})
        run = FakeRun(0)
        self.assertEqual(self.call(run=run), 'tab')
        self.assertEqual(run.argvs[0], ['open', self.page.resolve().as_uri()])
        self.config({'browser': 'safari'})
        run = FakeRun(0)
        self.assertEqual(self.call(run=run, bundle_id='com.google.chrome'), 'window')
        self.assertEqual(run.argvs[0][0], 'osascript')
        self.config({'browser': 'chrome'})
        run = FakeRun(0)
        self.assertEqual(self.call(run=run, bundle_id='com.apple.safari'), 'window')
        self.assertEqual(run.argvs[0][:4], ['open', '-n', '-b', 'com.google.chrome'])

    def test_not_macos(self):
        urls = []
        run = FakeRun(0)
        line = self.call(run=run, platform='linux', web_open=lambda u: urls.append(u) or True)
        self.assertEqual((line, urls, run.argvs), ('tab', [self.page.resolve().as_uri()], []))
        self.assertEqual(self.call(run=run, platform='linux', web_open=lambda u: False), 'failed: no browser opened')

    def test_missing_file_and_non_html(self):
        run = FakeRun(0)
        missing = self.task / 'nope' / 'index.html'
        self.assertEqual(self.call(missing, run=run), f'failed: no such file {missing}')
        self.assertEqual(self.call(self.task, run=run), f'failed: no such file {self.task}')
        note = self.task / 'notes.txt'
        note.write_text('x')
        self.assertEqual(self.call(note, run=run), f'failed: not an HTML file {note}')
        self.assertEqual(run.argvs, [])

    def test_unexpected_exception_is_one_failed_line(self):
        def boom(*a, **k):
            raise RuntimeError('boom')
        self.mod.open_monitor = boom
        self.assertEqual(self.call(), 'failed: RuntimeError: boom')

    def test_htm_suffix_and_relative_path_are_made_absolute(self):
        alt = self.task / 'a.htm'
        alt.write_text('x')
        run = FakeRun(0)
        self.assertEqual(self.call(alt, run=run), 'window')


if __name__ == '__main__':
    unittest.main()

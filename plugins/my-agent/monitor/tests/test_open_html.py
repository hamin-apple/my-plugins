"""open-html.py: open a local HTML file in the browser the way the monitor opens itself. No real browser is opened."""
import importlib.util
import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import quote

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


class ReportModeTest(unittest.TestCase):
    """`open-html.py --report <task folder>` against a real monitor server on the report fixture."""

    @classmethod
    def setUpClass(cls):
        import server
        from tests.test_report import ReportEnv
        cls.e = ReportEnv()
        cls.e.start()
        cls.httpd = server.make_server(0, cls.e.registry)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.e.stop()

    def setUp(self):
        from tests.test_report import FULL, PROJECT
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.data = self.dir / 'data'
        self.data.mkdir()
        self.project, self.full = PROJECT, FULL
        self.folder = PROJECT / 'docs' / 'agent' / FULL
        self.key = self.e.keys[FULL]
        self.url = f'http://127.0.0.1:{self.port}/#task={quote(self.key, safe="")}&tab=report'
        spec = importlib.util.spec_from_file_location('open_html_under_test', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self):
        from tests.test_report import snapshot
        return snapshot(self.project), sorted(str(p) for p in self.dir.rglob('*'))

    def call(self, *args, ports=None, expect=0, **kw):
        before = self.snap()
        out = io.StringIO()
        kw.setdefault('platform', 'darwin')
        kw.setdefault('bundle_id', 'com.apple.safari')
        argv = list(args) + ['--ports', ports or str(self.port), '--data-dir', str(self.data)]
        with redirect_stdout(out):
            code = self.mod.main(argv, **kw)
        self.assertEqual(code, expect)
        self.assertEqual(len(out.getvalue().splitlines()), 1, out.getvalue())
        self.assertEqual(self.snap(), before, 'the call must not write anything')
        return out.getvalue().strip()

    def free_port(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

    def test_report_opens_window(self):
        run = FakeRun(0)
        self.assertEqual(self.call('--report', str(self.folder), run=run), 'window')
        self.assertEqual(run.argvs[0][:2], ['osascript', '-e'])
        self.assertEqual(run.argvs[0][-1], self.url)
        self.assertIn('%2F261102-full-report&tab=report', self.url)

    def test_report_tab_from_config(self):
        (self.data / 'monitor-config.json').write_text(json.dumps({'open': 'tab'}))
        run = FakeRun(0)
        self.assertEqual(self.call('--report', str(self.folder), run=run), 'tab')
        self.assertEqual(run.argvs[0], ['open', self.url])

    def test_report_no_browser(self):
        line = self.call('--report', str(self.folder), platform='linux', web_open=lambda u: False)
        self.assertEqual(line, 'failed: no browser opened')
        self.assertEqual(self.call('--report', str(self.folder), '--url', platform='linux', web_open=lambda u: False), self.url)

    def test_report_url_only(self):
        run = FakeRun(0)
        self.assertEqual(self.call('--report', str(self.folder), '--url', run=run), self.url)
        self.assertEqual(run.argvs, [])

    def test_report_monitor_not_running(self):
        port = self.free_port()
        rng = f'{port}-{port + 1}'
        for extra in ([], ['--url']):
            run = FakeRun(0)
            line = self.call('--report', str(self.folder), *extra, ports=rng, run=run)
            self.assertEqual(line, f'failed: monitor not running (ports {rng})')
            self.assertEqual(run.argvs, [])

    def test_report_task_not_listed(self):
        other = self.dir / 'elsewhere' / 'docs' / 'agent' / '261199-x'
        other.mkdir(parents=True)
        (other / 'intake.md').write_text('# x\n')
        run = FakeRun(0)
        line = self.call('--report', str(other), run=run)
        self.assertEqual(line, f'failed: the monitor does not list {other} (projects.txt)')
        self.assertEqual(run.argvs, [])

    def test_report_no_such_folder(self):
        empty = self.dir / 'empty'
        empty.mkdir()
        for path in (empty, self.dir / 'missing'):
            self.assertEqual(self.call('--report', str(path)), f'failed: no such task folder {path}')

    def test_report_relative_folder(self):
        old = os.getcwd()
        os.chdir(self.folder.parent)
        self.addCleanup(os.chdir, old)
        self.assertEqual(self.call('--report', self.full, '--url'), self.url)

    def test_report_and_file_exclusive(self):
        page = self.dir / 'index.html'
        page.write_text('<html></html>')
        for args in (['--report', str(self.folder), str(page)], []):
            with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.mod.main(args + ['--data-dir', str(self.data)])
            self.assertEqual(cm.exception.code, 2)

    def test_report_writes_nothing(self):
        # call() compares the fixture and the data folder before and after
        self.call('--report', str(self.folder), run=FakeRun(0))
        self.call('--report', str(self.folder), '--url')

    def test_locate_is_ours(self):
        from monitor.locate import APP, is_ours
        self.assertTrue(is_ours({'app': APP, 'root': '/a/b'}, Path('/a/b')))
        self.assertTrue(is_ours({'app': APP, 'root': '/a/b', 'task_dir': 'x'}, '/a/b'))
        for bad in (None, [], [APP], {'app': 'other', 'root': '/a/b'}, {'app': APP, 'root': '/a/c'}, {'app': APP}, 'text'):
            self.assertFalse(is_ours(bad, Path('/a/b')), bad)


if __name__ == '__main__':
    unittest.main()

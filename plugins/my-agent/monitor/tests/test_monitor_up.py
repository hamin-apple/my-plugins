"""monitor-up.py: start once, report running, skip ports other programs hold, stop only our own server (spec 6.1)."""
import importlib.util
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'monitor-up.py'
PORTS = '8791-8794'


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(('127.0.0.1', port)) == 0


class MonitorUpTest(unittest.TestCase):
    def setUp(self):
        for p in range(8791, 8795):
            if port_open(p):
                self.skipTest(f'port {p} is in use on this machine')
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / 'projects.txt').write_text('')
        self.env = dict(os.environ, MA_TASKS_DIR=str(d), MA_PROJECTS_FILE=str(d / 'projects.txt'),
                        MA_CLAUDE_PROJECTS=str(d / 'claude'))
        self.state = d / 'monitor.json'
        self.foreign = []

    def tearDown(self):
        if self.state.exists():
            try:
                os.kill(json.loads(self.state.read_text())['pid'], signal.SIGTERM)
            except (OSError, ValueError, KeyError):
                pass
        for proc in self.foreign:
            proc.terminate()
            proc.wait(5)
        for p in range(8791, 8795):   # let the next test start with the ports free
            for _ in range(50):
                if not port_open(p):
                    break
                time.sleep(0.1)
        self.tmp.cleanup()

    def up(self, *args):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1, r.stdout)
        return lines[0]

    def start_foreign(self, port):
        proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=self.tmp.name)
        self.foreign.append(proc)
        for _ in range(50):
            if port_open(port):
                return proc
            time.sleep(0.1)
        self.fail('foreign server did not start')

    def health(self, port):
        import http.client
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
        c.request('GET', '/api/health')
        return json.loads(c.getresponse().read())

    def test_starts_when_none(self):
        out = self.up('--no-open', '--ports', PORTS)
        self.assertRegex(out, r'^monitor: http://127\.0\.0\.1:8791/ \(started\)$')
        st = json.loads(self.state.read_text())
        self.assertEqual(st['port'], 8791)
        os.kill(st['pid'], 0)   # alive
        self.assertEqual(self.health(8791)['root'], str(ROOT))

    def test_second_call_reports_running(self):
        self.up('--no-open', '--ports', PORTS)
        pid = json.loads(self.state.read_text())['pid']
        self.assertEqual(self.up('--no-open', '--ports', PORTS), 'monitor: http://127.0.0.1:8791/ (running)')
        self.assertEqual(json.loads(self.state.read_text())['pid'], pid)
        self.assertFalse(port_open(8792))

    def test_skips_foreign_port(self):
        self.start_foreign(8791)
        self.assertEqual(self.up('--no-open', '--ports', PORTS), 'monitor: http://127.0.0.1:8792/ (started)')
        self.assertTrue(port_open(8791))

    def test_status_and_stop(self):
        self.up('--no-open', '--ports', PORTS)
        pid = json.loads(self.state.read_text())['pid']
        self.assertRegex(self.up('status', '--ports', PORTS), r'^monitor: http://127\.0\.0\.1:8791/ \(running')
        self.assertEqual(self.up('stop', '--ports', PORTS), 'monitor: stopped 8791')
        self.assertFalse(self.state.exists())
        with self.assertRaises(OSError):
            for _ in range(30):
                os.kill(pid, 0)
                time.sleep(0.1)
        self.assertEqual(self.up('status', '--ports', PORTS), 'monitor: not running')

    def test_stop_ignores_foreign(self):
        proc = self.start_foreign(8791)
        self.state.write_text(json.dumps({'port': 8791, 'pid': proc.pid, 'root': str(ROOT), 'started': 'x'}))
        self.assertEqual(self.up('stop', '--ports', PORTS), 'monitor: nothing to stop')
        self.assertIsNone(proc.poll())
        self.state.unlink()

    def test_all_ports_busy(self):
        self.start_foreign(8791)
        self.assertEqual(self.up('--no-open', '--ports', '8791-8791'),
                         'monitor: not started (no free port in 8791-8791)')


class OpenModeTest(unittest.TestCase):
    """monitor-up.py loaded in-process with open_monitor stubbed: no window is ever opened."""

    def setUp(self):
        for p in range(8791, 8795):
            if port_open(p):
                self.skipTest(f'port {p} is in use on this machine')
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / 'projects.txt').write_text('')
        self.d = d
        self.env = dict(os.environ, MA_TASKS_DIR=str(d), MA_PROJECTS_FILE=str(d / 'projects.txt'),
                        MA_CLAUDE_PROJECTS=str(d / 'claude'))
        spec = importlib.util.spec_from_file_location('monitor_up_under_test', SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.calls = []
        self.browsers = []
        self.procs = []
        self.result = 'window'

    def tearDown(self):
        state = self.d / 'monitor.json'
        if state.exists():
            try:
                os.kill(json.loads(state.read_text())['pid'], signal.SIGTERM)
            except (OSError, ValueError, KeyError):
                pass
        for p in range(8791, 8795):
            for _ in range(50):
                if not port_open(p):
                    break
                time.sleep(0.1)
        for proc in self.procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self.tmp.cleanup()

    def fake_open(self, url, mode, *a, **kw):
        self.calls.append((url, mode))
        self.browsers.append(kw.get('browser'))
        return self.result

    def up(self, *args):
        buf = io.StringIO()
        real_popen = subprocess.Popen

        def tracking_popen(*a, **kw):
            proc = real_popen(*a, **kw)
            self.procs.append(proc)
            return proc

        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.mod, 'open_monitor', self.fake_open), \
                mock.patch.object(subprocess, 'Popen', tracking_popen), redirect_stdout(buf):
            rc = self.mod.main([*args, '--ports', PORTS])
        self.assertEqual(rc, 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 1, buf.getvalue())
        return lines[0]

    def config(self, text):
        (self.d / 'monitor-config.json').write_text(text)

    def test_new_start_defaults_to_window(self):
        self.assertRegex(self.up(), r'\(started\)$')
        self.assertEqual(self.calls, [('http://127.0.0.1:8791/', 'window')])

    def test_config_tab(self):
        self.config('{"open": "tab"}')
        self.up()
        self.assertEqual([m for _, m in self.calls], ['tab'])

    def test_flag_beats_config(self):
        self.config('{"open": "tab"}')
        self.up('--window')
        self.assertEqual([m for _, m in self.calls], ['window'])

    def test_running_without_flag_opens_nothing(self):
        self.up('--no-open')
        self.assertEqual(self.up(), 'monitor: http://127.0.0.1:8791/ (running)')
        self.assertEqual(self.calls, [])

    def test_running_open_tab(self):
        self.up('--no-open')
        self.up('--open', '--tab')
        self.assertEqual(self.calls, [('http://127.0.0.1:8791/', 'tab')])

    def test_no_open_wins_over_window(self):
        self.up('--no-open', '--window')
        self.assertEqual(self.calls, [])

    def test_task_link(self):
        self.up('--no-open')
        out = self.up('--open', '--task', 'ab12cd34/261025-x')
        self.assertEqual(self.calls, [('http://127.0.0.1:8791/#task=ab12cd34%2F261025-x', 'window')])
        self.assertEqual(out, 'monitor: http://127.0.0.1:8791/ (running)')

    def test_failed_open_still_started_and_exit_0(self):
        self.result = 'failed'
        self.assertEqual(self.up(), 'monitor: http://127.0.0.1:8791/ (started)')

    def test_browser_defaults_to_config_then_default(self):
        self.up('--no-open')
        self.up('--open')
        self.config('{"browser": "safari"}')
        self.up('--open')
        self.config('{"browser": "nope"}')
        self.up('--open')
        self.assertEqual(self.browsers, ['default', 'safari', 'default'])

    def test_browser_option_beats_config(self):
        self.config('{"browser": "safari", "open": "tab"}')
        self.up('--browser', 'chrome')
        self.assertEqual(self.browsers, ['chrome'])
        self.assertEqual([m for _, m in self.calls], ['tab'])
        self.up('--open', '--browser', 'default')
        self.assertEqual(self.browsers, ['chrome', 'default'])

    def test_unknown_browser_option_uses_config_and_exits_0(self):
        self.config('{"browser": "chrome"}')
        self.assertRegex(self.up('--browser', 'firefox'), r'\(started\)$')
        self.assertEqual(self.browsers, ['chrome'])

    def test_no_open_ignores_browser(self):
        self.up('--no-open', '--browser', 'safari')
        self.assertEqual(self.calls, [])

    def test_set_browser_preserves_other_keys(self):
        self.config('{"open": "tab", "x": 1}')
        self.assertEqual(self.up('set-browser', 'safari'), 'monitor: browser set to safari')
        self.assertEqual(json.loads((self.d / 'monitor-config.json').read_text()),
                         {'open': 'tab', 'x': 1, 'browser': 'safari'})
        self.assertEqual(self.calls, [])

    def test_set_browser_creates_file_and_refuses_bad_value(self):
        self.assertRegex(self.up('set-browser', 'firefox'), r'^monitor: browser not changed')
        self.assertFalse((self.d / 'monitor-config.json').exists())
        self.assertRegex(self.up('set-browser'), r'^monitor: browser not changed')
        self.up('set-browser', 'chrome')
        self.assertEqual(json.loads((self.d / 'monitor-config.json').read_text()), {'browser': 'chrome'})


if __name__ == '__main__':
    unittest.main()

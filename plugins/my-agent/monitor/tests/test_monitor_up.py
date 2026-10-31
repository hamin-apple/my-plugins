"""monitor-up.py: start once, report running, skip ports other programs hold, stop only our own server (spec 6.1)."""
import functools
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


class AutostartTest(MonitorUpTest):
    """`autostart` in monitor-config.json: only an explicit JSON false stops a call without --open."""
    OFF = 'monitor: not started (autostart off)'

    def config(self, text):
        (Path(self.tmp.name) / 'monitor-config.json').write_text(text, encoding='utf-8')

    def assert_closed(self):
        self.assertFalse(self.state.exists())
        for p in range(8791, 8795):
            self.assertFalse(port_open(p), p)

    def test_off_no_flag_starts_nothing(self):
        self.config('{"autostart": false}')
        self.assertEqual(self.up('--ports', PORTS), self.OFF)
        self.assert_closed()
        self.assertFalse((Path(self.tmp.name) / 'monitor.log').exists())

    def test_off_no_open_starts_nothing(self):
        self.config('{"autostart": false}')
        self.assertEqual(self.up('--no-open', '--ports', PORTS), self.OFF)
        self.assert_closed()

    def test_off_open_starts(self):
        self.config('{"autostart": false}')
        self.assertRegex(self.up('--open', '--ports', PORTS), r'\(started\)$')

    def test_off_status_stop_set_browser(self):
        self.config('{"autostart": false}')
        self.assertEqual(self.up('status', '--ports', PORTS), 'monitor: not running')
        self.assertEqual(self.up('stop', '--ports', PORTS), 'monitor: nothing to stop')
        self.assertEqual(self.up('set-browser', 'safari'), 'monitor: browser set to safari')
        cfg = json.loads((Path(self.tmp.name) / 'monitor-config.json').read_text())
        self.assertIs(cfg['autostart'], False)

    def test_other_values_start(self):
        for text in ('{"autostart": true}', '{"autostart": "false"}', '{"autostart": 0}', '{broken', '[false]', None):
            with self.subTest(text=text):
                cfg = Path(self.tmp.name) / 'monitor-config.json'
                if text is None:
                    cfg.unlink(missing_ok=True)
                else:
                    self.config(text)
                self.assertRegex(self.up('--no-open', '--ports', PORTS), r'\(started\)$')
                self.up('stop', '--ports', PORTS)
                for _ in range(50):
                    if not port_open(8791):
                        break
                    time.sleep(0.1)


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

    def test_non_macos_failed_open_keeps_the_output_line(self):
        sys.path.insert(0, str(ROOT))
        from monitor import opener
        self.fake_open = functools.partial(opener.open_monitor, platform='linux', web_open=lambda u: False)
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


class DataDirTest(unittest.TestCase):
    """The data folder comes from `--data-dir` (no MA_* override): state, log and the server's project list live there."""

    def setUp(self):
        for p in range(8791, 8795):
            if port_open(p):
                self.skipTest(f'port {p} is in use on this machine')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name) / 'data'
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith('MA_') and k != 'CLAUDE_PLUGIN_OPTION_DATA_DIR'}
        self.env.update(HOME=self.tmp.name, MA_CLAUDE_PROJECTS=str(Path(self.tmp.name) / 'claude'))
        self.addCleanup(self.kill_server)

    def kill_server(self):
        try:
            os.kill(json.loads((self.d / 'monitor.json').read_text())['pid'], signal.SIGTERM)
        except (OSError, ValueError, KeyError):
            pass
        for p in range(8791, 8795):
            for _ in range(50):
                if not port_open(p):
                    break
                time.sleep(0.1)

    def up(self, *args, env=None):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], env=env or self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1, r.stdout)
        return lines[0]

    def tasks(self, port):
        import http.client
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        c.request('GET', '/api/tasks')
        return json.loads(c.getresponse().read())['tasks']

    def test_data_dir_option_places_state_and_server_reads_its_projects(self):
        project = Path(self.tmp.name) / 'proj'
        (project / 'docs' / 'agent' / '261029-x').mkdir(parents=True)
        (project / 'docs' / 'agent' / '261029-x' / 'intake.md').write_text('# Intake\n')
        self.d.mkdir()
        (self.d / 'projects.txt').write_text(f'{project}\n')
        self.assertEqual(self.up('--no-open', '--ports', PORTS, '--data-dir', str(self.d)),
                         'monitor: http://127.0.0.1:8791/ (started)')
        self.assertEqual(json.loads((self.d / 'monitor.json').read_text())['port'], 8791)
        self.assertTrue((self.d / 'monitor.log').exists())
        self.assertEqual([t['id'] for t in self.tasks(8791)], ['261029-x'])

    def test_ma_tasks_dir_beats_data_dir_option(self):
        other = Path(self.tmp.name) / 'other'
        env = dict(self.env, MA_TASKS_DIR=str(other))
        self.up('--no-open', '--ports', PORTS, '--data-dir', str(self.d), env=env)
        self.assertTrue((other / 'monitor.json').exists())
        self.assertFalse((self.d / 'monitor.json').exists())
        os.kill(json.loads((other / 'monitor.json').read_text())['pid'], signal.SIGTERM)

    def test_status_and_stop_with_trailing_data_dir(self):
        self.up('--no-open', '--ports', PORTS, '--data-dir', str(self.d))
        self.assertRegex(self.up('status', '--ports', PORTS, '--data-dir', str(self.d)), r'\(running, since ')
        self.assertEqual(self.up('stop', '--ports', PORTS, '--data-dir', str(self.d)), 'monitor: stopped 8791')
        self.assertFalse((self.d / 'monitor.json').exists())

    def test_data_dir_after_subcommand_and_for_set_browser(self):
        self.assertEqual(self.up('set-browser', 'safari', '--data-dir', str(self.d)), 'monitor: browser set to safari')
        self.assertEqual(json.loads((self.d / 'monitor-config.json').read_text())['browser'], 'safari')

    def test_setting_env_is_used_without_option(self):
        env = dict(self.env, CLAUDE_PLUGIN_OPTION_DATA_DIR=str(self.d))
        self.up('set-browser', 'chrome', env=env)
        self.assertTrue((self.d / 'monitor-config.json').exists())

    def test_default_is_home_my_agent(self):
        self.up('set-browser', 'chrome')
        self.assertTrue((Path(self.tmp.name) / 'dev' / 'log' / 'my-agent' / 'monitor-config.json').exists())


if __name__ == '__main__':
    unittest.main()

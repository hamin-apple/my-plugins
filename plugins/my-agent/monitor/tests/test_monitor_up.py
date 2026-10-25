"""monitor-up.py: start once, report running, skip ports other programs hold, stop only our own server (spec 6.1)."""
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
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()

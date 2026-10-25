"""Menu bar app: builds with the system swiftc, then --print-menu shows menu lines and the commands they run."""
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from pathlib import Path

import server
from monitor.registry import Registry
from tests.fixtures.build_fixtures import CLAUDE, PROJECTS_TXT

ROOT = Path(__file__).resolve().parent.parent
MENUBAR = ROOT / 'menubar'
BINARY = MENUBAR / 'build' / 'my-agent-menubar'
PORTS = '8791-8794'
BROWSER_LINE = r'^Browser: (\*?default) (\*?safari) (\*?chrome)\trun: \S+ \S+/monitor-up\.py set-browser$'
TASK_LINE = re.compile(r'^\S+ · (\d\. .+|–)\t([0-9a-f]{8}/\S+)\trun: \S+ \S+/monitor-up\.py --open --task \2$')


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(('127.0.0.1', port)) == 0


def swiftc_works():
    try:
        return subprocess.run(['/usr/bin/swiftc', '-version'], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class MenubarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not swiftc_works():
            raise unittest.SkipTest('swiftc unavailable')
        try:
            r = subprocess.run(['sh', str(MENUBAR / 'build.sh')], capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            raise AssertionError('menubar/build.sh timed out after 300 s')
        if r.returncode != 0:
            raise AssertionError(f'menubar/build.sh failed: {r.stdout}{r.stderr}')

    def setUp(self):
        for p in range(8791, 8795):
            if port_open(p):
                self.skipTest(f'port {p} is in use on this machine')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def serve(self, projects_txt):
        httpd = server.make_server(0, Registry(projects_txt, claude_root=CLAUDE))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def print_menu(self, port, config=None):
        if config is not None:
            (self.dir / 'monitor-config.json').write_text(config)
        (self.dir / 'monitor.json').write_text(json.dumps({'port': port}))
        env = dict(os.environ, MA_TASKS_DIR=str(self.dir))
        r = subprocess.run([str(BINARY), '--print-menu', '--ports', PORTS], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()

    def check_footer(self, lines):
        self.assertEqual(lines[-4].split('\t')[0], 'Open Monitor')
        self.assertRegex(lines[-4], r'\trun: \S+ \S+/monitor-up\.py --open$')
        self.assertRegex(lines[-3], BROWSER_LINE)
        self.assertEqual(lines[-2], 'Quit')
        self.assertRegex(lines[-1], r'^launch: \S+ \S+/monitor-up\.py --no-open$')
        self.assertEqual(lines[-5], '---')

    def test_running_tasks(self):
        lines = self.print_menu(self.serve(PROJECTS_TXT))
        self.assertEqual(lines[0], 'icon: 2')
        tasks = lines[1:-5]
        self.assertEqual(len(tasks), 2)
        for line in tasks:
            self.assertRegex(line, TASK_LINE)
        ids = sorted(l.split(' · ')[0] for l in tasks)
        self.assertEqual(ids, ['261024-cli-json-output', '261024-hitl-survey'])
        self.assertEqual([l.split('\t')[0].split(' · ')[1] for l in tasks], ['5. Execute', '5. Execute'])
        self.check_footer(lines)

    def test_step_missing_and_unknown(self):
        tasks = [{'id': 'no-step', 'key': 'aaaaaaaa/no-step', 'status': 'running'},
                 {'id': 'odd-step', 'key': 'bbbbbbbb/odd-step', 'status': 'running', 'step': 9}]

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = {'/api/health': {'app': 'my-agent-monitor'}, '/api/tasks': {'tasks': tasks}}.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                if body is not None:
                    self.wfile.write(json.dumps(body).encode())

            def log_message(self, *a):
                pass

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        lines = self.print_menu(httpd.server_address[1])
        self.assertEqual(lines[1].split('\t')[0], 'no-step · –')
        self.assertEqual(lines[2].split('\t')[0], 'odd-step · 9')

    def test_no_running_tasks(self):
        empty = self.dir / 'projects.txt'
        empty.write_text('')
        lines = self.print_menu(self.serve(empty))
        self.assertEqual(lines[0], 'icon: 0')
        self.assertEqual(lines[1], 'No running tasks')
        self.check_footer(lines)

    def browser_marks(self, lines):
        return [bool(g.startswith('*')) for g in re.match(BROWSER_LINE, lines[-3]).groups()]

    def test_browser_line_marks_current_value(self):
        port = self.serve(PROJECTS_TXT)
        cases = [(None, [True, False, False]), ('{"browser": "default"}', [True, False, False]),
                 ('{"browser": "safari", "open": "tab"}', [False, True, False]),
                 ('{"browser": "chrome"}', [False, False, True]),
                 ('{"browser": "firefox"}', [True, False, False]), ('{broken', [True, False, False])]
        for config, marks in cases:
            with self.subTest(config=config):
                (self.dir / 'monitor-config.json').unlink(missing_ok=True)
                lines = self.print_menu(port, config)
                self.assertEqual(self.browser_marks(lines), marks)
                self.check_footer(lines)

    def test_browser_menu_when_server_down_and_no_tasks(self):
        lines = self.print_menu(8792, '{"browser": "chrome"}')
        self.assertEqual(lines[0], 'icon: off')
        self.assertEqual(self.browser_marks(lines), [False, False, True])
        empty = self.dir / 'projects.txt'
        empty.write_text('')
        lines = self.print_menu(self.serve(empty), '{"browser": "safari"}')
        self.assertEqual(lines[1], 'No running tasks')
        self.assertEqual(self.browser_marks(lines), [False, True, False])

    def test_server_down(self):
        lines = self.print_menu(8792)
        self.assertEqual(lines[0], 'icon: off')
        self.assertEqual(lines[1], 'Monitor server is off')
        self.check_footer(lines)


if __name__ == '__main__':
    unittest.main()

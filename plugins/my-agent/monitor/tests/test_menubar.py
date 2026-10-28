"""Menu bar app: builds with the system swiftc, then --print-menu shows menu lines and the commands they run."""
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import urllib.parse
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

    # ---- List / Detail logic (no GUI) ----

    def stub(self, tasks):
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
        return httpd.server_address[1]

    def print_list(self, port, *extra):
        (self.dir / 'monitor.json').write_text(json.dumps({'port': port}))
        env = dict(os.environ, MA_TASKS_DIR=str(self.dir))
        r = subprocess.run([str(BINARY), '--print-list', '--ports', PORTS, *extra], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()

    def run_flag(self, *argv):
        return subprocess.run([str(BINARY), *argv], capture_output=True, text=True, timeout=30)

    MIXED = [
        {'id': 'a-done', 'key': 'k/a-done', 'status': 'done', 'step': 8, 'elapsed': 3060},
        {'id': 'b-run', 'key': 'k/b-run', 'status': 'running', 'step': 5, 'elapsed': 65},
        {'id': 'c-stop', 'key': 'k/c-stop', 'status': 'stopped', 'step': 4, 'elapsed': 40},
        {'id': 'd-wait', 'key': 'k/d-wait', 'status': 'running', 'waiting': True, 'step': 2, 'elapsed': 12},
        {'id': 'e-broken', 'key': 'k/e-broken'},
        {'id': 'f-nostatus', 'key': 'k/f-nostatus', 'step': 3, 'elapsed': 5},
        {'id': 'g-odd', 'key': 'k/g-odd', 'status': 'running', 'step': 12},
        {'id': 'h-stop', 'key': 'k/h-stop', 'status': 'stopped', 'step': 1, 'elapsed': 38},
    ]

    def test_list_sort_puts_running_and_waiting_first(self):
        lines = self.print_list(self.stub(self.MIXED))
        self.assertEqual(lines[0], 'list: 8')
        ids = [l.split('\t')[1] for l in lines[1:]]
        self.assertEqual(ids, ['b-run', 'd-wait', 'g-odd', 'a-done', 'c-stop', 'e-broken', 'f-nostatus', 'h-stop'])

    def test_list_rows(self):
        rows = {l.split('\t')[1]: l.split('\t') for l in self.print_list(self.stub(self.MIXED))[1:]}
        self.assertEqual(rows['b-run'], ['●', 'b-run', '5. Execute', '1h 5m', 'ddddc---', 'pulse', 'k/b-run'])
        self.assertEqual(rows['d-wait'], ['?', 'd-wait', '2. Explore → Scope', '12m', 'dc------', 'pulse', 'k/d-wait'])
        self.assertEqual(rows['a-done'], ['✓', 'a-done', 'Done', '2d 3h', 'dddddddd', '-', 'k/a-done'])
        self.assertEqual(rows['c-stop'], ['■', 'c-stop', '4. Plan Review → G1b', '40m', 'ddds----', '-', 'k/c-stop'])
        self.assertEqual(rows['e-broken'], ['■', 'e-broken', '–', '–', '--------', '-', 'k/e-broken'])
        self.assertEqual(rows['g-odd'][2:5], ['12', '–', 'dddddddd'])
        self.assertEqual(rows['h-stop'][2:5], ['1. Intake', '38m', 's-------'])

    def test_list_pulse_only_for_running(self):
        rows = {l.split('\t')[1]: l.split('\t') for l in self.print_list(self.stub(self.MIXED))[1:]}
        pulses = {k for k, v in rows.items() if v[5] == 'pulse'}
        self.assertEqual(pulses, {'b-run', 'd-wait', 'g-odd'})
        self.assertTrue(all(v[5] in ('pulse', '-') for v in rows.values()))
        # no status but a step: the rail has a current cell, yet the row must not pulse
        self.assertEqual(rows['f-nostatus'][4], 'ddc-----')
        self.assertEqual(rows['f-nostatus'][5], '-')

    def test_list_filters(self):
        port = self.stub(self.MIXED)
        for f, n in {'all': 8, 'running': 3, 'done': 1, 'stopped': 2}.items():
            with self.subTest(filter=f):
                lines = self.print_list(port, '--filter', f)
                self.assertEqual(lines[0], f'list: {n}')
                self.assertEqual(len(lines), n + 1)

        def ids(f):
            return [l.split('\t')[1] for l in self.print_list(port, '--filter', f)[1:]]
        self.assertEqual(ids('running'), ['b-run', 'd-wait', 'g-odd'])
        self.assertEqual(ids('done'), ['a-done'])
        self.assertEqual(ids('stopped'), ['c-stop', 'h-stop'])
        for f in ('running', 'done', 'stopped'):
            self.assertNotIn('e-broken', ids(f))
            self.assertNotIn('f-nostatus', ids(f))

    def test_list_bad_filter(self):
        self.assertEqual(self.run_flag('--print-list', '--filter', 'nope').returncode, 2)

    def test_list_empty_cases(self):
        self.assertEqual(self.print_list(8792), ['list: off', 'Monitor server is off'])
        port = self.stub([])
        self.assertEqual(self.print_list(port), ['list: 0', 'No tasks'])
        self.assertEqual(self.print_list(port, '--filter', 'done'), ['list: 0', 'No done tasks'])
        port = self.stub([self.MIXED[1]])
        self.assertEqual(self.print_list(port, '--filter', 'done'), ['list: 0', 'No done tasks'])
        self.assertEqual(self.print_list(port, '--filter', 'stopped'), ['list: 0', 'No stopped tasks'])

    def fit(self, *rects):
        r = self.run_flag('--fit-frame', *rects)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_fit_frame(self):
        screen = '0,0,1512,944'
        self.assertEqual(self.fit('100,100,300,640', screen), '100,100,300,640')
        self.assertEqual(self.fit('1400,100,300,640', screen), '1212,100,300,640')
        self.assertEqual(self.fit('3000,100,300,640', screen), '1212,100,300,640')
        self.assertEqual(self.fit('0,0,2000,1200', screen), '0,0,1512,944')
        self.assertEqual(self.fit('1700,50,400,300', screen, '1512,0,1920,1080'), '1700,50,400,300')
        self.assertEqual(self.fit('1500,50,400,300', screen, '1512,0,1920,1080'), '1512,50,400,300')
        self.assertEqual(self.fit('-50,-30,300,300', screen), '0,0,300,300')

    def test_fit_frame_bad_input(self):
        for argv in (['1,2,3'], ['1,2,3,4'], ['a,b,c,d', '0,0,10,10'], [],
                     ['nan,0,10,10', '0,0,100,100'], ['0,0,inf,10', '0,0,100,100'],
                     ['0,0,0,10', '0,0,100,100'], ['0,0,10,-5', '0,0,100,100'],
                     ['0,0,10,10', '0,0,0,100']):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_flag('--fit-frame', *argv).returncode, 2)

    def list_frame(self, *argv):
        r = self.run_flag('--list-frame', *argv)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_list_frame(self):
        s = '0,0,1512,944'
        saved = '1180,220,300,640'
        self.assertEqual(self.list_frame(saved, '12', s), '1180,336,300,524 fit')
        self.assertEqual(self.list_frame(saved, '3', s), '1180,678,300,182 fit')
        self.assertEqual(self.list_frame(saved, '0', s), '1180,748,300,112 fit')
        self.assertEqual(self.list_frame(saved, '30', s), '1180,0,300,860 scroll')
        self.assertEqual(self.list_frame('100,700,300,640', '3', s), '100,762,300,182 fit')
        self.assertEqual(self.list_frame('3000,220,300,640', '3', s), '1212,678,300,182 fit')
        self.assertEqual(self.list_frame('1700,300,400,500', '2', s, '1512,0,1920,1080'), '1700,656,400,144 fit')
        self.assertEqual(self.list_frame('100,0,300,50', '3', s), '100,0,300,106 scroll')
        self.assertEqual(self.list_frame('0,500,2000,300', '1', s), '0,694,1512,106 fit')
        # a frame saved by the previous version (height 640) and a new one (height 182) give the same result
        self.assertEqual(self.list_frame('1180,678,300,182', '3', s), '1180,678,300,182 fit')

    def test_list_frame_height_formula(self):
        s = '0,0,1512,944'
        for n in range(6):
            with self.subTest(rows=n):
                x, y, w, h = map(int, self.list_frame('10,300,300,640', str(n), s).split()[0].split(','))
                self.assertEqual(h, 112 if n == 0 else 68 + n * 38)
                self.assertEqual(y + h, 940)

    def test_list_frame_bad_input(self):
        for argv in ([], ['1,2,3,4'], ['1,2,3,4', '3'], ['1,2,3,4', '-1', '0,0,100,100'],
                     ['1,2,3,4', 'x', '0,0,100,100'], ['a,b,c,d', '3', '0,0,100,100']):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_flag('--list-frame', *argv).returncode, 2)

    def test_list_tones(self):
        lines = self.print_list(self.stub(self.MIXED), '--tones')
        rows = {l.split('\t')[1]: l.split('\t')[7:] for l in lines[1:]}
        self.assertEqual(rows, {
            'b-run': ['run', 'ppppr---'], 'd-wait': ['wait', 'pw------'], 'g-odd': ['run', 'pppppppp'],
            'a-done': ['done', 'bbbbbbbb'], 'c-stop': ['stop', 'ppps----'], 'e-broken': ['none', '--------'],
            'f-nostatus': ['none', 'pp------'], 'h-stop': ['stop', 's-------']})

    def test_list_tones_keeps_default_output(self):
        port = self.stub(self.MIXED)
        plain = self.print_list(port)
        toned = self.print_list(port, '--tones')
        self.assertEqual(plain[0], toned[0])
        self.assertEqual(['\t'.join(l.split('\t')[:7]) for l in toned[1:]], plain[1:])
        self.assertTrue(all(len(l.split('\t')) == 9 for l in toned[1:]))

    def test_palette(self):
        r = self.run_flag('--print-palette')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            'run\t#c25e00\t#ffa94d', 'wait\t#d1242f\t#ff6b6b', 'done\t#2552c9\t#7ea3ff',
            'stop\t#4b5563\t#c9d1d9', 'past\t#1d7a3e\t#5fd08a'])

    def test_palette_matches_web(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        dark_at = html.index('prefers-color-scheme: dark')
        values = {}
        for scheme, block in (('light', html[:dark_at]), ('dark', html[dark_at:])):
            values[scheme] = dict(re.findall(r'--st-(run|wait|done|stop|past):\s*(#[0-9a-fA-F]{6})', block))
            self.assertEqual(len(values[scheme]), 5, scheme)
        r = self.run_flag('--print-palette')
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in r.stdout.splitlines():
            tone, light, dark = line.split('\t')
            self.assertEqual((light, dark), (values['light'][tone], values['dark'][tone]), tone)

    def detail(self, *argv):
        r = self.run_flag('--print-detail', *argv)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip('\n')

    def test_detail_actions(self):
        key = '3b51f7d0/261027-monitor-mini-window'
        js = 'typeof selectTask===\'function\'?(selectTask("' + key + '"),1):0'
        self.assertEqual(self.detail('loaded=none', 'port=8765', 'applied=0', 'seq=1', 'key=' + key),
                         'load http://127.0.0.1:8765/#task=3b51f7d0%2F261027-monitor-mini-window')
        self.assertEqual(self.detail('loaded=none', 'port=8765', 'applied=0', 'seq=0'), 'load http://127.0.0.1:8765/')
        self.assertEqual(self.detail('loaded=8765', 'port=8765', 'applied=1', 'seq=2', 'key=' + key), 'select ' + js)
        # same key clicked again: seq still moves, so it is applied again
        self.assertEqual(self.detail('loaded=8765', 'port=8765', 'applied=2', 'seq=3', 'key=' + key), 'select ' + js)
        self.assertEqual(self.detail('loaded=8765', 'port=8765', 'applied=2', 'seq=2', 'key=' + key), 'none')
        self.assertEqual(self.detail('loaded=8765', 'port=8765', 'applied=1', 'seq=2'), 'none')
        self.assertEqual(self.detail('loaded=8765', 'port=8766', 'applied=2', 'seq=2', 'key=' + key),
                         'load http://127.0.0.1:8766/#task=3b51f7d0%2F261027-monitor-mini-window')
        self.assertEqual(self.detail('loaded=8765', 'port=off', 'applied=2', 'seq=2'), 'off')
        self.assertEqual(self.detail('loaded=none', 'port=off', 'applied=0', 'seq=0'), 'off')

    def test_detail_percent_encoding(self):
        for key in ('a/b c', 'x-y._~z', 'über/naïve', 'q?#&=%', 'plain'):
            with self.subTest(key=key):
                out = self.detail('loaded=none', 'port=1', 'applied=0', 'seq=1', 'key=' + key)
                self.assertEqual(out, 'load http://127.0.0.1:1/#task=' + urllib.parse.quote(key, safe=''))

    def test_detail_select_js_escapes_key(self):
        key = 'a"b\\c/d'
        out = self.detail('loaded=1', 'port=1', 'applied=0', 'seq=1', 'key=' + key)
        self.assertEqual(out, 'select typeof selectTask===\'function\'?(selectTask(' + json.dumps(key) + '),1):0')

    def test_detail_bad_input(self):
        for argv in (['loaded=x', 'port=1', 'applied=0', 'seq=0'], ['loaded=none', 'port=1', 'applied=0'],
                     ['loaded=none', 'port=zz', 'applied=0', 'seq=0'], ['loaded=none', 'port=1', 'applied=q', 'seq=0']):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_flag('--print-detail', *argv).returncode, 2)

    # ---- data folder from the setting ----

    def clean_env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ('MA_TASKS_DIR', 'CLAUDE_PLUGIN_OPTION_DATA_DIR')}
        env.update(extra)
        return env

    def test_setting_env_locates_state_and_config(self):
        (self.dir / 'monitor-config.json').write_text('{"browser": "chrome"}')
        (self.dir / 'monitor.json').write_text(json.dumps({'port': self.serve(PROJECTS_TXT)}))
        env = self.clean_env(CLAUDE_PLUGIN_OPTION_DATA_DIR=str(self.dir), HOME=str(self.dir / 'home'))
        r = subprocess.run([str(BINARY), '--print-menu', '--ports', PORTS], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], 'icon: 2')
        self.assertEqual(self.browser_marks(lines), [False, False, True])

    def test_ma_tasks_dir_beats_setting(self):
        other = self.dir / 'other'
        other.mkdir()
        (other / 'monitor-config.json').write_text('{"browser": "safari"}')
        env = self.clean_env(MA_TASKS_DIR=str(other), CLAUDE_PLUGIN_OPTION_DATA_DIR=str(self.dir / 'unused'))
        r = subprocess.run([str(BINARY), '--print-menu', '--ports', PORTS], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(self.browser_marks(r.stdout.splitlines()), [False, True, False])

    def test_default_folder_is_home_my_agent_and_tilde_expands(self):
        home = self.dir / 'home'
        (home / 'my-agent').mkdir(parents=True)
        (home / 'my-agent' / 'monitor-config.json').write_text('{"browser": "chrome"}')
        for setting, expect in (('', [False, False, True]), ('~/nowhere', [True, False, False])):
            with self.subTest(setting=setting):
                env = self.clean_env(HOME=str(home))
                if setting:
                    env['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = setting
                r = subprocess.run([str(BINARY), '--print-menu', '--ports', PORTS], capture_output=True, text=True, env=env, timeout=30)
                self.assertEqual(self.browser_marks(r.stdout.splitlines()), expect)
        (home / 'cfg').mkdir()
        (home / 'cfg' / 'monitor-config.json').write_text('{"browser": "safari"}')
        env = self.clean_env(HOME=str(home), CLAUDE_PLUGIN_OPTION_DATA_DIR='~/cfg')
        r = subprocess.run([str(BINARY), '--print-menu', '--ports', PORTS], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(self.browser_marks(r.stdout.splitlines()), [False, True, False])

    # ---- login item ----

    def run_login_item(self, *args):
        home = self.dir / 'home'
        fake = self.dir / 'fakebin'
        fake.mkdir(exist_ok=True)
        (home / 'Library' / 'LaunchAgents').mkdir(parents=True, exist_ok=True)
        launchctl = fake / 'launchctl'
        launchctl.write_text('#!/bin/sh\nexit 0\n')
        launchctl.chmod(0o755)
        env = dict(os.environ, HOME=str(home), PATH=f'{fake}:{os.environ["PATH"]}')
        r = subprocess.run(['sh', str(MENUBAR / 'login-item.sh'), *args], capture_output=True, text=True, env=env, timeout=30)
        return r, home / 'Library' / 'LaunchAgents' / 'my-agent.monitor-menubar.plist'

    def test_login_item_install_records_folder(self):
        r, plist = self.run_login_item('install', str(self.dir / 'my data'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(self.dir / 'my data'), r.stdout)
        import plistlib
        data = plistlib.loads(plist.read_bytes())
        self.assertEqual(data['EnvironmentVariables'], {'CLAUDE_PLUGIN_OPTION_DATA_DIR': str(self.dir / 'my data')})
        # reinstalling with another folder replaces the value
        r, plist = self.run_login_item('install', str(self.dir / 'second'))
        self.assertEqual(plistlib.loads(plist.read_bytes())['EnvironmentVariables']['CLAUDE_PLUGIN_OPTION_DATA_DIR'],
                         str(self.dir / 'second'))

    def test_login_item_default_and_tilde(self):
        import plistlib
        r, plist = self.run_login_item('install')
        home = self.dir / 'home'
        self.assertEqual(plistlib.loads(plist.read_bytes())['EnvironmentVariables']['CLAUDE_PLUGIN_OPTION_DATA_DIR'],
                         str(home / 'my-agent'))
        r, plist = self.run_login_item('install', '~/dev/agent-data')
        self.assertEqual(plistlib.loads(plist.read_bytes())['EnvironmentVariables']['CLAUDE_PLUGIN_OPTION_DATA_DIR'],
                         str(home / 'dev/agent-data'))

    def test_login_item_escapes_xml(self):
        import plistlib
        r, plist = self.run_login_item('install', str(self.dir / 'a&b<c>'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(plistlib.loads(plist.read_bytes())['EnvironmentVariables']['CLAUDE_PLUGIN_OPTION_DATA_DIR'],
                         str(self.dir / 'a&b<c>'))


if __name__ == '__main__':
    unittest.main()

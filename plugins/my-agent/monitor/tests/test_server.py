import json
import os
from pathlib import Path
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

import server
from monitor.registry import Registry
from monitor.registry import SUMMARY
from tests.fixtures.build_fixtures import CLAUDE, PROJECTS_TXT
from tests.test_report import FULL, PROJECT, ReportEnv

G1B = '261106-gate-g1b'


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, {'MA_TASK_DIR': 'docs/agent'})   # the fixtures live under docs/agent
        cls.env.start()
        cls.httpd = server.make_server(0, Registry(PROJECTS_TXT, claude_root=CLAUDE))
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path, method='GET'):
        with urllib.request.urlopen(urllib.request.Request(self.base + path, method=method)) as r:
            return r.status, r.headers, r.read()

    def test_list(self):
        status, headers, body = self.get('/api/tasks')
        data = json.loads(body)
        self.assertEqual((status, len(data['tasks'])), (200, 5))
        self.assertRegex(data['now'], r'^\d\d:\d\d$')
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_health(self):
        status, _, body = self.get('/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'app': 'my-agent-monitor', 'root': str(Path(server.__file__).resolve().parent),
                                                'task_dir': 'docs/agent'})

    def test_task_by_key(self):
        key = json.loads(self.get('/api/tasks')[2])['tasks'][0]['key']
        t = json.loads(self.get('/api/tasks/' + key)[2])
        self.assertEqual(t['id'], '261024-cli-json-output')
        self.assertIn('① Define', self.get('/api/tasks/' + key)[2].decode('utf-8'))   # ensure_ascii=False

    def test_index(self):
        status, headers, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])

    def test_index_reads_task_from_hash(self):
        body = self.get('/')[2].decode('utf-8')
        self.assertIn('location.hash', body)
        self.assertIn('URLSearchParams', body)
        self.assertIn("get('tab')", body)

    def test_unknown_key_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get('/api/tasks/deadbeef/nope')
        self.assertEqual(cm.exception.code, 404)

    def test_post_405(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get('/api/tasks', method='POST')
        self.assertEqual(cm.exception.code, 405)

    def test_binds_localhost_only(self):
        self.assertEqual(self.httpd.server_address[0], '127.0.0.1')

    def test_port_fallback(self):
        busy = server.make_server(0, None)
        try:
            port = busy.server_address[1]
            httpd = server.bind(range(port, port + 2), None)
            self.assertEqual(httpd.server_address[1], port + 1)
            httpd.server_close()
        finally:
            busy.server_close()


class ReportRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = ReportEnv()
        cls.e.start()
        cls.httpd = server.make_server(0, cls.e.registry)
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.e.stop()

    def get(self, path, method='GET'):
        with urllib.request.urlopen(urllib.request.Request(self.base + path, method=method)) as r:
            return r.status, json.loads(r.read())

    def test_report_200_for_key_with_slash(self):
        key = self.e.keys[FULL]
        self.assertIn('/', key)
        status, data = self.get(f'/api/tasks/{key}/report')
        self.assertEqual(status, 200)
        self.assertEqual(data['overview']['task'], FULL)
        self.assertEqual(len(data['criteria']), 3)

    def test_task_by_key_is_not_the_report(self):
        status, data = self.get('/api/tasks/' + self.e.keys[FULL])
        self.assertEqual((status, data['id']), (200, FULL))
        self.assertNotIn('timeline', data)

    def test_unknown_key_404(self):
        for path in ('/api/tasks/deadbeef/nope/report', '/api/tasks/deadbeef/report'):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(path)
            self.assertEqual(cm.exception.code, 404)

    def test_post_405(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get(f'/api/tasks/{self.e.keys[FULL]}/report', method='POST')
        self.assertEqual(cm.exception.code, 405)

    def test_list_and_health_keep_their_shape(self):
        status, data = self.get('/api/tasks')
        self.assertEqual((status, sorted(data), len(data['tasks'])), (200, ['now', 'tasks'], 9))
        self.assertEqual(set(data['tasks'][0]), set(SUMMARY))
        status, health = self.get('/api/health')
        self.assertEqual(sorted(health), ['app', 'root', 'task_dir'])

    def raw(self, path, method='GET'):
        return urllib.request.urlopen(urllib.request.Request(self.base + path, method=method))

    def proto_path(self):
        return f'/api/tasks/{self.e.keys[G1B]}/prototype'

    def test_prototype_served(self):
        expected = (PROJECT / 'docs/agent' / G1B / 'prototype/index.html').read_bytes()
        with self.raw(self.proto_path()) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read(), expected)
            self.assertEqual(r.headers['Content-Type'], 'text/html; charset=utf-8')
            self.assertEqual(r.headers['Content-Security-Policy'], 'sandbox allow-scripts')
            self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(r.headers['Cache-Control'], 'no-store')

    def test_prototype_missing(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get(f'/api/tasks/{self.e.keys[FULL]}/prototype')
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(json.loads(cm.exception.read()), {'error': 'no prototype'})

    def test_prototype_unknown_key(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get('/api/tasks/00000000/nope/prototype')
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(json.loads(cm.exception.read()), {'error': 'no such task'})

    def test_prototype_extra_parts(self):
        for path in (self.proto_path() + '/x', f'/api/tasks/{self.e.keys[G1B]}/../prototype',
                     f'/api/tasks/{self.e.keys[G1B]}/prototype/..'):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as cm:
                self.get(path)
            self.assertEqual(cm.exception.code, 404, path)
            self.assertNotIn(b'<html', cm.exception.read().lower())

    def test_prototype_post_405(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get(self.proto_path(), method='POST')
        self.assertEqual(cm.exception.code, 405)

    def test_report_gate_points_to_served_prototype(self):
        status, data = self.get(f'/api/tasks/{self.e.keys[G1B]}/report')
        self.assertEqual(data['gate']['prototype'], self.proto_path())
        with self.raw(data['gate']['prototype']) as r:
            self.assertEqual(r.status, 200)


if __name__ == '__main__':
    unittest.main()

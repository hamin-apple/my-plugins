import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

import server
from monitor.registry import Registry
from tests.fixtures.build_fixtures import CLAUDE, PROJECTS_TXT


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(0, Registry(PROJECTS_TXT, claude_root=CLAUDE))
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
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
        self.assertEqual(json.loads(body), {'app': 'my-agent-monitor', 'root': str(Path(server.__file__).resolve().parent)})

    def test_task_by_key(self):
        key = json.loads(self.get('/api/tasks')[2])['tasks'][0]['key']
        t = json.loads(self.get('/api/tasks/' + key)[2])
        self.assertEqual(t['id'], '261024-cli-json-output')
        self.assertIn('CLI에', self.get('/api/tasks/' + key)[2].decode('utf-8'))   # ensure_ascii=False

    def test_index(self):
        status, headers, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])

    def test_index_reads_task_from_hash(self):
        body = self.get('/')[2].decode('utf-8')
        self.assertIn('location.hash', body)
        self.assertIn('/^#task=(.+)$/', body)

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


if __name__ == '__main__':
    unittest.main()

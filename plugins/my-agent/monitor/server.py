"""my-agent monitor: read-only local server. Usage: python3 server.py [--port N]"""
import argparse
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from monitor.registry import Registry

HOST = '127.0.0.1'
PORTS = range(8765, 8776)
ROOT = Path(__file__).resolve().parent
INDEX = ROOT / 'web' / 'index.html'


class Handler(BaseHTTPRequestHandler):
    registry = None

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/index.html'):
            try:
                return self._send(200, INDEX.read_bytes(), 'text/html; charset=utf-8')
            except OSError:
                return self._json(404, {'error': 'web/index.html missing'})
        if path == '/api/health':
            return self._json(200, {'app': 'my-agent-monitor', 'root': str(ROOT)})
        if path == '/api/tasks':
            return self._json(200, {'tasks': self.registry.list_tasks(), 'now': datetime.now().strftime('%H:%M')})
        if path.startswith('/api/tasks/'):
            task = self.registry.get_task(path[len('/api/tasks/'):])
            return self._json(200, task) if task else self._json(404, {'error': 'no such task'})
        self._json(404, {'error': 'not found'})

    def _405(self):
        self.send_response(405)
        self.send_header('Allow', 'GET')
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = _405

    def log_message(self, *args):
        pass


def make_server(port, registry):
    handler = type('BoundHandler', (Handler,), {'registry': registry})
    return ThreadingHTTPServer((HOST, port), handler)


def bind(ports, registry):
    last = None
    for port in ports:
        try:
            return make_server(port, registry)
        except OSError as exc:
            last = exc
    raise last


def main(argv=None):
    ap = argparse.ArgumentParser(description='my-agent monitor (read-only)')
    ap.add_argument('--port', type=int, help='port (default 8765, falls back up to 8775)')
    args = ap.parse_args(argv)
    httpd = bind([args.port] if args.port else PORTS, Registry())
    print(f'my-agent monitor: http://{HOST}:{httpd.server_address[1]}/', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    sys.exit(main())

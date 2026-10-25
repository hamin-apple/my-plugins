#!/usr/bin/env python3
"""Start the my-agent monitor once and print its URL (architecture 4.7.4, monitor spec 6.1).

usage: monitor-up.py [--open | --no-open] [--ports A-B]
       monitor-up.py status [--ports A-B]
       monitor-up.py stop [--ports A-B]

Prints exactly one line and always exits 0, so the my-agent Router can pass the
line on and carry on when the monitor cannot start. A port that answers
/api/health with this folder as `root` is ours; anything else on a port is
left alone. State goes to $MA_TASKS_DIR (default ~/dev/agent-tasks):
monitor.json (port, pid, root, started) and monitor.log.
"""
import argparse
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = '127.0.0.1'
WAIT_SECS = 3.0


def tasks_dir() -> Path:
    return Path(os.environ.get('MA_TASKS_DIR') or Path.home() / 'dev/agent-tasks')


def health(port: int):
    """The /api/health JSON on that port, or None when nothing (or nothing JSON) answers."""
    try:
        c = http.client.HTTPConnection(HOST, port, timeout=0.5)
        c.request('GET', '/api/health')
        r = c.getresponse()
        body = r.read()
        return json.loads(body) if r.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None


def ours(port: int) -> bool:
    h = health(port)
    return isinstance(h, dict) and h.get('app') == 'my-agent-monitor' and h.get('root') == str(ROOT)


def port_free(port: int) -> bool:
    """Bindable the way server.py binds (allow_reuse_address), so a port in TIME_WAIT counts as free."""
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def url(port: int) -> str:
    return f'http://{HOST}:{port}/'


def find_running(ports):
    return next((p for p in ports if ours(p)), None)


def read_state():
    try:
        return json.loads((tasks_dir() / 'monitor.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def start(ports, open_browser):
    port = find_running(ports)
    if port is not None:
        if open_browser is True:
            subprocess.run(['open', url(port)], check=False)
        return f'monitor: {url(port)} (running)'
    free = next((p for p in ports if port_free(p)), None)
    if free is None:
        return f'monitor: not started (no free port in {ports[0]}-{ports[-1]})'
    d = tasks_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'monitor.log', 'ab') as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py'), '--port', str(free)], cwd=str(ROOT),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic() + WAIT_SECS
    while time.monotonic() < deadline:
        if ours(free):
            state = {'port': free, 'pid': proc.pid, 'root': str(ROOT),
                     'started': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            (d / 'monitor.json').write_text(json.dumps(state), encoding='utf-8')
            if open_browser is not False:
                subprocess.run(['open', url(free)], check=False)
            return f'monitor: {url(free)} (started)'
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if proc.poll() is None:
        proc.terminate()
    return f'monitor: not started (server did not answer on {free}; see {d / "monitor.log"})'


def status(ports):
    port = find_running(ports)
    if port is None:
        return 'monitor: not running'
    st = read_state()
    since = f", since {st['started']}" if st and st.get('port') == port and st.get('started') else ''
    return f'monitor: {url(port)} (running{since})'


def stop(ports):
    st = read_state()
    if not st or not isinstance(st.get('port'), int) or not ours(st['port']):
        return 'monitor: nothing to stop'
    try:
        os.kill(int(st['pid']), signal.SIGTERM)
    except (OSError, ValueError, KeyError, TypeError):
        return f"monitor: nothing to stop (pid in monitor.json is not running)"
    for _ in range(30):
        if not ours(st['port']):
            break
        time.sleep(0.1)
    try:
        (tasks_dir() / 'monitor.json').unlink()
    except OSError:
        pass
    return f"monitor: stopped {st['port']}"


def parse_ports(text: str):
    a, _, b = text.partition('-')
    lo, hi = int(a), int(b or a)
    if not 0 < lo <= hi < 65536:
        raise ValueError(text)
    return list(range(lo, hi + 1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('action', nargs='?', choices=('start', 'status', 'stop'), default='start')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--open', dest='open_browser', action='store_const', const=True, help='always open the browser')
    g.add_argument('--no-open', dest='open_browser', action='store_const', const=False, help='never open the browser')
    ap.add_argument('--ports', default='8765-8775')
    args = ap.parse_args(argv)
    try:
        ports = parse_ports(args.ports)
        line = {'start': lambda: start(ports, args.open_browser), 'status': lambda: status(ports),
                'stop': lambda: stop(ports)}[args.action]()
    except Exception as exc:   # one line and exit 0 whatever happens: my-agent must not stop for the monitor
        line = f'monitor: not started ({type(exc).__name__}: {exc})'
    print(line, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

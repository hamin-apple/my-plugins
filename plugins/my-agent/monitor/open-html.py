#!/usr/bin/env python3
"""Open a local HTML file in the person's browser, the way the monitor opens itself (architecture 4.7.4).

usage: open-html.py <file> [--data-dir DIR]
       open-html.py --report <task folder> [--url] [--ports A-B] [--data-dir DIR]

The mode (window or tab) and the browser come from monitor-config.json in the data folder (ma_data.data_dir:
$MA_TASKS_DIR, else --data-dir, else $CLAUDE_PLUGIN_OPTION_DATA_DIR, else ~/dev/log/my-agent); the file is opened
as a file:// URL through monitor.opener.open_monitor (macOS: window or tab commands; other platforms: one tab
through webbrowser). Prints exactly one line and always exits 0 (argparse's 2 for bad arguments aside), so the
Router carries on: `window`, `tab`, or `failed: <reason>`. Reads only; writes nothing.

--report opens the running monitor (never starts it) on the Report tab of that task folder:
http://127.0.0.1:<port>/#task=<key>&tab=report. With --url it prints that URL and opens nothing.
"""
import argparse
import http.client
import json
import sys
from pathlib import Path
from urllib.parse import quote

from monitor.locate import is_ours
from monitor.opener import open_monitor, read_browser, read_mode
from monitor.taskview import show_path

import ma_data   # on sys.path through monitor/__init__.py

SUFFIXES = ('.html', '.htm')
ROOT = Path(__file__).resolve().parent   # the folder monitor-up.py checks in /api/health
HOST = '127.0.0.1'
DEFAULT_PORTS = '8765-8775'


def _get(port, path):
    """The JSON of a GET on the local monitor, or None on any error or non-200."""
    try:
        c = http.client.HTTPConnection(HOST, port, timeout=0.5)
        c.request('GET', path)
        r = c.getresponse()
        body = r.read()
        return json.loads(body) if r.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None


def _health(port):
    return _get(port, '/api/health')


def _find_running(ports):
    return next((p for p in ports if is_ours(_health(p), ROOT)), None)


def _ports(text):
    a, _, b = text.partition('-')
    lo, hi = int(a), int(b or a)
    if not 0 < lo <= hi < 65536:
        raise ValueError(text)
    return lo, hi


def report_target(folder, ports_text=DEFAULT_PORTS):
    """(URL, None) of the Report tab of the task folder, or (None, 'failed: <reason>')."""
    target = Path(folder).expanduser()
    target = target if target.is_absolute() else Path.cwd() / target
    if not (target / 'intake.md').is_file():
        return None, f'failed: no such task folder {target}'
    lo, hi = _ports(ports_text)
    port = _find_running(range(lo, hi + 1))
    if port is None:
        return None, f'failed: monitor not running (ports {lo}-{hi})'
    tasks = (_get(port, '/api/tasks') or {}).get('tasks') or []
    shown = {show_path(target), show_path(target.resolve())}
    match = next((t for t in tasks if t.get('folder') in shown), None)
    if match is None:
        by_id = [t for t in tasks if t.get('id') == target.name]
        match = by_id[0] if len(by_id) == 1 else None
    if match is None or not match.get('key'):
        return None, f'failed: the monitor does not list {target} (projects.txt)'
    return f'http://{HOST}:{port}/#task={quote(match["key"], safe="")}&tab=report', None


def open_report(folder, url_only=False, ports_text=DEFAULT_PORTS, data_dir_arg=None, **opener_kw) -> str:
    """The one output line for the Report tab of `folder`."""
    try:
        url, failed = report_target(folder, ports_text)
        if failed:
            return failed
        if url_only:
            return url
        data = ma_data.data_dir(data_dir_arg)
        result = open_monitor(url, read_mode(data), browser=read_browser(data), **opener_kw)
        return 'failed: no browser opened' if result == 'failed' else result
    except Exception as exc:   # one line and exit 0 whatever happens
        return f'failed: {type(exc).__name__}: {exc}'


def open_file(path, data_dir_arg=None, **opener_kw) -> str:
    """The one output line for `path`."""
    try:
        target = Path(path).expanduser()
        target = target if target.is_absolute() else Path.cwd() / target
        if not target.is_file():
            return f'failed: no such file {target}'
        if target.suffix.lower() not in SUFFIXES:
            return f'failed: not an HTML file {target}'
        data = ma_data.data_dir(data_dir_arg)
        result = open_monitor(target.resolve().as_uri(), read_mode(data), browser=read_browser(data), **opener_kw)
        return 'failed: no browser opened' if result == 'failed' else result
    except Exception as exc:   # one line and exit 0 whatever happens
        return f'failed: {type(exc).__name__}: {exc}'


def main(argv=None, **opener_kw) -> int:
    """`opener_kw` (run, bundle_id, platform, web_open) go to open_monitor; the tests use them."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('file', nargs='?', default=None)
    g.add_argument('--report', metavar='TASK_FOLDER', help="open the running monitor on this task's Report tab")
    ap.add_argument('--url', action='store_true', help='with --report: print the URL and open nothing')
    ap.add_argument('--ports', default=DEFAULT_PORTS, metavar='A-B', help='with --report: the monitor ports to look at')
    ap.add_argument('--data-dir', default=None, metavar='DIR', help='the my-agent data folder (the plugin setting)')
    args = ap.parse_args(argv)
    if args.report is not None:
        line = open_report(args.report, args.url, args.ports, args.data_dir, **opener_kw)
    else:
        line = open_file(args.file, args.data_dir, **opener_kw)
    print(line, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

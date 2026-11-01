#!/usr/bin/env python3
"""Open a local HTML file in the person's browser, the way the monitor opens itself (architecture 4.7.4).

usage: open-html.py <file> [--data-dir DIR]

The mode (window or tab) and the browser come from monitor-config.json in the data folder (ma_data.data_dir:
$MA_TASKS_DIR, else --data-dir, else $CLAUDE_PLUGIN_OPTION_DATA_DIR, else ~/dev/log/my-agent); the file is opened
as a file:// URL through monitor.opener.open_monitor (macOS: window or tab commands; other platforms: one tab
through webbrowser). Prints exactly one line and always exits 0 (argparse's 2 for bad arguments aside), so the
Router carries on: `window`, `tab`, or `failed: <reason>`. Reads only; writes nothing.
"""
import argparse
import sys
from pathlib import Path

from monitor.opener import open_monitor, read_browser, read_mode

import ma_data   # on sys.path through monitor/__init__.py

SUFFIXES = ('.html', '.htm')


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
    ap.add_argument('file')
    ap.add_argument('--data-dir', default=None, metavar='DIR', help='the my-agent data folder (the plugin setting)')
    args = ap.parse_args(argv)
    print(open_file(args.file, args.data_dir, **opener_kw), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

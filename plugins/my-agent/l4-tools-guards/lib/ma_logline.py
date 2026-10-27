"""Write run-log lines in the 4.7.2 format: `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`.

A value is double-quoted when it is empty or has whitespace, `"`, `'` or `\\`; inside the quotes
`\\` → `\\\\` and `"` → `\\"`. Newlines become one space. The monitor reads lines with shlex.
"""
from datetime import datetime
from pathlib import Path

import ma_schema

SPECIAL = set('"\'\\')


def value_text(value) -> str:
    if value is None:
        return '-'
    if value is True or value is False:
        return 'true' if value else 'false'
    text = str(value).replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    if text == '' or any(c.isspace() or c in SPECIAL for c in text):
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return text


def format_line(kind: str, fields, now: datetime = None) -> str:
    stamp = (now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
    body = ' '.join(f'{k}={value_text(v)}' for k, v in fields)
    return f'{stamp} {kind}: {body}'.rstrip()


def append(log: Path, line: str) -> None:
    with open(log, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def log_error(active, where: str, exc: BaseException) -> None:
    """A `log-error` line in the task's run-log; its own failure is swallowed (hooks never fail the session)."""
    try:
        append(active.log, format_line('log-error', [('where', where), ('error', f'{type(exc).__name__}: {exc}')]))
    except Exception:
        pass


def parse_line(text: str):
    """(kind, fields) of a run-log line, or None; the monitor reads with the same ma_schema.split_line."""
    parsed = ma_schema.split_line(text)
    return parsed[1:] if parsed else None


def read(log: Path) -> list:
    """Parsed (kind, fields) of every readable line; [] when the file is missing."""
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    return [p for p in map(parse_line, text.splitlines()) if p]


def unreadable(log: Path) -> list:
    """Line numbers that look like records but do not parse (they drop out of read(), 4.7.2)."""
    try:
        return ma_schema.unreadable_lines(Path(log).read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return []


HOOK_KINDS = {'call', 'start', 'stop', 'log-error'}


def is_hook_line(kind: str, fields: dict) -> bool:
    """Lines the L4 hooks write; every other line is an L1 (Recorder) line."""
    return kind in HOOK_KINDS or (kind in ('ask', 'answer') and fields.get('gate') == 'G2')

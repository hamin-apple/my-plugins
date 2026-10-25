"""run-log.md line parser (my-agent-architecture.md v0.19, 4.7.2 "줄 형식").

A line is `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`; values with spaces
are double-quoted. Anything else (headings, old-style lines) is ignored.
"""
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

LINE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([a-z][a-z0-9-]*):(?:\s+(.*))?$')


class Line(NamedTuple):
    ts: datetime
    kind: str
    f: dict
    raw: str


def parse_line(text: str):
    m = LINE_RE.match(text.strip())
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
        tokens = shlex.split(m.group(3) or '')
    except ValueError:
        return None
    fields = {}
    for tok in tokens:
        key, sep, value = tok.partition('=')
        if sep:
            fields[key] = value
    return Line(ts, m.group(2), fields, text)


def read_lines(path: Path) -> list:
    """Parsed lines of a run-log; a last line still being written (no newline) is left for the next read."""
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    if text and not text.endswith('\n'):
        text = text[:text.rfind('\n') + 1]
    return [l for l in map(parse_line, text.splitlines()) if l]

"""run-log.md line parser (my-agent-architecture.md 4.7.2 "줄 형식"), the same `ma_schema.split_line` the hooks use.

A line is `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`; values with spaces
are double-quoted. Anything else (headings, old-style lines) is ignored.
"""
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import ma_schema


class Line(NamedTuple):
    ts: datetime
    kind: str
    f: dict
    raw: str


def parse_line(text: str):
    parsed = ma_schema.split_line(text)
    if not parsed:
        return None
    stamp, kind, fields = parsed
    try:
        ts = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    return Line(ts, kind, fields, text)


def read_lines(path: Path) -> list:
    """Parsed lines of a run-log; a last line still being written (no newline) is left for the next read."""
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    if text and not text.endswith('\n'):
        text = text[:text.rfind('\n') + 1]
    return [l for l in map(parse_line, text.splitlines()) if l]

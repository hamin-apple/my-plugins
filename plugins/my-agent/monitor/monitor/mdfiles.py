"""Readers for the Markdown files my-agent keeps in a task folder (spec 5). Section and marker shapes: ma_schema."""
import re
from pathlib import Path

import ma_schema


def _text(p: Path):
    try:
        return Path(p).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def _section(text: str, *names):
    """Lines under the first `## <name>` heading, up to the next `## `, or None."""
    return ma_schema.section_lines(text, *names)


def read_intake(p: Path):
    text = _text(p)
    if text is None:
        return None
    d = {'status': None, 'profile': None, 'location': None, 'title': None, 'delivered': []}
    for line in text.splitlines():
        key, sep, val = line.partition(':')
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        if key == 'Status' and d['status'] is None:
            d['status'] = val.split()[0] if val else None
        elif key == 'Profile':
            d['profile'] = val
        elif key == 'Location':
            d['location'] = val
        elif key == 'Request' and d['title'] is None:
            d['title'] = val
        elif key == 'Delivered' and val:
            d['delivered'].append(val)
    return d


def read_criteria(p: Path) -> int:
    text = _text(p)
    sec = _section(text, 'Completion criteria') if text else None
    return sum(1 for l in sec or [] if re.match(r'\s*\d+\.\s', l))


def read_verify(p: Path) -> list:
    text = _text(p)
    if not text:
        return []
    out = []
    for line in text.splitlines():
        m = re.match(r'\s*-\s*(\d+)\.\s*(PASS|FAIL)\b', line)
        if m:
            out.append('p' if m.group(2) == 'PASS' else 'f')
    return out


def read_plan(p: Path) -> dict:
    d = {'approved_at': None, 'mockup': None, 'prototype': None, 'revisions': []}
    text = _text(p)
    if not text:
        return d
    d['approved_at'] = ma_schema.approved_at(text)
    mock = _section(text, 'Mock-up')
    if mock:
        body = '\n'.join(mock).strip('\n')
        d['mockup'] = body or None
    if ma_schema.prototype_requested_text(text):
        d['prototype'] = 'prototype'
    d['revisions'] = [l[2:].strip() for l in _section(text, 'Revisions') or [] if l.startswith('- ')]
    return d


def read_confirmation(p: Path):
    """`YYYY-MM-DD HH:MM` from scope.md `## Confirmation`, or None."""
    text = _text(p)
    for line in (_section(text, 'Confirmation') if text else None) or []:
        m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', line)
        if m:
            return m.group(1)
    return None

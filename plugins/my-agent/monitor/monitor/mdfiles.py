"""Readers for the Markdown files my-agent keeps in a task folder (spec 5)."""
import re
from pathlib import Path


def _text(p: Path):
    try:
        return Path(p).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def _section(text: str, *names):
    """Lines under the first `## <name>` heading, up to the next `## `."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith('## '):
            if inside:
                break
            inside = line[3:].strip().split(' (')[0] in names
            continue
        if inside:
            out.append(line)
    return out if inside or out else None


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
        elif key in ('요청', 'Request') and d['title'] is None:
            d['title'] = val
        elif key == 'Delivered' and val:
            d['delivered'].append(val)
    return d


def read_active(docs_agent: Path):
    text = _text(Path(docs_agent) / '.active')
    if text is None:
        return None
    d = {'task': None, 'phase': None, 'session': None, 'started': None}
    for line in text.splitlines():
        key, sep, val = line.partition(':')
        if sep and key.strip().lower() in d:
            d[key.strip().lower()] = val.strip()
    return d


def read_criteria(p: Path) -> int:
    text = _text(p)
    sec = _section(text, '완료 기준', 'Criteria') if text else None
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
    d = {'estimate_k': None, 'approved_at': None, 'mockup': None, 'revisions': []}
    text = _text(p)
    if not text:
        return d
    for line in _section(text, 'Estimate') or []:
        if re.search(r'token|토큰', line, re.I):
            m = re.search(r'(\d+)\s*k\b', line)
            if m:
                d['estimate_k'] = int(m.group(1))
                break
    for line in _section(text, 'Approval') or []:
        m = re.search(r'Approved\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', line)
        if m:
            d['approved_at'] = m.group(1)
            break
    mock = _section(text, 'Mock-up')
    if mock:
        body = '\n'.join(mock).strip('\n')
        d['mockup'] = body or None
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

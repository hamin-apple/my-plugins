#!/usr/bin/env python3
"""Scan files for secret-shaped text before a result leaves the task folder (architecture 4.12
"바깥으로 나가기 전 점검": prototype publish, G3 deliver copy, a commit).

usage: secret-scan.py <path>...   (directories are walked; files that are not UTF-8 text are skipped)
Prints `<path>:<line>: <kind>` per hit, never the matched text. Exit 0 clean, 1 hits, 2 no paths or a path that
does not exist (a typo must not read as "clean").
"""
import re
import sys
from pathlib import Path

KINDS = [
    ('aws-key', re.compile(r'AKIA[0-9A-Z]{16}')),
    ('private-key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('env-line', re.compile(r'(?:^|\s)[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)=\S+')),
    ('github-token', re.compile(r'gh[pousr]_[A-Za-z0-9]{36}')),
    ('anthropic-key', re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}')),
]


def files(paths):
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            yield from sorted(f for f in p.rglob('*') if f.is_file())
        elif p.is_file():
            yield p


def scan(path: Path):
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return
    for n, line in enumerate(text.splitlines(), 1):
        for kind, rx in KINDS:
            if rx.search(line):
                yield n, kind


def main(argv) -> int:
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    missing = [a for a in argv if not Path(a).exists()]
    if missing:
        print(f'secret-scan: no such path: {", ".join(missing)}', file=sys.stderr)
        return 2
    hits = 0
    for f in files(argv):
        for n, kind in scan(f):
            print(f'{f}:{n}: {kind}')
            hits += 1
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

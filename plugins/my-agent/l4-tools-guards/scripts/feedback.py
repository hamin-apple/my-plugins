#!/usr/bin/env python3
"""Retro improvement points in the plugin's feedback.md (architecture 4.11).

usage: feedback.py add L<1-4> <task-id> "<text>"   append `- [open] L<n> <YYYY-MM-DD> <task-id>: <text>` under ## Open
       feedback.py count                           print `L1 <n> · L2 <n> · L3 <n> · L4 <n>`, then
                                                   `REVIEW: L<n> has <n> open items` for each level with 4 or more
$MA_FEEDBACK_FILE overrides the file (tests). Exit 0 done, 2 bad arguments.
"""
import datetime
import os
import re
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[2] / 'feedback.md'
OPEN = re.compile(r'^- \[open\] L([1-4]) ')
REVIEW_AT = 4


def path() -> Path:
    return Path(os.environ.get('MA_FEEDBACK_FILE') or DEFAULT)


def add(level: str, task: str, text: str) -> None:
    p = path()
    lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else ['# my-agent feedback', '', '## Open',
                                                                              '', '## Done']
    if '## Open' not in lines:
        lines += ['', '## Open']
    start = lines.index('## Open')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    last = max((i for i in range(start + 1, end) if lines[i].strip()), default=None)
    entry = f'- [open] {level} {datetime.date.today().isoformat()} {task}: {text}'
    if last is None:
        lines[start + 1:end] = ['', entry] + ([''] if end < len(lines) else [])
    else:
        lines.insert(last + 1, entry)
    p.write_text('\n'.join(lines).rstrip('\n') + '\n', encoding='utf-8')


def count() -> str:
    p = path()
    n = {str(i): 0 for i in range(1, 5)}
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            m = OPEN.match(line)
            if m:
                n[m.group(1)] += 1
    out = [' · '.join(f'L{k} {v}' for k, v in n.items())]
    out += [f'REVIEW: L{k} has {v} open items' for k, v in n.items() if v >= REVIEW_AT]
    return '\n'.join(out)


def main(argv) -> int:
    if argv[:1] == ['count'] and len(argv) == 1:
        print(count())
        return 0
    if (len(argv) == 4 and argv[0] == 'add' and re.fullmatch(r'L[1-4]', argv[1]) and argv[2].strip()
            and argv[3].strip() and '\n' not in argv[3]):
        add(argv[1], argv[2].strip(), argv[3].strip())
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

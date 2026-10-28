#!/usr/bin/env python3
"""Retro improvement points in <data folder>/feedback.md (architecture 4.11).

usage: feedback.py add L<1-4> <task-id> "<text>"   append `- [open] L<n> <YYYY-MM-DD> <task-id>: <text>` under ## Open
       feedback.py count                           print `L1 <n> · L2 <n> · L3 <n> · L4 <n>`, then
                                                   `REVIEW: L<n> has <n> open items` for each level with 4 or more
       feedback.py list                            print the open items numbered `<n>. <item without "- [open] ">`
       feedback.py done <n> "<what fixed it>"      move open item <n> (as `list` numbers it) to the end of ## Done
                                                   as `- [done] … → <what fixed it>`
File format: `# my-agent feedback`, `## Open`, `## Done`; one `- [open|done] L<1-4> <YYYY-MM-DD> <task-id>: <text>`
line per item. $MA_FEEDBACK_FILE overrides the file. Any form ends with `--data-dir <folder>` (the data folder; default: the
setting, else ~/dev/my-agent); it is taken only as the last two arguments. Exit 0 done, 2 bad arguments.
"""
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_data  # noqa: E402
import ma_schema  # noqa: E402

OPEN = re.compile(r'^- \[open\] L([1-4]) ')
REVIEW_AT = 4


DATA_DIR = None   # set by main() from a trailing `--data-dir X`


def path() -> Path:
    return ma_data.feedback_file(DATA_DIR)


def load() -> list:
    p = path()
    return p.read_text(encoding='utf-8').splitlines() if p.exists() else ['# my-agent feedback', '', '## Open',
                                                                         '', '## Done']


def save(lines: list) -> None:
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text('\n'.join(lines).rstrip('\n') + '\n', encoding='utf-8')


def span(lines: list, name: str):
    """(heading index, end index) of `## <name>`, adding the section at the end when it is missing."""
    if not any(ma_schema.heading_name(l) == name for l in lines):
        lines += ['', f'## {name}']
    start = next(i for i, l in enumerate(lines) if ma_schema.heading_name(l) == name)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    return start, end


def append_item(lines: list, name: str, entry: str) -> None:
    start, end = span(lines, name)
    last = max((i for i in range(start + 1, end) if lines[i].strip()), default=None)
    if last is None:
        lines[start + 1:end] = ['', entry] + ([''] if end < len(lines) else [])
    else:
        lines.insert(last + 1, entry)


def add(level: str, task: str, text: str) -> None:
    lines = load()
    append_item(lines, 'Open', f'- [open] {level} {datetime.date.today().isoformat()} {task}: {text}')
    save(lines)


def open_items(lines: list) -> list:
    start, end = span(lines, 'Open')
    return [i for i in range(start + 1, end) if OPEN.match(lines[i])]


def listing() -> str:
    lines = load()
    return '\n'.join(f'{n}. {lines[i][len("- [open] "):]}' for n, i in enumerate(open_items(lines), 1))


def done(n: int, fixed: str) -> bool:
    lines = load()
    items = open_items(lines)
    if not 1 <= n <= len(items):
        return False
    item = lines.pop(items[n - 1])
    append_item(lines, 'Done', f'- [done] {item[len("- [open] "):]} → {fixed}')
    save(lines)
    return True


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
    global DATA_DIR
    DATA_DIR = None
    if len(argv) >= 2 and argv[-2] == '--data-dir':
        DATA_DIR, argv = argv[-1], argv[:-2]
    if argv[:1] == ['count'] and len(argv) == 1:
        print(count())
        return 0
    if argv == ['list']:
        out = listing()
        if out:
            print(out)
        return 0
    if (len(argv) == 3 and argv[0] == 'done' and argv[1].isdigit() and argv[2].strip() and '\n' not in argv[2]
            and done(int(argv[1]), argv[2].strip())):
        return 0
    if (len(argv) == 4 and argv[0] == 'add' and re.fullmatch(r'L[1-4]', argv[1]) and argv[2].strip()
            and argv[3].strip() and '\n' not in argv[3]):
        add(argv[1], argv[2].strip(), argv[3].strip())
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

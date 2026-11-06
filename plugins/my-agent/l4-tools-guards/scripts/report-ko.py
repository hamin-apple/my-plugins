#!/usr/bin/env python3
"""The Korean copy of the Report texts (SKILL.md "Gate reports"): which items L1 still has to translate.

usage: report-ko.py --task TASK_FOLDER todo    print {key: {sha, en}} of the items whose copy is missing or stale, then
                                               `report-ko: <n> to translate, <m> current`; writes nothing
       report-ko.py --task TASK_FOLDER check   print only the count line; exit 0 when nothing is left, else 1

The items are the overview (`background`, `purpose`), each completion criterion (`c<n>`) and each work unit title (`u<n>`),
read from scope.md and plan.md with the parsers the Report tab uses. L1 writes <task folder>/report-ko.json as
{"items": {"<key>": {"sha": "<printed sha>", "ko": "<Korean text>"}}}, keeping the other items; an item whose English
source changed gets a new sha, so it shows in English until the copy is updated.
exit: 0 (todo; check with nothing left), 1 check with items left, 2 bad arguments or no such task folder.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_schema  # noqa: E402


def read(path: Path):
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('command', choices=('todo', 'check'))
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    task = Path(args.task)
    if not task.is_dir():
        print(f'report-ko: no such task folder: {task}')
        return 2
    sources = ma_schema.ko_sources(read(task / 'scope.md'), read(task / 'plan.md'))
    current = ma_schema.ko_current(sources, ma_schema.ko_copy(read(task / ma_schema.KO_COPY)))
    todo = {k: {'sha': ma_schema.text_sha(en), 'en': en} for k, en in sources.items() if k not in current}
    count = f'report-ko: {len(todo)} to translate, {len(current)} current'
    if args.command == 'todo':
        print(json.dumps(todo, ensure_ascii=False, indent=1))
        print(count)
        return 0
    print(count)
    return 0 if not todo else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Gate decision tally and report copy for the retrospective (architecture 4.11).

usage: gate-report.py tally [--cwd DIR] [--data-dir DIR]   print the decision table, counters and cost/tokens per stretch of the
                                          active task's run-log, and save them to <task>/gate-tally.md
       gate-report.py copy [--cwd DIR] [--data-dir DIR]    copy <task>/gate-report.md to the report folder as <task-id>.md
                                          (-2, -3 … when the name is taken; the folder is made if missing)
$MA_GATE_REPORT_DIR sets the report folder (default <data folder>/gate-report;
the data folder is $MA_TASKS_DIR, else the setting (--data-dir or CLAUDE_PLUGIN_OPTION_DATA_DIR), else ~/my-agent).
tally exit: 0 printed (also with no decisions), 1 no active task, 2 bad arguments,
            3 gate-tally.md could not be written (the cause is printed).
copy exit: 0 copied, 1 no active task or no gate-report.md, 2 bad arguments,
           3 the copy could not be written (the cause is printed).
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_data  # noqa: E402
import ma_gate_report  # noqa: E402


def shown(path: Path, active) -> str:
    try:
        return str(path.relative_to(active.location))
    except ValueError:
        return str(path)


def tally(active) -> int:
    lines = ma_gate_report.read_stamped(active.log)
    head = [f'gate-report tally: {active.task}']
    if active.log.exists():
        l1, hook, g2 = ma_gate_report.counts(lines)
        head.append(f'run-log: {shown(active.log, active)} (L1 lines {l1}, hook lines {hook}, G2 lines {g2} left out)')
    else:
        head.append(f'run-log: {shown(active.log, active)} missing')
    body = ma_gate_report.tally_text(lines) + '\n'
    target = active.task_dir / 'gate-tally.md'
    try:
        target.write_text('\n'.join(head) + '\n\n' + body, encoding='utf-8')
    except OSError as exc:
        print(f'gate-report: cannot write {target}: {exc}')
        return 3
    print('\n'.join(head) + f'\nsaved: {shown(target, active)}\n\n' + body, end='')
    return 0


def copy(active, data_dir=None) -> int:
    src = active.task_dir / 'gate-report.md'
    if not src.is_file():
        print(f'gate-report: {shown(src, active)} not found')
        return 1
    folder = ma_gate_report.report_dir(data_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        dest = ma_gate_report.free_name(folder, active.task)
        shutil.copyfile(src, dest)
    except OSError as exc:
        print(f'gate-report: cannot copy to {folder}: {exc}')
        return 3
    print(f'copied {shown(src, active)} -> {dest}')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('command', choices=('tally', 'copy'))
    ap.add_argument('--cwd', default=os.getcwd())
    ap.add_argument('--data-dir', help='the my-agent data folder (default: the setting, else ~/my-agent)')
    args = ap.parse_args(argv)   # argparse exits 2 on bad arguments
    active = ma_active.find_active(args.cwd, ma_data.data_dir(args.data_dir))
    if active is None:
        print(f'gate-report: no active my-agent task under {args.cwd}')
        return 1
    return tally(active) if args.command == 'tally' else copy(active, args.data_dir)


if __name__ == '__main__':
    sys.exit(main())

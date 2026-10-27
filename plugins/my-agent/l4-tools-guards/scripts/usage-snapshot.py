#!/usr/bin/env python3
"""Save the main session's token usage per step to <task>/main-usage.json (architecture 4.8.2 "Task records over time").

usage: usage-snapshot.py [--cwd DIR]        the active task of DIR (L1, at the end of a task: accept.md
                                            "Retrospective", SKILL.md "Abort")
       usage-snapshot.py --task-dir DIR     any task folder (archive-tasks.py, or by hand for an older task)
The transcripts are read from $MA_CLAUDE_PROJECTS (default ~/.claude/projects). The task is treated as finished:
the last step window ends 1 second after the last run-log line, as the monitor counts a finished task.
exit: 0 written, 1 no active task (or the task folder does not exist), 2 bad arguments,
      3 nothing written (the run-log has no step line with a session, no transcript was found, or the file could
        not be written; the cause is printed). An existing main-usage.json is never replaced by a partial one.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_subagent  # noqa: E402
import ma_usage  # noqa: E402


def snapshot(task_dir: Path) -> int:
    code, message = ma_usage.write_snapshot(task_dir, ma_subagent.claude_projects(), datetime.now())
    print(message if code == 0 else f'usage-snapshot: {message}')
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--cwd', default=os.getcwd())
    ap.add_argument('--task-dir')
    args = ap.parse_args(argv)   # argparse exits 2 on bad arguments
    if args.task_dir:
        task_dir = Path(args.task_dir).expanduser().resolve()
        if not (task_dir / 'intake.md').is_file():
            print(f'usage-snapshot: {task_dir} is not a task folder (no intake.md)')
            return 1
    else:
        active = ma_active.find_active(args.cwd)
        if active is None:
            print(f'usage-snapshot: no active my-agent task under {args.cwd}')
            return 1
        task_dir = active.task_dir
        if not task_dir.is_dir():
            print(f'usage-snapshot: {task_dir} does not exist')
            return 1
    return snapshot(task_dir)


if __name__ == '__main__':
    sys.exit(main())

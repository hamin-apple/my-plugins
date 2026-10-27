#!/usr/bin/env python3
"""Move finished task folders out of the monitor's list (architecture 4.8.2 "Task records over time").

usage: archive-tasks.py [--days N] [--dry-run] [--projects FILE]
For each project in the project list, a task folder `<project>/docs/agent/<task-id>/` whose `intake.md` says
`Status: done` or `Status: aborted`, and whose last run-log line (or `intake.md` change, without a run-log) is N days
old or more (default 30), moves to `<project>/docs/agent/.archived/<task-id>/` (`-b`, `-c` … when the name is taken).
The task named in that project's `.active` never moves. Before a move, a task without `main-usage.json` gets one
(usage-snapshot) while its transcript still exists; a task whose transcript is gone moves anyway.
The monitor, the menu bar app and `/my-agent status` read only `docs/agent/*/`, so moved tasks leave them without any
change there. To bring a task back, move its folder back to `docs/agent/`.
--dry-run prints what would move and changes nothing. The project list is $MA_PROJECTS_FILE, else
$MA_TASKS_DIR/projects.txt (default ~/dev/agent-tasks/projects.txt). Transcripts: $MA_CLAUDE_PROJECTS.
Run by the person (not by L1). exit: 0 done (also when nothing was due), 2 bad arguments, 3 a move failed.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_schema  # noqa: E402
import ma_subagent  # noqa: E402
import ma_usage  # noqa: E402

ARCHIVED = '.archived'
FINISHED = ma_schema.INTAKE_STATUS[1:]   # done, aborted


def projects_file() -> Path:
    env = os.environ.get('MA_PROJECTS_FILE')
    return Path(env) if env else ma_active.default_tasks_dir() / 'projects.txt'


def projects(path: Path) -> list:
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            p = Path(os.path.expanduser(line))
            if p.is_dir() and p not in out:
                out.append(p)
    return out


def status(task_dir: Path):
    try:
        text = (task_dir / 'intake.md').read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    for line in text.splitlines():
        key, sep, val = line.partition(':')
        if sep and key.strip() == 'Status':
            return val.split()[0] if val.split() else None
    return None


def last_activity(task_dir: Path) -> datetime:
    lines = ma_usage.read_log(task_dir / 'run-log.md')
    if lines:
        return lines[-1][0]
    return datetime.fromtimestamp((task_dir / 'intake.md').stat().st_mtime)


def free_dest(folder: Path, name: str) -> Path:
    dest = folder / name
    for suffix in 'bcdefghijklmnopqrstuvwxyz':
        if not dest.exists():
            return dest
        dest = folder / f'{name}-{suffix}'
    raise OSError(f'no free name for {name} in {folder}')


def due(project: Path, cutoff: datetime) -> list:
    """(task folder, status, last activity) of every task in `project` that may move, oldest first."""
    agent = project / 'docs' / 'agent'
    active = ma_active.read_active(project)
    out = []
    for intake in sorted(agent.glob('*/intake.md')):
        task_dir = intake.parent
        if task_dir.name.startswith('.') or (active and active.task == task_dir.name):
            continue
        st = status(task_dir)
        if st not in FINISHED:
            continue
        when = last_activity(task_dir)
        if when <= cutoff:
            out.append((task_dir, st, when))
    return sorted(out, key=lambda x: x[2])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--projects')
    args = ap.parse_args(argv)   # argparse exits 2 on bad arguments
    if args.days < 0:
        ap.error('--days must be 0 or more')
    now = datetime.now()
    cutoff = now - timedelta(days=args.days)
    root = ma_subagent.claude_projects()
    moved, failed = 0, 0
    for project in projects(Path(args.projects).expanduser() if args.projects else projects_file()):
        for task_dir, st, when in due(project, cutoff):
            folder = task_dir.parent / ARCHIVED
            head = f'{task_dir} ({st}, last {when:%Y-%m-%d})'
            if args.dry_run:
                print(f'would move: {head}')
                continue
            if not (task_dir / ma_usage.SNAPSHOT).exists():
                code, message = ma_usage.write_snapshot(task_dir, root, now)
                print(f'  {message}' if code == 0 else f'  no usage snapshot: {message}')
            try:
                folder.mkdir(exist_ok=True)
                dest = free_dest(folder, task_dir.name)
                task_dir.rename(dest)
            except OSError as exc:
                print(f'cannot move {head}: {exc}')
                failed += 1
                continue
            print(f'moved: {head} -> {dest}')
            moved += 1
    if not args.dry_run:
        print(f'archive-tasks: {moved} moved' + (f', {failed} failed' if failed else '')
              + f' (finished {args.days} days ago or more)')
    return 3 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

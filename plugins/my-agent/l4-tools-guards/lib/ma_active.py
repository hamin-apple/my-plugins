"""Find the active my-agent task for a folder (architecture 4.8.2 "the order in which hooks find .active").

1. the git root of `cwd` (nearest ancestor with a `.git` entry, file or folder) → `<root>/docs/agent/.active`;
   when that root is a linked worktree (`.git` file, e.g. an isolation:worktree agent in
   `<main>/.claude/worktrees/agent-<id>`, probe r2) and has no `.active`, the main worktree's `.active`;
   outside any git repo, the nearest of `cwd` and its ancestors with `docs/agent/.active` (a location such as
   the data folder run from itself, which Intake writes no index line for);
2. `<tasks_dir>/active-index.json` (`{"<run folder>": "<task location>"}`): inside a git repo, only the entry for
   its root (or main worktree), so a run folder such as ~/dev never reaches the repos below it; outside git, the
   entry for `cwd` or its nearest ancestor.

`.active` is four `key: value` lines: task, phase, session, started (4.7.3).
"""
import json
from pathlib import Path
from typing import NamedTuple

import ma_data


class Active(NamedTuple):
    location: Path
    task: str
    phase: str
    session: str
    started: str
    task_dir: Path
    log: Path


BROKEN = ('my-agent: {path} has no `task:` line, so it cannot be read as the active task. As it is, the G1b and '
          'verdict-freshness hooks do not apply. Fix or delete `.active`.')


def in_subagent(inp: dict) -> bool:
    """True when the hook input comes from inside a subagent (it has `agent_id`). The gate hooks skip such calls;
    scope-guard.py covers subagents. A session started with `--agent` has `agent_id` on its main thread too, so the
    gate hooks skip that whole session."""
    return bool(inp.get('agent_id'))


def owns(active: 'Active', inp: dict) -> bool:
    """False only when `.active` `session:` and the input `session_id` are both set and differ: another session of
    the same repo is not this task's session, so the gate hooks let it through (fail open, as session-notice.py
    compares). If either side is empty the hook applies (closed side)."""
    mine, theirs = active.session, inp.get('session_id')
    return not (mine and theirs and mine != theirs)


def default_tasks_dir() -> Path:
    return ma_data.data_dir()


def read_active(location: Path, broken: list = None):
    """The Active task of `location`, or None. A `.active` that exists but cannot be read or has no `task:` line is
    appended to `broken` (C9: hooks warn instead of passing silently)."""
    path = location / 'docs' / 'agent' / '.active'
    try:
        text = path.read_text(encoding='utf-8')
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError):   # there, but unreadable
        text = ''
    f = {}
    for line in text.splitlines():
        key, sep, value = line.partition(':')
        if sep:
            f[key.strip()] = value.strip()
    if not f.get('task'):
        if broken is not None:
            broken.append(path)
        return None
    task_dir = location / 'docs' / 'agent' / f['task']
    return Active(location, f['task'], f.get('phase', ''), f.get('session', ''), f.get('started', ''),
                  task_dir, task_dir / 'run-log.md')


def git_root(start: Path):
    for d in (start, *start.parents):
        if (d / '.git').exists():
            return d
    return None


def main_worktree(root: Path):
    """The main worktree of a linked worktree `root` (its `.git` is a `gitdir:` file), else None."""
    try:
        text = (root / '.git').read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith('gitdir:'):
        return None
    gitdir = (root / text[len('gitdir:'):].strip()).resolve()
    try:
        common = (gitdir / (gitdir / 'commondir').read_text(encoding='utf-8').strip()).resolve()
    except (OSError, UnicodeDecodeError):
        common = gitdir.parent.parent if gitdir.parent.name == 'worktrees' else None
    return common.parent if common is not None and common.name == '.git' else None


def find_active(cwd: str, tasks_dir: Path = None, broken: list = None):
    """The Active task for `cwd`, or None. Never raises. `broken` collects `.active` files it met without a task."""
    try:
        start = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    root = git_root(start)
    if root is not None:
        found = read_active(root, broken)
        if found:
            return found
        main = main_worktree(root) if (root / '.git').is_file() else None
        found = read_active(main, broken) if main is not None else None
        if found:
            return found
        candidates = [root] + ([main] if main is not None else [])   # a repo never takes a parent's index entry
    else:
        for d in (start, *start.parents):
            found = read_active(d, broken)
            if found:
                return found
        candidates = [start, *start.parents]
    try:
        index = json.loads((Path(tasks_dir or default_tasks_dir()) / 'active-index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(index, dict):
        return None
    keys = {}
    for k, v in index.items():
        try:
            keys[Path(k).expanduser().resolve()] = v
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
    for d in candidates:
        if d in keys and isinstance(keys[d], str):
            return read_active(Path(keys[d]).expanduser().resolve(), broken)
    return None

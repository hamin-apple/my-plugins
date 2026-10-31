"""Shared test helpers: temp task folders, hook runner, and the monitor parser as the oracle for run-log lines."""
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
L4 = REPO / 'l4-tools-guards'
sys.path.insert(0, str(L4 / 'lib'))
sys.path.insert(0, str(REPO / 'monitor'))

import ma_data  # noqa: E402
from monitor.events import build_events  # noqa: E402  (monitor oracle)
from monitor.runlog import parse_line, read_lines  # noqa: E402


def records(root, sub=None) -> Path:
    """The records folder of the project at `root`: `<root>/<task_dir>` (follows $MA_TASK_DIR)."""
    return Path(root) / ma_data.task_dir(sub)


@contextlib.contextmanager
def clean_task_env(**env):
    """In-process: $MA_TASK_DIR and $CLAUDE_PLUGIN_OPTION_TASK_DIR removed (then `env` set) for the block."""
    from unittest import mock
    with mock.patch.dict(os.environ):
        os.environ.pop('MA_TASK_DIR', None)
        os.environ.pop('CLAUDE_PLUGIN_OPTION_TASK_DIR', None)
        os.environ.update(env)
        yield


def rel(sub=None) -> str:
    """The task subfolder as a relative path string (follows $MA_TASK_DIR), for command texts."""
    return ma_data.task_dir(sub)


def make_task(root, task='261025-probe-task', phase='1', session='s-test', git=True, sub=None) -> Path:
    """A project at `root` with <task_dir>/.active and an empty task folder; returns the task folder."""
    root = Path(root)
    if git:
        (root / '.git').mkdir(parents=True, exist_ok=True)
    agent = records(root, sub)
    (agent / task).mkdir(parents=True, exist_ok=True)
    (agent / '.active').write_text(f'task: {task}\nphase: {phase}\nsession: {session}\nstarted: 2026-10-25 09:00\n',
                                   encoding='utf-8')
    return agent / task


def parse(line: str) -> dict:
    parsed = parse_line(line)
    assert parsed is not None, f'monitor cannot parse: {line!r}'
    return parsed.f


def log_lines(task_dir) -> list:
    p = Path(task_dir) / 'run-log.md'
    return p.read_text(encoding='utf-8').splitlines() if p.exists() else []


def events(task_dir):
    return build_events(read_lines(Path(task_dir) / 'run-log.md'))


def run_script(path, *args, payload=None, cwd=None, env=None, drop=()) -> subprocess.CompletedProcess:
    """`drop`: names removed from the child environment after the merge."""
    stdin = payload if isinstance(payload, str) or payload is None else json.dumps(payload)
    child = {k: v for k, v in dict(os.environ, **(env or {})).items() if k not in drop}
    return subprocess.run([sys.executable, str(path), *args], input=stdin, capture_output=True, text=True,
                          cwd=cwd, env=child, timeout=30)


def run_hook(script, mode, payload, cwd, env=None, drop=()) -> subprocess.CompletedProcess:
    """Run l4-tools-guards/hooks/<script> <mode> with stdin JSON; `cwd` also goes into the payload."""
    if isinstance(payload, dict):
        payload = dict(payload, cwd=str(cwd))
    args = [mode] if mode else []
    return run_script(L4 / 'hooks' / script, *args, payload=payload, cwd=cwd, env=env, drop=drop)

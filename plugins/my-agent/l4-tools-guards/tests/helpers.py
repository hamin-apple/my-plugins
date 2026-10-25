"""Shared test helpers: temp task folders, hook runner, and the monitor parser as the oracle for run-log lines."""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
L4 = REPO / 'l4-tools-guards'
sys.path.insert(0, str(L4 / 'lib'))
sys.path.insert(0, str(REPO / 'monitor'))

from monitor.events import build_events  # noqa: E402  (monitor oracle)
from monitor.runlog import parse_line, read_lines  # noqa: E402


def make_task(root, task='261025-probe-task', phase='1', session='s-test', git=True) -> Path:
    """A project at `root` with docs/agent/.active and an empty task folder; returns the task folder."""
    root = Path(root)
    if git:
        (root / '.git').mkdir(parents=True, exist_ok=True)
    agent = root / 'docs' / 'agent'
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


def run_script(path, *args, payload=None, cwd=None, env=None) -> subprocess.CompletedProcess:
    stdin = payload if isinstance(payload, str) or payload is None else json.dumps(payload)
    return subprocess.run([sys.executable, str(path), *args], input=stdin, capture_output=True, text=True,
                          cwd=cwd, env=dict(os.environ, **(env or {})), timeout=30)


def run_hook(script, mode, payload, cwd, env=None) -> subprocess.CompletedProcess:
    """Run l4-tools-guards/hooks/<script> <mode> with stdin JSON; `cwd` also goes into the payload."""
    if isinstance(payload, dict):
        payload = dict(payload, cwd=str(cwd))
    args = [mode] if mode else []
    return run_script(L4 / 'hooks' / script, *args, payload=payload, cwd=cwd, env=env)

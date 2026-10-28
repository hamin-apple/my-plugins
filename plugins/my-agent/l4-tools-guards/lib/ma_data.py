"""The my-agent data folder and the files inside it (one place decides the order).

Data folder: $MA_TASKS_DIR, else the setting (a script's `--data-dir` argument, or for hooks the environment
variable $CLAUDE_PLUGIN_OPTION_DATA_DIR), else ~/dev/my-agent. `~` is expanded. An empty value or one starting with `${`
(a placeholder that was never substituted) counts as "not set".
Per-file overrides win first: $MA_PROJECTS_FILE, $MA_FEEDBACK_FILE, $MA_GATE_REPORT_DIR.
The run index, monitor state, logs, open settings and price override sit directly in the data folder.
"""
import os
from pathlib import Path

SETTING_ENV = 'CLAUDE_PLUGIN_OPTION_DATA_DIR'


def _value(raw):
    """`raw` stripped, or None when it is empty or an unsubstituted `${...}` placeholder."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    return None if not raw or raw.startswith('${') else raw


def _path(raw: str) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else Path.cwd() / p


def data_dir(arg=None) -> Path:
    raw = _value(os.environ.get('MA_TASKS_DIR')) or _value(arg) or _value(os.environ.get(SETTING_ENV))
    return _path(raw) if raw else Path.home() / 'dev' / 'my-agent'


def projects_file(arg=None) -> Path:
    raw = _value(os.environ.get('MA_PROJECTS_FILE'))
    return _path(raw) if raw else data_dir(arg) / 'projects.txt'


def feedback_file(arg=None) -> Path:
    raw = _value(os.environ.get('MA_FEEDBACK_FILE'))
    return _path(raw) if raw else data_dir(arg) / 'feedback.md'


def report_dir(arg=None) -> Path:
    raw = _value(os.environ.get('MA_GATE_REPORT_DIR'))
    return _path(raw) if raw else data_dir(arg) / 'gate-report'

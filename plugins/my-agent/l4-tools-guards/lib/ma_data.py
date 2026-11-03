"""The my-agent data folder and the files inside it (one place decides the order).

Data folder: $MA_TASKS_DIR, else the setting (a script's `--data-dir` argument, or for hooks the environment
variable $CLAUDE_PLUGIN_OPTION_DATA_DIR), else ~/dev/log/my-agent. `~` is expanded. An empty value or one starting with `${`
(a placeholder that was never substituted) counts as "not set".
Per-file overrides win first: $MA_PROJECTS_FILE, $MA_FEEDBACK_FILE, $MA_GATE_REPORT_DIR.
The run index, monitor state, logs, open settings and price override sit directly in the data folder.

Task subfolder (`task_dir()`): $MA_TASK_DIR (tests), else the setting (a script's `--task-dir` argument, or the
environment variable $CLAUDE_PLUGIN_OPTION_TASK_DIR), else `.my-agent`. $MA_TASK_DIR is not $MA_TASKS_DIR (the data
folder, an older name); the names differ by one letter.
"""
import os
from pathlib import Path

import ma_host

SETTING_ENV = 'CLAUDE_PLUGIN_OPTION_DATA_DIR'
TASK_SETTING_ENV = 'CLAUDE_PLUGIN_OPTION_TASK_DIR'
TASK_DIR_DEFAULT = '.my-agent'


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
    raw = _value(os.environ.get('MA_TASKS_DIR')) or _value(arg) or _value(ma_host.plugin_option(SETTING_ENV))
    return _path(raw) if raw else Path.home() / 'dev' / 'log' / 'my-agent'


def projects_file(arg=None) -> Path:
    raw = _value(os.environ.get('MA_PROJECTS_FILE'))
    return _path(raw) if raw else data_dir(arg) / 'projects.txt'


def feedback_file(arg=None) -> Path:
    raw = _value(os.environ.get('MA_FEEDBACK_FILE'))
    return _path(raw) if raw else data_dir(arg) / 'feedback.md'


def report_dir(arg=None) -> Path:
    raw = _value(os.environ.get('MA_GATE_REPORT_DIR'))
    return _path(raw) if raw else data_dir(arg) / 'gate-report'


def task_dir(arg=None) -> str:
    """The task subfolder (a normalized relative path, case kept). The first set value of $MA_TASK_DIR, `arg`,
    $CLAUDE_PLUGIN_OPTION_TASK_DIR is used; an invalid one (absolute, `~`, a `..` segment, no segment left, first
    segment `.git` or `.claude`) gives the default, never the next source. $MA_TASK_DIR is not $MA_TASKS_DIR."""
    raw = _value(os.environ.get('MA_TASK_DIR')) or _value(arg) or _value(ma_host.plugin_option(TASK_SETTING_ENV))
    if not raw or raw.startswith(('/', '~')):
        return TASK_DIR_DEFAULT
    parts = [p for p in raw.split('/') if p not in ('', '.')]
    if not parts or '..' in parts or parts[0].casefold() in ('.git', '.claude'):
        return TASK_DIR_DEFAULT
    return '/'.join(parts)


def task_root(location, arg=None) -> Path:
    """`location / task_dir(arg)`, not resolved."""
    return Path(location) / task_dir(arg)

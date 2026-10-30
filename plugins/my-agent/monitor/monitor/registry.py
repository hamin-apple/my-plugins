"""projects.txt → task folders; builds task dicts and keeps them until a folder changes (spec 5.1)."""
import os
import threading
from datetime import datetime
from pathlib import Path

from .runlog import read_lines
from .taskview import build_task, task_key
from .transcript import TranscriptCache

import ma_data
import ma_prices
import ma_usage
from ma_prices import load_prices

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ('id', 'key', 'project', 'profile', 'status', 'step', 'title', 'waiting', 'elapsed')


def default_projects_file() -> Path:
    return ma_data.projects_file()


def default_prices_file() -> Path:
    """`prices.json` in the data folder when it exists, else the bundled one (spec 6.1)."""
    return ma_prices.prices_file()


def default_claude_root() -> Path:
    return Path(os.environ.get('MA_CLAUDE_PROJECTS') or Path.home() / '.claude/projects')


def _signature(task_dir: Path):
    newest = 0.0
    for dirpath, dirnames, filenames in os.walk(task_dir):
        for name in dirnames + filenames:
            try:
                newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
            except OSError:
                pass
    return newest


class Registry:
    def __init__(self, projects_file: Path = None, claude_root: Path = None, prices_file: Path = None, clock=datetime.now):
        self.projects_file = Path(projects_file or default_projects_file())
        self.tcache = TranscriptCache(claude_root or default_claude_root())
        self.prices_file = Path(prices_file or default_prices_file())
        self.clock = clock
        self._prices, self._prices_mtime = {}, None
        self._cache = {}   # key -> {sig, task, sessions, started}
        self._lock = threading.Lock()   # server threads share the cache

    def _projects(self):
        try:
            lines = self.projects_file.read_text(encoding='utf-8').splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            p = Path(os.path.expanduser(line))
            if p.is_dir() and p not in out:
                out.append(p)
        return out

    def _task_dirs(self):
        for project in self._projects():
            for intake in sorted((project / 'docs' / 'agent').glob('*/intake.md')):
                yield project, intake.parent

    def _prices_now(self):
        try:
            mt = self.prices_file.stat().st_mtime
        except OSError:
            mt = None
        if mt != self._prices_mtime:
            self._prices, self._prices_mtime = load_prices(self.prices_file), mt
        return self._prices

    def _get(self, project, task_dir):
        """Cached task, rebuilt only when the folder, the transcript size or prices.json changed."""
        key = task_key(project, task_dir.name)
        prices = self._prices_now()
        cached = self._cache.get(key)
        sessions = cached['sessions'] if cached else ()
        sig = (_signature(task_dir), self._prices_mtime, tuple(self.tcache.size(s) for s in sessions))
        if not cached or cached['sig'] != sig:
            now = self.clock()
            task = build_task(project, task_dir, prices, self.tcache, now)
            lines = read_lines(task_dir / 'run-log.md')
            sessions = tuple(sorted({l.f['session'] for l in lines if l.kind == 'step' and l.f.get('session')}))
            if task.get('status') != 'running' and (task_dir / ma_usage.SNAPSHOT).is_file():
                sessions = ()   # read from main-usage.json: the transcript no longer matters
            started = lines[0].ts if lines else datetime.fromtimestamp(_signature(task_dir))
            sig = sig[:2] + (tuple(self.tcache.size(s) for s in sessions),)
            cached = self._cache[key] = {'sig': sig, 'task': task, 'sessions': sessions, 'started': started}
        task = cached['task']
        if task.get('status') == 'running':   # the clock moves without any file changing
            now = self.clock()
            task['now'] = now.strftime('%H:%M')
            task['elapsed'] = round((now - cached['started']).total_seconds() / 60)
        return task

    def _started(self, task):
        c = self._cache.get(task['key'])
        return c['started'] if c else datetime.min

    def list_tasks(self) -> list:
        with self._lock:
            return self._list()

    def get_task(self, key: str):
        with self._lock:
            return self._find(key)

    def _list(self):
        tasks = [self._get(p, d) for p, d in self._task_dirs()]
        keys = {t['key'] for t in tasks}
        for k in set(self._cache) - keys:   # folders that were moved or deleted
            del self._cache[k]
        self.tcache.keep({s for c in self._cache.values() for s in c['sessions']})
        tasks.sort(key=lambda t: (self._started(t), t['id']), reverse=True)
        return [{k: t.get(k) for k in SUMMARY} for t in tasks]

    def _find(self, key):
        for project, task_dir in self._task_dirs():
            if task_key(project, task_dir.name) == key:
                return self._get(project, task_dir)
        return None

"""Main-session token usage from `~/.claude/projects/*/<session>.jsonl` (spec 5.3).

Each file is read once from the start and afterwards only from the stored byte
offset, so a transcript of hundreds of MB costs one full read. Lines are read and
summed with the plugin's `ma_usage`, the same code `usage-snapshot.py` uses.
"""
from pathlib import Path

import ma_usage

KEYS = ma_usage.KEYS


class _File:
    def __init__(self, path):
        self.path, self.offset, self.msgs = path, 0, {}   # message id -> (local ts, model, usage)


class TranscriptCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {}   # session -> _File

    def _find(self, session):
        if session not in self.files:
            hit = ma_usage.find_transcript(self.root, session)
            if hit is None:
                return None
            self.files[session] = _File(hit)
        return self.files[session]

    def keep(self, sessions):
        """Forget every session not in `sessions` (tasks that left the list, or finished ones read from a snapshot)."""
        for s in set(self.files) - set(sessions):
            del self.files[s]

    def size(self, session):
        tf = self._find(session)
        try:
            return tf.path.stat().st_size if tf else None
        except OSError:
            return None

    def _refresh(self, tf):
        try:
            size = tf.path.stat().st_size
        except OSError:
            return
        if size < tf.offset:          # rewritten: start over
            tf.offset, tf.msgs = 0, {}
        if size == tf.offset:
            return
        with open(tf.path, 'rb') as f:
            f.seek(tf.offset)
            data = f.read(size - tf.offset)
        end = data.rfind(b'\n') + 1   # leave a half-written last line for the next read
        tf.offset += end
        for raw in data[:end].splitlines():
            got = ma_usage.parse_entry(raw)
            if got:
                mid, ts, model, usage = got
                tf.msgs[mid or f'@{tf.offset}:{len(tf.msgs)}'] = (ts, model, usage)

    def usage_by_window(self, session, windows) -> dict:
        """{key: {model: usage}} for each (start, end|None, key) window; {} if no transcript."""
        tf = self._find(session)
        if not tf:
            return {}
        self._refresh(tf)
        return ma_usage.sum_windows(tf.msgs.values(), windows)

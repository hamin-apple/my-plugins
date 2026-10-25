"""Main-session token usage from `~/.claude/projects/*/<session>.jsonl` (spec 5.3).

Each file is read once from the start and afterwards only from the stored byte
offset, so a transcript of hundreds of MB costs one full read.
"""
import json
from datetime import datetime
from pathlib import Path

KEYS = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')


class _File:
    def __init__(self, path):
        self.path, self.offset, self.msgs = path, 0, {}   # message id -> (local ts, model, usage)


class TranscriptCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {}   # session -> _File

    def _find(self, session):
        if session not in self.files:
            hits = sorted(self.root.glob(f'*/{session}.jsonl')) if session else []
            if not hits:
                return None
            self.files[session] = _File(hits[0])
        return self.files[session]

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
            try:
                e = json.loads(raw)
                msg = e.get('message') or {}
                if e.get('type') != 'assistant' or not msg.get('usage'):
                    continue
                ts = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')).astimezone().replace(tzinfo=None)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            mid = msg.get('id') or f'@{tf.offset}:{len(tf.msgs)}'
            tf.msgs[mid] = (ts, msg.get('model'), {k: msg['usage'].get(k) or 0 for k in KEYS})

    def usage_by_window(self, session, windows) -> dict:
        """{key: {model: usage}} for each (start, end|None, key) window; {} if no transcript."""
        tf = self._find(session)
        if not tf:
            return {}
        self._refresh(tf)
        out = {}
        for start, end, key in windows:
            for ts, model, usage in tf.msgs.values():
                if ts >= start and (end is None or ts < end):
                    acc = out.setdefault(key, {}).setdefault(model, dict.fromkeys(KEYS, 0))
                    for k in KEYS:
                        acc[k] += usage[k]
        return out

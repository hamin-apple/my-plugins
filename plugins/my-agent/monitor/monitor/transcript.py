"""Main-session token usage from `~/.claude/projects/*/<session>.jsonl` (spec 5.3).

Each file is read once from the start and afterwards only from the stored byte
offset, so a transcript of hundreds of MB costs one full read. Lines are read and
summed with the plugin's `ma_usage`, the same code `usage-snapshot.py` uses.
A session id with no Claude transcript is looked up as a Codex session record (`ma_host.codex_record`, root
$MA_CODEX_SESSIONS or `~/.codex/sessions`); its usage lines are re-read whenever the file grew.
"""
from pathlib import Path

import ma_host
import ma_schema
import ma_usage


class _File:
    def __init__(self, path, codex=False):
        self.path, self.offset, self.msgs = path, 0, {}   # message id -> (local ts, model, usage)
        self.codex = codex       # a Codex record: msgs is rebuilt on growth


class TranscriptCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {}   # session -> _File

    def _find(self, session):
        if session not in self.files:
            hit = ma_usage.find_transcript(self.root, session)
            if hit is not None:
                self.files[session] = _File(hit)
            else:
                hit = ma_host.codex_record(session)
                if hit is None:
                    return None
                self.files[session] = _File(hit, codex=True)
                self.files[session].session = session
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
        if tf.codex:
            if size != tf.offset:
                tf.offset, tf.msgs = size, dict(enumerate(ma_usage.read_codex(tf.path, tf.session)))
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

    def codex_model_family(self, session):
        """The Codex family of the model a Codex session's main thread used (its first response), else None."""
        tf = self._find(session)
        if not tf or not tf.codex:
            return None
        self._refresh(tf)
        for _, model, _ in tf.msgs.values():
            fam = ma_schema.codex_family(model)
            if fam:
                return fam
        return None

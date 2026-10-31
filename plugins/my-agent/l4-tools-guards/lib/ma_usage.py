"""Main-session token usage per step, from the session transcript, and its snapshot in the task folder.

The usage of each assistant response in `<projects>/*/<session>.jsonl` (counted once per response ID) is summed per
model inside each step window: from a `step:` line to the next `step:` line; the last window of a finished task ends
1 second after the last run-log line (monitor design 5.3). Claude Code deletes transcripts after `cleanupPeriodDays`
(default 30 days), so at the end of a task L1 runs `usage-snapshot.py`, which writes the same sums to
`<task>/main-usage.json` (architecture 4.8.2 "Task records over time"). The monitor reads that file for a finished task.
The monitor also uses `parse_entry` and `windows` here, so both count the same way.
`write_snapshot` returns a message with the cost from `ma_prices` (the same table and override as the monitor); the
scripts print it.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import ma_prices
import ma_schema

KEYS = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
SNAPSHOT = 'main-usage.json'


def parse_entry(raw):
    """(message id or None, local naive time, model, usage) of an assistant transcript line with usage, else None."""
    try:
        e = json.loads(raw)
        msg = e.get('message') or {}
        if e.get('type') != 'assistant' or not msg.get('usage'):
            return None
        ts = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00')).astimezone().replace(tzinfo=None)
        usage = {k: msg['usage'].get(k) or 0 for k in KEYS}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return msg.get('id'), ts, msg.get('model'), usage


def step_enter(lines) -> list:
    """(time, step, rev, session) per `step:` line; `lines` are (datetime, kind, fields). rev carries forward."""
    out, rev = [], 0
    for ts, kind, f in lines:
        if kind != 'step':
            continue
        try:
            n = int(f.get('n'))
        except (TypeError, ValueError):
            continue
        try:
            rev = int(f['rev'])
        except (KeyError, TypeError, ValueError):
            pass
        out.append((ts, n, rev, f.get('session')))
    return out


def windows(enter, last, running) -> list:
    """(session, start, end or None, (rev, step)) per step entry; a finished task's last window ends at last + 1 s."""
    out = []
    for i, (ts, n, rev, sess) in enumerate(enter):
        if i + 1 < len(enter):
            end = enter[i + 1][0]
        else:
            end = None if running or last is None else last + timedelta(seconds=1)
        out.append((sess, ts, end, (rev, n)))
    return out


def sum_windows(msgs, wins) -> dict:
    """{key: {model: usage}} of the (ts, model, usage) values in `msgs` that fall in each (start, end, key) window."""
    out = {}
    for start, end, key in wins:
        for ts, model, usage in msgs:
            if ts >= start and (end is None or ts < end):
                acc = out.setdefault(key, {}).setdefault(model, dict.fromkeys(KEYS, 0))
                for k in KEYS:
                    acc[k] += usage[k]
    return out


def find_transcript(root: Path, session):
    hits = sorted(Path(root).glob(f'*/{session}.jsonl')) if session else []
    return hits[0] if hits else None


def read_transcript(path: Path) -> list:
    """(ts, model, usage) per response of a whole transcript, the last line of a response ID winning."""
    msgs = {}
    with open(path, 'rb') as fh:
        for i, raw in enumerate(fh):
            got = parse_entry(raw)
            if got:
                mid, ts, model, usage = got
                msgs[mid or f'@{i}'] = (ts, model, usage)
    return list(msgs.values())


def read_log(log: Path) -> list:
    """(datetime, kind, fields) of every readable run-log line; [] when the file is missing."""
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parsed = ma_schema.split_line(line)
        if parsed:
            try:
                out.append((datetime.strptime(parsed[0], '%Y-%m-%d %H:%M:%S'), parsed[1], parsed[2]))
            except ValueError:
                pass
    return out


def measure(task_dir: Path, root: Path):
    """(sessions, missing sessions, {(rev, step): {model: usage}}) of a task treated as finished."""
    lines = read_log(Path(task_dir) / 'run-log.md')
    enter = step_enter(lines)
    wins = windows(enter, lines[-1][0] if lines else None, running=False)
    sessions = sorted({w[0] for w in wins if w[0]})
    missing, out = [], {}
    for sess in sessions:
        path = find_transcript(root, sess)
        if path is None:
            missing.append(sess)
            continue
        got = sum_windows(read_transcript(path), [(s, e, k) for ss, s, e, k in wins if ss == sess])
        for key, models in got.items():
            for model, usage in models.items():
                acc = out.setdefault(key, {}).setdefault(model, dict.fromkeys(KEYS, 0))
                for k in KEYS:
                    acc[k] += usage[k]
    return sessions, missing, out


def to_json(sessions, usage, now: datetime) -> dict:
    rows = [{'rev': rev, 'step': n, 'model': model, 'usage': u}
            for (rev, n), models in sorted(usage.items()) for model, u in sorted(models.items(), key=lambda x: str(x[0]))]
    return {'written': now.strftime('%Y-%m-%d %H:%M:%S'), 'sessions': sessions, 'windows': rows}


def read_snapshot(task_dir: Path):
    """{(rev, step): {model: usage}} from `<task>/main-usage.json`, or None when it is missing or unreadable."""
    try:
        data = json.loads((Path(task_dir) / SNAPSHOT).read_text(encoding='utf-8'))
        out = {}
        for row in data['windows']:
            usage = {k: int(row['usage'].get(k) or 0) for k in KEYS}
            out.setdefault((int(row['rev']), int(row['step'])), {})[row.get('model')] = usage
        return out
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def write_snapshot(task_dir: Path, root: Path, now: datetime, prices=None):
    """(0, message) after writing `<task>/main-usage.json`, or (3, cause) when nothing was written.

    `prices` is a `models` table; None loads the shared one (bundled, or the data folder override)."""
    task_dir = Path(task_dir)
    sessions, missing, usage = measure(task_dir, root)
    target = task_dir / SNAPSHOT
    if not sessions:
        return 3, f'{task_dir / "run-log.md"} has no step line with a session; nothing written'
    if missing:
        return 3, f'no transcript for session {", ".join(missing)}; nothing written'
    data = to_json(sessions, usage, now)
    try:
        target.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
    except OSError as exc:
        return 3, f'cannot write {target}: {exc}'
    if prices is None:
        prices = ma_prices.load_prices(ma_prices.prices_file())
    costs = [ma_prices.cost(prices, w['model'], w['usage']) for w in data['windows']]
    costs = [c for c in costs if c is not None]
    shown = f', ≈ ${round(sum(costs), 2):.2f}' if costs else ''
    return 0, f'saved: {target} ({len(data["windows"])} rows{shown})'

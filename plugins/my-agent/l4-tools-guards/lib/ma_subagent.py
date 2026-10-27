"""Subagent `stop:` lines: transcript sums, the line's fields, and the sweep for agents that end without
SubagentStop (architecture 4.7.2).

An agent that ends at maxTurns gets no SubagentStop (probe r4/r7). Its meta file
`<claude projects>/<project>/<session>/subagents/agent-<id>.meta.json` then says `"finished": true` and
its last assistant entry has a `stop_reason` other than `end_turn`. `sweep` writes the missing `stop:`
line with `end=partial`; run-log.py and subagent-log.py start/stop call it.
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ma_logline
import ma_schema
from ma_schema import family

RESULT_MAX = 80


def claude_projects() -> Path:
    return Path(os.environ.get('MA_CLAUDE_PROJECTS') or Path.home() / '.claude/projects')


RESUME_SLACK = 2   # seconds: run-log times are whole local seconds


def run_since(log, agent_id):
    """UTC time a resumed run began: its latest `start:` line, less RESUME_SLACK; None without one."""
    stamp = None
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    for line in text.splitlines():
        parsed = ma_logline.parse_line(line)
        if parsed and parsed[0] == 'start' and parsed[1].get('id') == agent_id:
            stamp = line[:19]
    if stamp is None:
        return None
    local = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S').astimezone()
    return (local - timedelta(seconds=RESUME_SLACK)).astimezone(timezone.utc)


def _entries(path, since=None):
    """Parsed transcript entries; with `since`, only those stamped at or after it (a resumed agent appends its
    next run to the same file, F33)."""
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue   # a line still being written
            if not isinstance(e, dict):
                continue
            if since is not None:
                try:
                    if datetime.fromisoformat(str(e.get('timestamp')).replace('Z', '+00:00')) < since:
                        continue
                except ValueError:
                    continue
            out.append(e)
    return out


def unit_of(path) -> str:
    """The work unit (`u1`) named on a `작업 단위:` line of the run's first prompt, or None (4.8.2)."""
    for e in _entries(path):
        msg = e.get('message') if e.get('type') == 'user' else None
        if not isinstance(msg, dict):
            continue
        content = msg.get('content')
        if isinstance(content, list):
            content = ' '.join(c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text')
        return ma_schema.unit_of_prompt(content if isinstance(content, str) else '')
    return None


def handback_message(path, since=None) -> str:
    """The `message` of the last SubagentHandback tool call in the run, or ''. A subagent may end with that
    call instead of a final text reply, and then SubagentStop's `last_assistant_message` is empty (F30)."""
    found = ''
    for e in _entries(path, since):
        msg = e.get('message')
        for c in msg.get('content') or [] if isinstance(msg, dict) else []:
            if isinstance(c, dict) and c.get('type') == 'tool_use' and c.get('name') == 'SubagentHandback':
                found = str((c.get('input') or {}).get('message') or '')
    return found


def read_transcript(path, since=None):
    """(usage sums, Counter of models, seconds, last assistant entry) from a subagent transcript (from `since`)."""
    by_id, order, models, stamps, last = {}, [], Counter(), [], None
    for e in _entries(path, since):
        ts = e.get('timestamp')
        if isinstance(ts, str):
            try:
                stamps.append(datetime.fromisoformat(ts.replace('Z', '+00:00')))
            except ValueError:
                pass
        msg = e.get('message') if e.get('type') == 'assistant' else None
        if not isinstance(msg, dict):
            continue
        last = e
        mid = msg.get('id') or f'_{len(order)}'
        if mid not in by_id:
            order.append(mid)
        by_id[mid] = msg   # the last entry for a message id wins
    sums = {'in': 0, 'out': 0, 'cw': 0, 'cr': 0}
    for mid in order:
        msg = by_id[mid]
        u = msg.get('usage') or {}
        sums['in'] += int(u.get('input_tokens') or 0)
        sums['out'] += int(u.get('output_tokens') or 0)
        sums['cw'] += int(u.get('cache_creation_input_tokens') or 0)
        sums['cr'] += int(u.get('cache_read_input_tokens') or 0)
        model = msg.get('model')
        if isinstance(model, str) and model != '<synthetic>':
            models[model] += 1
    secs = int((max(stamps) - min(stamps)).total_seconds()) if stamps else None
    return sums, models, secs, last


def first_line(text):
    result = next((l.strip() for l in (text or '').splitlines() if l.strip()), None)
    if result and len(result) > RESULT_MAX:
        result = result[:RESULT_MAX - 1] + '…'
    return result


def runs(lines, agent_id) -> tuple:
    """(start: lines, stop: lines) for one agent id; SendMessage resumes an agent under the same id."""
    count = lambda kind: sum(1 for k, f in lines if k == kind and f.get('id') == agent_id)
    return count('start'), count('stop')


def stop_line(lines, agent_id, sums, actual, secs, result, end, mode=None, effort=None, unit=None) -> str:
    fields = [('id', agent_id)] + ([('unit', unit)] if unit else []) + [('actual', actual)]
    if sums is None:
        fields += [('tokens', None), ('in', None), ('out', None), ('cw', None), ('cr', None)]
    else:
        fields += [('tokens', sum(sums.values()))] + [(k, sums[k]) for k in ('in', 'out', 'cw', 'cr')]
    fields += [('secs', secs), ('result', result), ('end', end), ('mode', mode), ('effort', effort)]
    starts = [f for k, f in lines if k == 'start' and f.get('id') == agent_id]
    configured = starts[-1].get('configured') if starts else None
    if family(configured) and family(actual) and family(configured) != family(actual):
        fields.append(('mismatch', 1))
    return ma_logline.format_line('stop', fields)


def main_model(session, tail=4 << 20):
    """The model of the last main-chain assistant message in the session transcript, or None.

    The skill's `model:` holds for the invoking turn only (F13), so L1 cannot name its own model reliably."""
    if not session:
        return None
    path = next(iter(sorted(claude_projects().glob(f'*/{session}.jsonl'))), None)
    if path is None:
        return None
    with open(path, 'rb') as fh:
        fh.seek(max(0, path.stat().st_size - tail))
        rows = fh.read().decode('utf-8', 'replace').splitlines()
    for row in reversed(rows):
        try:
            d = json.loads(row)
        except ValueError:
            continue
        model = (d.get('message') or {}).get('model') if isinstance(d, dict) else None
        if d.get('type') == 'assistant' and not d.get('isSidechain') and family(model):
            return model
    return None


def find_meta(agent_id, session):
    root = claude_projects()
    pattern = f"*/{session}/subagents/agent-{agent_id}.meta.json" if session else f"*/*/subagents/agent-{agent_id}.meta.json"
    return next(iter(sorted(root.glob(pattern))), None)


def sweep(active) -> list:
    """Write `stop: … end=partial` for each open start whose agent finished without a final reply.
    Returns [(agent, id, unit)] for the lines written (unit None when the prompt named none)."""
    lines = ma_logline.read(active.log)
    closed = []
    for kind, f in lines:
        agent_id = f.get('id')
        if kind != 'start' or not agent_id:
            continue
        if runs(lines, agent_id)[1]:
            continue   # stopped once: a resumed run's meta still says finished, so only SubagentStop closes it
        meta_path = find_meta(agent_id, f.get('session'))   # no session= (older lines): every session
        if meta_path is None:
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            if not (isinstance(meta, dict) and meta.get('finished') is True):
                continue
            sums, models, secs, last = read_transcript(meta_path.with_name(f'agent-{agent_id}.jsonl'))
        except (OSError, ValueError) as exc:
            ma_logline.log_error(active, 'sweep', exc)
            continue
        msg = (last or {}).get('message') or {}
        if msg.get('stop_reason') == 'end_turn':
            continue   # a normal end: SubagentStop writes that line
        text = ' '.join(c.get('text', '') for c in msg.get('content') or [] if isinstance(c, dict) and c.get('type') == 'text')
        actual = models.most_common(1)[0][0] if models else None
        try:
            unit = unit_of(meta_path.with_name(f'agent-{agent_id}.jsonl'))
        except OSError:
            unit = None   # the stop line matters more than its unit
        line = stop_line(lines, agent_id, sums, actual, secs, first_line(text), ma_schema.END_PARTIAL,
                         effort=(last or {}).get('effort'), unit=unit)
        ma_logline.append(active.log, line)
        lines.append(('stop', {'id': agent_id}))
        closed.append((f.get('agent'), agent_id, unit))
    return closed

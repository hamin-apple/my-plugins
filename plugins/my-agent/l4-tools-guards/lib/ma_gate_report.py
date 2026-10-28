"""Gate decision tally and the report copy folder (architecture 4.11, "retrospective").

`tally_text` only counts what the active task's run-log says: the ask/answer decision table, a few counters and
the cost/tokens per stretch between `cost:` lines. It does not interpret anything (the gate-analyst does).
`report_dir` is the folder `gate-report.py copy` writes to; plan-approved-check lets writes there pass unasked.
"""
import re
from pathlib import Path

import ma_data
import ma_logline
import ma_schema

NO_REC = '(not recorded)'
SCOPE_CHANGE = 'Scope change:'   # a `fix` line that records an in-scope adjustment (B3), not a fix
NOTE_BY_L1 = 'answered by L1'
RECOMMENDED = re.compile(r'\s*\(recommended\)\s*$', re.I)


def report_dir(data_dir=None) -> Path:
    """$MA_GATE_REPORT_DIR, else <data folder>/gate-report (like $MA_FEEDBACK_FILE)."""
    return ma_data.report_dir(data_dir)


def read_stamped(log) -> list:
    """(HH:MM, kind, fields) of every readable run-log line; [] when the file is missing."""
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parsed = ma_logline.parse_line(line)
        if parsed:
            out.append((line.strip()[11:16], parsed[0], parsed[1]))
    return out


def _cell(text) -> str:
    return str(text).replace('|', '\\|').replace('\n', ' ')


def _bare(label):
    """The label without a trailing ' (Recommended)' (old logs have it on choice/rec)."""
    return RECOMMENDED.sub('', label) if isinstance(label, str) else label


def decisions(lines) -> list:
    """Rows [gate, question, rec, choice, picked, note] from the L1 ask/answer lines, paired per gate in order.

    An ask without an answer, an answer without an ask and a second answer to one ask are all kept, with a note."""
    rows, pending, last_ask, after_answer = [], {}, {}, {}
    for _, kind, f in lines:
        if kind not in ('ask', 'answer') or ma_logline.is_hook_line(kind, f):
            continue
        gate = f.get('gate') or '?'
        if kind == 'ask':
            rec = _bare(f.get('rec'))
            shown = NO_REC if rec is None else ('none' if rec == '-' else rec)
            row = [gate, f.get('q', '-'), shown, '-', 'unknown', 'no answer']
            rows.append(row)
            pending[gate], last_ask[gate], after_answer[gate] = (row, rec), (row[1], shown, rec), False
            continue
        choice = _bare(f.get('choice', '-'))
        if gate in pending:
            row, rec = pending.pop(gate)
            note = ''
        else:
            twice = after_answer.get(gate) and gate in last_ask
            q, shown, rec = last_ask[gate] if twice else ('-', NO_REC, None)
            note = 'answered twice' if twice else 'answer only'
            row = [gate, q, shown, '-', 'unknown', note]
            rows.append(row)
        if f.get('by') == ma_schema.ANSWERED_BY_L1:
            note = f'{note}; {NOTE_BY_L1}' if note else NOTE_BY_L1
        row[3], row[5] = choice, note
        if f.get('other') == '1':
            row[4] = 'typed (Other)'
        elif rec not in (None, '-'):
            row[4] = 'yes' if choice == rec else 'no'
        after_answer[gate] = True
    return rows


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _segments(lines) -> list:
    """Stretches between `cost:` lines: [start, end, step names, usd or None, tokens].

    The cost of a stretch is the gain of the cost line that ends it over the previous cost line of the same
    session (a drop is a reset); the stretch after the last cost line has none."""
    cuts = [i for i, (_, k, _) in enumerate(lines) if k == 'cost']
    prev, segs = {}, []
    for n in range(len(cuts) + 1):
        lo = cuts[n - 1] if n else 0
        hi = cuts[n] if n < len(cuts) else len(lines) - 1
        body = lines[lo:hi + 1]
        usd = None
        if n < len(cuts):
            f = lines[hi][2]
            try:
                now = float(f.get('usd'))
            except (TypeError, ValueError):
                now = None
            before = prev.get(f.get('session'))
            if now is not None:
                if before is not None:
                    usd = now - before if now >= before else now
                prev[f.get('session')] = now
        steps = [f"{f.get('n', '?')} {f.get('name', '?')}" for _, k, f in body if k == 'step']
        tokens = sum(_int(f.get('tokens')) for _, k, f in body if k == 'stop')
        if steps or tokens or usd is not None:
            segs.append([lines[lo][0], lines[hi][0] if n < len(cuts) else '', steps, usd, tokens])
    return segs


def tally_text(lines) -> str:
    """The "Decision table", "Metrics" and "Cost and tokens per stretch" sections for a run-log's stamped lines."""
    out = ['## Decision table']
    rows = decisions(lines)
    if rows:
        out += ['| # | Gate | Question | Recommended | Choice | Picked recommended | Note |', '|---|---|---|---|---|---|---|']
        out += [(f'| {i} | ' + ' | '.join(_cell(c) for c in r) + ' |').replace(' |  |', ' | |')
                for i, r in enumerate(rows, 1)]
    else:
        out.append('No decisions (no ask/answer lines)')
    kinds = [(k, f) for _, k, f in lines]
    count = lambda kind, **want: sum(1 for k, f in kinds if k == kind and all(f.get(a) == b for a, b in want.items()))  # noqa: E731
    main = sum(1 for k, f in kinds if k == 'step' and f.get('model') not in (None, '-')
               and ma_schema.family(f.get('model')) != 'opus')
    sub = count('stop', mismatch='1')
    opus = sum(1 for k, f in kinds if k == 'call' and 'opus' in (f.get('model') or ''))
    scope = sum(1 for k, f in kinds if k == 'fix' and (f.get('what') or '').startswith(SCOPE_CHANGE))
    plan_edits = sum(1 for k, f in kinds if k == 'fix' and f.get('before') == ma_schema.PLAN_EDIT_GATE)
    fixes = count('fix') - scope - plan_edits
    delegated = sum(1 for k, f in kinds if k == 'answer' and f.get('by') == ma_schema.ANSWERED_BY_L1)
    switches = [f'{t} {f.get("state")} ({f.get("how", "-")})' for t, k, f in lines if k == 'delegate']
    profiles = [f'{f.get("from")} → {f.get("to")}' for _, k, f in lines if k == 'profile']
    drafts = sum(1 for k, f in kinds if k == 'revision' and f.get('before'))
    revs = len({f.get('rev') for k, f in kinds if k == 'revision' and not f.get('before') and f.get('rev')})
    out += ['', '## Metrics', '| Item | Value |', '|---|---|',
            f"| Verify runs | {count('step', name='Verify')} |",
            f"| Plan Review runs | {count('step', name='Plan-Review')} |",
            f"| Subagents | {count('start')} |",
            f'| Model mismatches | {main + sub} (main session {main} · by step lines, subagents {sub}) |',
            f'| L1 small fixes | {fixes} |',
            f'| Adjustments within the approved scope | {scope} |',
            f'| Plan rewrites before approval | {drafts} |',
            f'| In-flight revisions | {revs} |',
            f'| Calls raised to opus | {opus} (retries and explicit calls are not told apart) |',
            *([f'| Plan edits by L1 before approval | {plan_edits} |'] if plan_edits else []),
            *([f'| Delegated answers | {delegated} |'] if delegated else []),
            *([f"| Delegated approval | {', '.join(switches)} |"] if switches else []),
            *([f"| Profile changes | {len(profiles)} ({', '.join(profiles)}) |"] if profiles else []),
            '', '## Cost and tokens per stretch']
    segs = _segments(lines)
    if segs:
        out += ['| Stretch | Steps | Cost USD (approx.) | Subagent tokens |', '|---|---|---|---|']
        for start, end, names, usd, tokens in segs:
            cost = 'not recorded' if usd is None else f'{usd:.2f}'
            out.append(f"| {start}–{end} | {', '.join(names) or '-'} | {cost} | {tokens:,} |")
    else:
        out.append('Not recorded')
    return '\n'.join(out)


def counts(lines) -> tuple:
    """(L1 lines, hook lines, G2 lines) of a run-log."""
    g2 = sum(1 for _, k, f in lines if k in ('ask', 'answer') and f.get('gate') == 'G2')
    hook = sum(1 for _, k, f in lines if ma_logline.is_hook_line(k, f))
    return len(lines) - hook, hook - g2, g2


def free_name(folder: Path, task: str) -> Path:
    """`<task>.md` in folder, or `<task>-2.md`, `<task>-3.md` … when taken."""
    dest, n = folder / f'{task}.md', 2
    while dest.exists():
        dest = folder / f'{task}-{n}.md'
        n += 1
    return dest

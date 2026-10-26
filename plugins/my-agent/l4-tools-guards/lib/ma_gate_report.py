"""Gate decision tally and the report copy folder (architecture 4.11, "회고").

`tally_text` only counts what the active task's run-log says: the ask/answer decision table, a few counters and
the cost/tokens per stretch between `cost:` lines. It does not interpret anything (the gate-analyst does).
`report_dir` is the folder `gate-report.py copy` writes to; plan-approved-check lets writes there pass unasked.
"""
import os
import re
from pathlib import Path

import ma_logline

DEFAULT_REPORT_DIR = Path.home() / 'dev/skills/my-surrogate/gate-report'
NO_REC = '(기록 없음)'
RECOMMENDED = re.compile(r'\s*\(recommended\)\s*$', re.I)
FAMILY = re.compile(r'(opus|sonnet|haiku|fable)')


def report_dir() -> Path:
    """$MA_GATE_REPORT_DIR, else ~/dev/skills/my-surrogate/gate-report (like $MA_FEEDBACK_FILE)."""
    return Path(os.environ.get('MA_GATE_REPORT_DIR') or DEFAULT_REPORT_DIR).expanduser()


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
            shown = NO_REC if rec is None else ('없음' if rec == '-' else rec)
            row = [gate, f.get('q', '-'), shown, '-', '알 수 없음', '답 없음']
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
            note = '답 두 번' if twice else '답만 있음'
            row = [gate, q, shown, '-', '알 수 없음', note]
            rows.append(row)
        row[3], row[5] = choice, note
        if f.get('other') == '1':
            row[4] = '직접 입력'
        elif rec not in (None, '-'):
            row[4] = '예' if choice == rec else '아니오'
        after_answer[gate] = True
    return rows


def _model_family(model):
    m = FAMILY.search(model or '')
    return m.group(1) if m else None


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
    """The "결정 표", "지표" and "단계별 비용·토큰" sections for a run-log's stamped lines."""
    out = ['## 결정 표']
    rows = decisions(lines)
    if rows:
        out += ['| # | 게이트 | 질문 | 권장안 | 고른 선택지 | 권장안 선택 | 비고 |', '|---|---|---|---|---|---|---|']
        out += [(f'| {i} | ' + ' | '.join(_cell(c) for c in r) + ' |').replace(' |  |', ' | |')
                for i, r in enumerate(rows, 1)]
    else:
        out.append('결정 없음 (ask/answer 줄이 없습니다)')
    kinds = [(k, f) for _, k, f in lines]
    count = lambda kind, **want: sum(1 for k, f in kinds if k == kind and all(f.get(a) == b for a, b in want.items()))  # noqa: E731
    main = sum(1 for k, f in kinds if k == 'step' and f.get('model') not in (None, '-')
               and _model_family(f.get('model')) != 'opus')
    sub = count('stop', mismatch='1')
    opus = sum(1 for k, f in kinds if k == 'call' and 'opus' in (f.get('model') or ''))
    out += ['', '## 지표', '| 항목 | 값 |', '|---|---|',
            f"| Verify 횟수 | {count('step', name='Verify')} |",
            f"| Plan Review 횟수 | {count('step', name='Plan-Review')} |",
            f"| 서브에이전트 수 | {count('start')} |",
            f'| 모델 불일치 수 | {main + sub} (주 세션 {main} · step 줄 기준, 서브에이전트 {sub}) |',
            f"| L1 작은 수정 수 | {count('fix')} |",
            f'| opus로 올린 호출 수 | {opus} (재시도와 명시 호출을 구별하지 않음) |',
            '', '## 단계별 비용·토큰']
    segs = _segments(lines)
    if segs:
        out += ['| 구간 | 단계 | 비용 USD (근사) | 서브에이전트 토큰 |', '|---|---|---|---|']
        for start, end, names, usd, tokens in segs:
            cost = '기록 없음' if usd is None else f'{usd:.2f}'
            out.append(f"| {start}–{end} | {', '.join(names) or '-'} | {cost} | {tokens:,} |")
    else:
        out.append('기록 없음')
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

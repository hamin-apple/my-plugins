#!/usr/bin/env python3
"""Append one L1 Recorder line to the active task's run-log.md (architecture 4.7.2).

usage: run-log.py <kind> [key=value ...] [--model MODEL_ID] [--cwd DIR] [--data-dir DIR] [--task-dir DIR]

The time comes from the clock. `step` needs n= and name=; rev= (latest revision:
line, else 0) and session= ($CLAUDE_CODE_SESSION_ID or Codex's $CODEX_THREAD_ID, else .active) are filled in.
On step lines (and any line given --model), model= is the model of the session
transcript's last main-chain reply (F13: the skill's `model:` holds for one
turn), else --model; it is checked against the configured main model (opus, P9; the Codex default for a Codex model id)
and a main-session MISMATCH is printed once per task and model.
`ask` and `answer` lines get session= the same way. `cost` takes no value from the command line (usd= or
session= is refused): it reads `cost_usd` from the statusline file `<session>.json` in $MA_STATUSLINE_DIR (default
~/.cache/claude-sessions/statusline), session from .active first, else $CLAUDE_CODE_SESSION_ID. A missing or
unreadable file prints `run-log: no cost line (<reason>)` and writes nothing (exit 0); a value below the previous
`cost:` line of that session gets reset=1. `cost` also refuses baseline=.
`inline` records a role that ran in the main session (the inline pass of agent-models.py): agent=my-agent:<role> of the nine
roles and file= (the result file, or `-` for my-agent:coder) are needed, unit= is optional (`-`). result= is the first line of
the file (cut to 200 characters); for `file=-` (coder only) it is given as result=, and for every other role it is refused. A missing
result file prints `run-log: inline needs the result file <path> (missing)`, exit 1, nothing written. Fields: agent unit file
result model (--model gives model=).
After the `step` line with n=1 the script writes a second line `cost: session=<sid> usd=<value> baseline=1` (the
baseline the tally measures the Intake stretch against), when the statusline file gives a value (same lookup as `cost`)
and the run-log has no `cost:` line yet; otherwise it writes and prints nothing extra. Other `step` lines never do.
`ask` takes no prose=, other= or pre= (they belong on the `answer` line): one line on stderr, exit 1, nothing written.
Prints the line, then one MISMATCH line per subagent stop: line with
mismatch=1 written since the previous L1 line, and PARTIAL lines (with unit=)
for workers the sweep closed. Unreadable record lines are named on stderr.
--data-dir is the data folder, where the run index (active-index.json) is read for a run folder
outside git. --task-dir is the task subfolder (setting `task_dir`, default .my-agent): the records are in
<task location>/<task_dir>/. Exit 0 written, 1 no active task (or an `ask` with prose=/other=/pre=, the one
argument error that exits 1), 2 bad arguments.
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_data  # noqa: E402
import ma_gate_report  # noqa: E402
import ma_host  # noqa: E402
import ma_logline  # noqa: E402
import ma_prices  # noqa: E402
import ma_schema  # noqa: E402
import ma_subagent  # noqa: E402
import ma_usage  # noqa: E402

KINDS = ('step', 'ask', 'answer', 'revision', 'cost', 'stale', 'base', 'abort', 'deliver', 'resume',
         'rules-changed', 'merge', 'fix', 'delegate', 'profile', 'models', 'inline')
RESULT_CHARS = 200   # longest `result=` an inline line takes from its result file


def statusline_cost(session):
    """(cost_usd, None) from the session's statusline file, else (None, reason)."""
    if not session or re.search(r'[/\\\0]', session) or session in ('.', '..'):
        return None, 'no session id'
    base = os.environ.get('MA_STATUSLINE_DIR') or os.path.expanduser('~/.cache/claude-sessions/statusline')
    path = Path(base) / f'{session}.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None, f'{path} is missing'
    except (OSError, ValueError) as exc:
        return None, f'{path} is unreadable: {type(exc).__name__}'
    value = data.get('cost_usd') if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None, f'{path} has no cost_usd number'
    return value, None


def session_cost(session, data_dir):
    """(cost_usd, None) or (None, reason): a Claude session's statusline value; for a session with a Codex
    record (and no statusline file) tokens times list prices."""
    usd, why = statusline_cost(session)
    if why and ma_host.codex_record(session):
        return ma_usage.codex_cost(session, ma_prices.load_prices(ma_prices.prices_file(data_dir)))
    return usd, why


def subagent_mismatches(lines) -> list:
    """MISMATCH lines for stop: lines with mismatch=1 after the last L1 line."""
    last_l1 = max((i for i, (k, f) in enumerate(lines) if not ma_logline.is_hook_line(k, f)), default=-1)
    starts = {f.get('id'): f for k, f in lines if k == 'start'}
    out = []
    for kind, f in lines[last_l1 + 1:]:
        if kind == 'stop' and f.get('mismatch') == '1':
            s = starts.get(f.get('id'), {})
            out.append(f"MISMATCH: {s.get('agent', '?')} configured {s.get('configured', '?')}, actual {f.get('actual', '?')}")
    return out


def inline_fields(fields, given, cwd):
    """The ordered fields of an `inline` line, or the exit code (message printed) when the arguments are refused."""
    role = (given.get('agent') or '').partition(':')[2]
    if not given.get('agent', '').startswith('my-agent:') or role not in ma_schema.AGENTS or 'file' not in given:
        print('run-log: inline needs agent=my-agent:<role> (one of the nine roles) and file=', file=sys.stderr)
        return 2
    extra = {k for k, _ in fields} - {'agent', 'unit', 'file', 'result'}
    if extra:
        print(f"run-log: inline takes agent=, unit=, file= and result=, not {', '.join(sorted(extra))}=", file=sys.stderr)
        return 2
    path = given['file']
    if role == 'coder' and path == '-':
        if not given.get('result'):
            print('run-log: inline for my-agent:coder with file=- needs result= (the first line of its report)', file=sys.stderr)
            return 2
        result = given['result']
    elif path == '-' or 'result' in given:
        print('run-log: inline takes file=- and result= for my-agent:coder only; other roles give the result file', file=sys.stderr)
        return 2
    else:
        full = Path(path) if os.path.isabs(path) else Path(cwd) / path
        try:
            text = full.read_text(encoding='utf-8', errors='replace')
        except OSError:
            print(f'run-log: inline needs the result file {path} (missing)')
            return 1
        result = (text.splitlines() or [''])[0].strip()[:RESULT_CHARS] or '-'
    return [('agent', given['agent']), ('unit', given.get('unit') or '-'), ('file', path), ('result', result)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('kind')
    ap.add_argument('fields', nargs='*', metavar='key=value')
    ap.add_argument('--model')
    ap.add_argument('--cwd', default=os.getcwd())
    ap.add_argument('--data-dir', help='the my-agent data folder (default: the setting, else ~/dev/log/my-agent)')
    ap.add_argument('--task-dir', help='the task subfolder, setting `task_dir` (default: the setting, else .my-agent)')
    args = ap.parse_args(argv)
    if args.kind not in KINDS:
        print(f"run-log: unknown kind {args.kind!r}; one of: {' '.join(KINDS)}", file=sys.stderr)
        return 2
    fields = []
    for item in args.fields:
        key, sep, value = item.partition('=')
        if not sep or not re.fullmatch(r'[a-z][a-z0-9_-]*', key):
            print(f'run-log: {item!r} is not key=value', file=sys.stderr)
            return 2
        fields.append((key, value))
    keys = {k for k, _ in fields}
    if args.kind == 'step' and not {'n', 'name'} <= keys:
        print('run-log: step needs n= and name=', file=sys.stderr)
        return 2
    fields_d = dict(fields)
    if args.kind == 'cost' and keys & {'usd', 'session', ma_gate_report.BASELINE}:
        print('run-log: cost takes no usd=, session= or baseline=; it reads the statusline file', file=sys.stderr)
        return 2
    if args.kind == 'ask' and keys & {'prose', 'other', 'pre'}:
        got = ' '.join(f'{k}={v}' for k, v in fields if k in ('prose', 'other', 'pre'))
        print(f'run-log: prose=, other= and pre= go on the answer line, not on ask (got {got})', file=sys.stderr)
        return 1
    if args.kind == 'delegate' and fields_d.get('state') not in ma_schema.DELEGATE_STATES:
        print('run-log: delegate needs state=on|off', file=sys.stderr)
        return 2
    if args.kind == 'profile' and not {'from', 'to'} <= keys:
        print('run-log: profile needs from= and to=', file=sys.stderr)
        return 2
    if args.kind == 'models' and not {'preset', 'source'} <= keys:
        print('run-log: models needs preset= and source=', file=sys.stderr)
        return 2
    if args.kind == 'inline':
        code = inline_fields(fields, fields_d, args.cwd)
        if isinstance(code, int):
            return code
        fields = code
    active = ma_active.find_active(args.cwd, ma_data.data_dir(args.data_dir), sub=args.task_dir)
    if active is None:
        print(f'run-log: no active my-agent task under {args.cwd}')
        return 1
    try:
        partial = ma_subagent.sweep(active)
    except Exception as exc:   # the sweep never blocks an L1 record
        ma_logline.log_error(active, 'run-log sweep', exc)
        partial = []
    lines = ma_logline.read(active.log)
    if args.kind == 'step':
        if 'rev' not in keys:
            revs = [f.get('rev') for k, f in lines if k == 'revision' and f.get('rev')]
            fields.append(('rev', revs[-1] if revs else '0'))
        if 'session' not in keys:
            fields.append(('session', ma_host.session_id() or active.session or None))
    if args.kind in ('ask', 'answer') and 'session' not in keys:
        sid = ma_host.session_id() or active.session
        if sid:
            fields.append(('session', sid))
    if args.kind == 'cost':
        sid = active.session or ma_host.session_id()
        usd, why = session_cost(sid, args.data_dir)
        if why:
            print(f'run-log: no cost line ({why})')
            return 0
        prev = [f.get('usd') for k, f in lines if k == 'cost' and f.get('session') == sid]
        try:
            lower = bool(prev) and usd < float(prev[-1])
        except (TypeError, ValueError):
            lower = False
        fields += [('session', sid), ('usd', usd)] + ([('reset', '1')] if lower else [])
    session = dict(fields).get('session') or ma_host.session_id() or active.session
    try:
        model = (ma_subagent.main_model(session) if args.kind == 'step' or args.model else None) or args.model
    except OSError as exc:   # an unreadable transcript never blocks an L1 record
        ma_logline.log_error(active, 'run-log main model', exc)
        model = args.model
    if model:
        fields.append(('model', model))
    line = ma_logline.format_line(args.kind, fields)
    report = subagent_mismatches(lines)
    try:
        ma_logline.append(active.log, line)
    except OSError as exc:
        print(f'run-log: cannot write {active.log}: {exc}', file=sys.stderr)
        return 1
    print(line)
    if args.kind == 'step' and dict(fields).get('n') == '1' and not any(k == 'cost' for k, _ in lines):
        sid = active.session or ma_host.session_id()
        usd, why = session_cost(sid, args.data_dir)
        if not why:   # no statusline value: no baseline, nothing printed
            base = ma_logline.format_line('cost', [('session', sid), ('usd', usd), (ma_gate_report.BASELINE, '1')])
            try:
                ma_logline.append(active.log, base)
                print(base)
            except OSError as exc:
                print(f'run-log: cannot write {active.log}: {exc}', file=sys.stderr)
    if model:
        seen = any(f.get('model') == model for k, f in lines if not ma_logline.is_hook_line(k, f))
        if ma_host.main_mismatch(model) and not seen:   # once per task and model
            print(f'MISMATCH: main session configured {ma_host.main_family(model)}, actual {model}')
    for m in report:
        print(m)
    for agent, agent_id, unit in partial:
        print(f'PARTIAL: {agent} {agent_id}{f" unit={unit}" if unit else ""} stopped before its final reply (maxTurns?)')
    bad = ma_logline.unreadable(active.log)
    if bad:   # C9: such lines drop out of every reader, so say so instead of losing them quietly
        print(f"run-log: unreadable line(s) {', '.join(map(str, bad))} in {active.log}", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())

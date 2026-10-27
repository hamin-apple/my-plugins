#!/usr/bin/env python3
"""Append one L1 Recorder line to the active task's run-log.md (architecture 4.7.2).

usage: run-log.py <kind> [key=value ...] [--model MODEL_ID] [--cwd DIR]

The time comes from the clock. `step` needs n= and name=; rev= (latest revision:
line, else 0) and session= ($CLAUDE_CODE_SESSION_ID, else .active) are filled in.
On step lines (and any line given --model), model= is the model of the session
transcript's last main-chain reply (F13: the skill's `model:` holds for one
turn), else --model; it is checked against the configured main model (opus, P9)
and a main-session MISMATCH is printed once per task and model.
Prints the line, then one MISMATCH line per subagent stop: line with
mismatch=1 written since the previous L1 line, and PARTIAL lines (with unit=)
for workers the sweep closed. Unreadable record lines are named on stderr.
Exit 0 written, 1 no active task, 2 bad arguments.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_logline  # noqa: E402
import ma_schema  # noqa: E402
import ma_subagent  # noqa: E402

KINDS = ('step', 'ask', 'answer', 'revision', 'cost', 'stale', 'base', 'abort', 'deliver', 'resume',
         'rules-changed', 'merge', 'fix')
MAIN_MODEL = 'opus'


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('kind')
    ap.add_argument('fields', nargs='*', metavar='key=value')
    ap.add_argument('--model')
    ap.add_argument('--cwd', default=os.getcwd())
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
    active = ma_active.find_active(args.cwd)
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
            fields.append(('session', os.environ.get('CLAUDE_CODE_SESSION_ID') or active.session or None))
    session = dict(fields).get('session') or os.environ.get('CLAUDE_CODE_SESSION_ID') or active.session
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
    if model:
        fam = ma_schema.family(model)
        seen = any(f.get('model') == model for k, f in lines if not ma_logline.is_hook_line(k, f))
        if fam != MAIN_MODEL and not seen:   # once per task and model
            print(f'MISMATCH: main session configured {MAIN_MODEL}, actual {model}')
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

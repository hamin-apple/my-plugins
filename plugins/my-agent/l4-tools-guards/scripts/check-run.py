#!/usr/bin/env python3
"""Pass condition of a scenario run (architecture 4.13 scenarios): did a finished task go through the design's path?

usage: check-run.py <task folder>   (docs/agent/<task-id>/)
Prints `ok <check>` / `FAIL <check>: <why>` per check and `info …` lines (popup count against 4.1 principle 6).
Exit 0 all ok, 1 a check failed, 2 bad arguments.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_logline  # noqa: E402
import ma_plan  # noqa: E402
import ma_schema  # noqa: E402

PEOPLE_GATES = ma_schema.PEOPLE_POPUPS
NORMAL_POPUPS = {'general': 2, 'research': 3, 'dev': 3}


def first_line(path: Path) -> str:
    text = ma_plan.read(path)
    return text.splitlines()[0].strip() if text.strip() else ''


def field(text: str, key: str) -> str:
    for line in text.splitlines():
        k, sep, v = line.partition(':')
        if sep and k.strip() == key:
            return v.strip()
    return ''


def checks(T: Path):
    lines = ma_logline.read(T / 'run-log.md')
    intake = ma_plan.read(T / 'intake.md')
    profile = field(intake, 'Profile') or '-'
    out = []

    def check(name, ok, why=''):
        out.append(f'ok   {name}' if ok else f'FAIL {name}: {why}')

    first = {}
    for i, (kind, f) in enumerate(lines):
        if kind == 'step' and f.get('n', '').isdigit():
            first.setdefault(int(f['n']), i)
    skipped = ma_schema.plan_review_skipped(first_line(T / 'plan-review.md'))
    need = [n for n in range(1, 9) if not (n == 4 and skipped)]
    missing = [n for n in need if n not in first]
    order = [first[n] for n in need if n in first]
    check('steps', not missing and order == sorted(order),
          f'missing {missing}' if missing else 'steps out of order')

    pending, unanswered = {}, []
    for kind, f in lines:
        gate = f.get('gate')
        if gate not in PEOPLE_GATES:
            continue
        if kind == 'ask':
            pending[gate] = pending.get(gate, 0) + 1
        elif kind == 'answer':
            pending[gate] = pending.get(gate, 0) - 1
            if pending[gate] < 0:
                unanswered.append(f'answer without ask ({gate})')
                pending[gate] = 0
    unanswered += [f'{g} ×{n}' for g, n in pending.items() if n > 0]
    check('gates', not unanswered, 'unanswered ' + ', '.join(unanswered))

    started = [f.get('id') for k, f in lines if k == 'start']
    stopped = {f.get('id') for k, f in lines if k == 'stop'}
    open_ids = [i for i in started if i not in stopped]
    check('agents', not open_ids, 'no stop: for ' + ', '.join(map(str, open_ids)))

    g1b = next((i for i, (k, f) in enumerate(lines) if k == 'answer' and f.get('gate') == 'G1b'), None)
    exe = first.get(5)
    check('approval-order', g1b is not None and exe is not None and g1b < exe,
          'G1b answer missing' if g1b is None else 'step 5 before the G1b answer')
    check('approved', ma_plan.approved(T / 'plan.md'), 'plan.md has no Approved line under ## Approval')
    check('verify', first_line(T / 'verify.md') == ma_schema.VERIFY_PASS,
          f"verify.md first line {first_line(T / 'verify.md')!r}")
    check('review', first_line(T / 'review.md') == ma_schema.REVIEW_PASS,
          f"review.md first line {first_line(T / 'review.md')!r}")
    check('g3', any(k == 'answer' and f.get('gate') == 'G3' for k, f in lines), 'no G3 answer')
    check('status', field(intake, 'Status') == 'done', f"intake.md Status: {field(intake, 'Status') or '-'}")
    units = ma_plan.units(T / 'plan.md')
    left = [f'{u} {st or "-"}' for u, _, st in units if st not in ma_schema.UNIT_FINISHED]
    check('units', not left, 'unit Status not done: ' + ', '.join(left))
    bad = ma_logline.unreadable(T / 'run-log.md')
    check('log-format', not bad, 'unreadable run-log line(s) ' + ', '.join(map(str, bad)))
    revs = {}
    for kind, f in lines:
        if kind == 'revision' and f.get('before') is None and f.get('rev'):
            revs[f['rev']] = revs.get(f['rev']) or f.get('state') == 'done'
    open_revs = [r for r, done in revs.items() if not done]
    check('revisions', not open_revs, 'no state=done for rev ' + ', '.join(open_revs))

    popups = sum(1 for k, f in lines if k == 'ask' and f.get('gate') in PEOPLE_GATES)
    normal = NORMAL_POPUPS.get(profile)
    if profile == 'dev' and skipped:
        normal = 2
    out.append(f'info popups: {popups} ({profile} normal path: {normal if normal is not None else "?"})')
    out.append(f"info G2 asks: {sum(1 for k, f in lines if k == 'ask' and f.get('gate') == 'G2')}")
    modes = sorted({f.get('mode') for k, f in lines if k == 'stop' and f.get('mode') not in (None, '-', 'auto')})
    if modes:
        out.append(f"info non-auto permission modes: {', '.join(modes)}")
    partial = sum(1 for k, f in lines if k == 'stop' and f.get('end') == 'partial')
    if partial:
        out.append(f'info partial stops: {partial}')
    return out


def main(argv) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print(__doc__.strip(), file=sys.stderr)
        return 2
    out = checks(Path(argv[0]))
    print('\n'.join(out))
    return 1 if any(line.startswith('FAIL') for line in out) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

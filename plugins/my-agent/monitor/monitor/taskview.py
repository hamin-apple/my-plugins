"""One task folder → one task dict in the mock-up's TASKS shape (plan "Task JSON shape")."""
import hashlib
import re
from datetime import datetime
from pathlib import Path

from .events import build_events
from .mdfiles import read_confirmation, read_criteria, read_intake, read_plan, read_verify
from .prices import cost
from .runlog import read_lines

import ma_schema
import ma_usage

STATUS = dict(zip(ma_schema.INTAKE_STATUS, ('running', 'done', 'stopped')))
PREVIEW_MAX_BYTES, PREVIEW_CHARS = 200 * 1024, 4000
LIVE_SECS = 10 * 60
INTERNAL = ('usage', 'actual_id', 'tokens')


def task_key(project: Path, task_id: str) -> str:
    return hashlib.sha1(str(project).encode()).hexdigest()[:8] + '/' + task_id


def show_path(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    return '~' + s[len(home):] if s == home or s.startswith(home + '/') else s


def _hm(dt, ref):
    return dt.strftime('%H:%M') if dt.date() == ref.date() else dt.strftime('%m-%d %H:%M')


def _size(n):
    return f'{n} B' if n < 1024 else f'{n / 1024:.1f} KB' if n < 1024 * 1024 else f'{n / 1024 / 1024:.1f} MB'


def _step_at(step_enter, ts):
    s = None
    for t, n, _rev, _sess in step_enter:
        if t <= ts:
            s = n
    return s or 1


def _preview(p: Path):
    try:
        if p.stat().st_size > PREVIEW_MAX_BYTES:
            return None
        return p.read_text(encoding='utf-8')[:PREVIEW_CHARS]
    except (OSError, UnicodeDecodeError):
        return None


def _files(task_dir: Path, ev, running, now):
    rows = []
    for p in sorted(task_dir.rglob('*')):
        rel = p.relative_to(task_dir).as_posix()
        if rel.startswith('archive/') or rel == 'archive' or p.is_dir() or p.name.startswith('.'):
            continue
        mt = datetime.fromtimestamp(p.stat().st_mtime)
        row = {'p': rel, 's': _step_at(ev.step_enter, mt), 't': mt.strftime('%H:%M')}
        pv = _preview(p)
        if pv is not None:
            row['pv'] = pv
        if running and (now - mt).total_seconds() < LIVE_SECS:
            row['live'] = True
        rows.append(row)
    arch = task_dir / 'archive'
    if arch.is_dir():
        tree, newest = [], None
        for p in sorted(arch.rglob('*')):
            rel = p.relative_to(arch)
            tree.append('  ' * (len(rel.parts) - 1) + rel.name + ('/' if p.is_dir() else ''))
            mt = datetime.fromtimestamp(p.stat().st_mtime)
            newest = max(newest or mt, mt)
        newest = newest or datetime.fromtimestamp(arch.stat().st_mtime)
        rows.append({'p': 'archive/', 's': _step_at(ev.step_enter, newest), 't': newest.strftime('%H:%M'),
                     'pv': '\n'.join(tree)})
    if running:
        have = {r['p'] for r in rows}
        rows += [{'p': p, 's': s, 'todo': True} for p, s in (('verify.md', 7), ('review.md', 8)) if p not in have]
    return rows


def _mock(plan: dict, r: int):
    """The `## Mock-up` body with its first-line `Kind:` (architect.md) split off; `proto` when L1 asked for one."""
    body = plan.get('mockup')
    if not body:
        return None
    lines = body.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    m = ma_schema.MOCKUP_KIND.match(lines[first].strip()) if first is not None else None
    kind = m.group(1).strip() if m else None
    rest = lines[first + 1:] if m else lines
    at = plan.get('approved_at')
    return {'r': r, 'at': at[11:] if at else None, 'kind': kind, 'body': '\n'.join(rest).strip('\n'),
            'proto': plan.get('prototype')}


def _mocks(task_dir: Path, plan_now: dict, cur_rev: int):
    out = []
    for d in sorted((task_dir / 'archive').glob('*/')):
        m = re.search(r'-rev(\d+)(?:-[b-z])?$', d.name.rstrip('/'))   # `-b`, `-c` when the name was taken
        if not m or int(m.group(1)) < 1:
            continue   # drafts before G1b (`-rev<N>-draft`) and kept verdicts (`-run<n>`) are not an approved plan
        mk = _mock(read_plan(d / 'plan.md'), int(m.group(1)) - 1)
        if mk:
            out.append(mk)
    mk = _mock(plan_now, cur_rev)
    if mk:
        out.append(mk)
    return sorted(out, key=lambda x: x['r'])


def _deliver(project: Path, intake: dict, status: str):
    if intake['delivered']:
        items = []
        for rel in intake['delivered']:
            if rel.startswith(ma_schema.DELIVERED_COMMIT):   # dev profile: the deliverable is a commit (accept.md)
                items.append([rel, 'commit', '–'])
                continue
            p = Path(rel) if Path(rel).is_absolute() else project / rel
            try:
                st = p.stat()
                items.append([rel, _size(st.st_size), datetime.fromtimestamp(st.st_mtime).strftime('%H:%M')])
            except OSError:
                items.append([rel, '–', '–'])
        return {'kind': 'file', 'label': None, 'items': items}
    if status == 'stopped':
        return {'kind': 'none', 'label': None, 'items': []}
    return None


def _main(ev, tcache, prices, unpriced, running, task_dir):
    """{(rev, step): [k, usd]} of the main session, or None if neither a snapshot nor a transcript was found.

    A finished task reads `main-usage.json` (written by L1 at the end of the task, ma_usage) when it exists, since
    Claude Code deletes transcripts after `cleanupPeriodDays`; otherwise the transcript. A finished task's last window
    ends at its last run-log record: the session goes on to other work.
    """
    got = None if running else ma_usage.read_snapshot(task_dir)
    if got is None:
        wins = ma_usage.windows(ev.step_enter, ev.last, running)
        found, got = False, {}
        for sess in {w[0] for w in wins if w[0]}:
            for key, models in tcache.usage_by_window(sess, [(s, e, k) for ss, s, e, k in wins if ss == sess]).items():
                for model, usage in models.items():
                    acc = got.setdefault(key, {}).setdefault(model, dict.fromkeys(ma_usage.KEYS, 0))
                    for k in ma_usage.KEYS:
                        acc[k] += usage[k]
            if tcache.size(sess) is not None:
                found = True
        if not found:
            return None
    out = {}
    for key, models in got.items():
        acc = out.setdefault(key, [0, 0.0])
        for model, usage in models.items():
            acc[0] += sum(usage.values())
            c = cost(prices, model, usage)
            if c is None:
                unpriced.add(model)
            else:
                acc[1] += c
    return {k: [round(v[0] / 1000), round(v[1], 2)] for k, v in out.items()}


def build_task(project: Path, task_dir: Path, prices, tcache, now: datetime) -> dict:
    project, task_dir = Path(project), Path(task_dir)
    tid = task_dir.name
    key = task_key(project, tid)
    try:
        return _build(project, task_dir, tid, key, prices, tcache, now)
    except Exception as exc:   # one broken task must not take the list down (Global Constraints)
        return {'id': tid, 'key': key, 'project': show_path(project), 'error': f'{type(exc).__name__}: {exc}'}


def _build(project, task_dir, tid, key, prices, tcache, now):
    intake = read_intake(task_dir / 'intake.md')
    if intake is None:
        raise OSError(f'cannot read {task_dir / "intake.md"}')
    ev = build_events(read_lines(task_dir / 'run-log.md'))
    plan = read_plan(task_dir / 'plan.md')
    status = STATUS.get(intake['status'], 'running')
    profile = intake['profile']
    cur_rev = ev.step_enter[-1][2] if ev.step_enter else 0
    if ev.revs:
        cur_rev = max(cur_rev, len(ev.revs) - 1)

    def gate(g, ok):
        return 'wait' if ev.gates.get(g) == 'wait' else 'ok' if ok else 'todo'
    gates = {'G1a': 'skip' if profile == 'general' else gate('G1a', read_confirmation(task_dir / 'scope.md')),
             'G1b': gate('G1b', plan['approved_at']),
             'G2': ev.gates.get('G2', 'todo'),
             'G3': gate('G3', status == 'done')}

    scope = task_dir / 'scope.md'
    crit_total = read_criteria(scope) if scope.exists() else read_criteria(task_dir / 'plan.md')

    unpriced, sub_tokens = set(), 0
    log = []
    for it in ev.log:
        it = dict(it)
        if it['k'] == 'agent':
            sub_tokens += it.get('tokens') or 0
            if it.get('usage') and it.get('actual_id'):
                it['c'] = cost(prices, it['actual_id'], it['usage'])
                if it['c'] is not None:
                    it['c'] = round(it['c'], 2)
                else:
                    unpriced.add(it['actual_id'])
        for k in INTERNAL:
            it.pop(k, None)
        log.append(it)

    main = _main(ev, tcache, prices, unpriced, status == 'running', task_dir)
    main_tokens = sum(v[0] for v in main.values()) if main else 0

    started = ev.started or datetime.fromtimestamp((task_dir / 'intake.md').stat().st_mtime)
    end = now if status == 'running' else (ev.last or started)
    task = {
        'id': tid, 'key': key, 'project': show_path(project), 'profile': profile, 'title': intake['title'] or tid,
        'status': status,
        'step': 9 if status == 'done' else (ev.step_enter[-1][1] if ev.step_enter else None),
        'started': _hm(started, now), 'elapsed': round((end - started).total_seconds() / 60),
        'now': end.strftime('%H:%M'),
        'tokens': round(sub_tokens / 1000) + main_tokens, 'cost': ev.cost_usd,
        'gates': gates, 'running': ev.running if status == 'running' else [],
        'waiting': ev.waiting if status == 'running' else None,
        'revs': ev.revs, 'log': log,
        'files': _files(task_dir, ev, status == 'running', now),
        'deliver': _deliver(project, intake, status),
        'crit': {'total': crit_total, 'res': read_verify(task_dir / 'verify.md')},
        'vfail': ev.vfail, 'vfailMax': ev.vfail_max, 'sstop': ev.sstop,
        'mocks': _mocks(task_dir, plan, cur_rev),
        'mainApprox': True,
    }
    if ev.revs:
        task['main'] = None
        task['mainR'] = None if main is None else {}
        for (rev, n), v in (main or {}).items():
            task['mainR'].setdefault(rev, {})[n] = v
    else:
        task['main'] = None if main is None else {n: v for (rev, n), v in main.items()}
    task['unpriced'] = sorted(unpriced)
    return task

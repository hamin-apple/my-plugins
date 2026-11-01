"""One task folder → the report JSON of the Report tab (eight keys). Only reads files; a missing source gives a null key."""
import re
from pathlib import Path

from .mdfiles import read_intake
from .runlog import read_lines

import ma_gate_report
import ma_schema

KEYS = ('overview', 'timeline', 'criteria', 'units', 'review', 'plan_review', 'decisions', 'gate_report')
SENTENCE = re.compile(r'^(.*?[.!?])(?:\s|$)')
TALLY_COST = 'Cost and tokens per stretch'
PICKED = {'yes': 'yes', 'no': 'no', 'delegated': 'delegated', 'typed (Other)': 'typed', 'prose reply': 'typed'}
GATE_MARKS = ('G1a', 'G1b', 'G3')
REVISION_TO = {'1': 2, '2': 3}   # `revision … to=` is the phase to go back to; the Report shows the step


def _text(path: Path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def _iso(ts):
    return ts.strftime('%Y-%m-%dT%H:%M:%S')


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _intake_fields(text):
    out = {}
    for line in (text or '').splitlines():
        key, sep, val = line.partition(':')
        if sep and key.strip() in ('Request', 'Follows') and key.strip() not in out:
            out[key.strip()] = val.strip()
    return out


def follows_of(intake_text):
    """The task id after `Follows:` in an intake.md text, or None."""
    return _intake_fields(intake_text).get('Follows') or None


def _overview(task, task_dir, intake, scope, plan, lines, followed_by):
    delivered = base = None
    for l in lines:
        if l.kind == 'deliver' and l.f.get('path'):
            delivered = l.f['path']
        elif l.kind == 'base' and l.f.get('commit') and base is None:
            base = l.f['commit'][:7]
    if delivered is None:
        shown = (read_intake(task_dir / 'intake.md') or {}).get('delivered') or []
        delivered = shown[-1] if shown else None
    fields = _intake_fields(intake)
    return {'task': task.get('id') or task_dir.name, 'profile': task.get('profile'), 'status': task.get('status'),
            'delivered': delivered, 'base': base, 'follows': fields.get('Follows') or None,
            'followed_by': list(followed_by), 'request': fields.get('Request') or None,
            'purpose': ma_schema.purpose(scope) or ma_schema.purpose(plan)}


def _cost_from_tally(text):
    """[{steps, span, usd, tokens}] from the stretch table of gate-tally.md, or None when it has no such section."""
    body = ma_schema.section_lines(text, TALLY_COST)
    if body is None:
        return None
    out = []
    for line in body:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 4 or not line.strip().startswith('|') or not cells[0][:1].isdigit():
            continue
        try:
            usd = float(cells[2])
        except ValueError:
            usd = None
        steps = '' if cells[1] == '-' else cells[1]
        out.append({'steps': steps, 'span': cells[0].replace('–', '-'), 'usd': usd, 'tokens': _int(cells[3].replace(',', ''))})
    return out


def _cost_from_lines(lines):
    stamped = [(l.raw.strip()[11:16], l.kind, l.f) for l in lines]
    return [{'steps': ', '.join(names), 'span': f'{start}-{end}', 'usd': None if usd is None else round(usd, 2), 'tokens': tokens}
            for start, end, names, usd, tokens in ma_gate_report.segments(stamped)]


def _timeline(task_dir, lines):
    steps, gates, backs, cur = [], [], [], None
    g3_ask = g3_answer = wait_step = None
    for l in lines:
        if l.kind == 'step' and l.f.get('n'):
            n = _int(l.f['n'])
            if l.f.get('back'):
                backs.append({'from': cur, 'to': 5, 'at': _iso(l.ts), 'why': l.f['back']})
            steps.append({'n': n, 'name': l.f.get('name', ''), 'start': _iso(l.ts)})
            cur = n
        elif l.kind == 'revision' and (l.f.get('before') == ma_schema.PLAN_EDIT_GATE or l.f.get('to') in REVISION_TO):
            to = 3 if l.f.get('before') == ma_schema.PLAN_EDIT_GATE else REVISION_TO[l.f['to']]
            backs.append({'from': cur, 'to': to, 'at': _iso(l.ts), 'why': l.f.get('why', '')})
        elif l.kind == 'ask' and l.f.get('gate') in GATE_MARKS and not any(g['id'] == l.f['gate'] for g in gates):
            gates.append({'id': l.f['gate'], 'at': _iso(l.ts)})
            if l.f['gate'] == 'G3':
                g3_ask, wait_step = l.ts, cur
        elif l.kind == 'answer' and l.f.get('gate') == 'G3' and g3_ask is not None:
            g3_answer = l.ts
    end = g3_ask or (lines[-1].ts if lines else None)
    cost = _cost_from_tally(_text(task_dir / 'gate-tally.md'))
    if cost is None:
        cost = _cost_from_lines(lines)
    wait = {'step': wait_step, 'from': _iso(g3_ask), 'until': _iso(g3_answer)} if g3_ask and g3_answer else None
    return {'end': _iso(end) if end else None, 'steps': steps, 'gates': gates, 'backs': backs, 'wait': wait, 'cost': cost}


def _short(text):
    m = SENTENCE.match(text)
    return m.group(1) if m else text


def _criteria(scope, plan, verify):
    rows = ma_schema.criteria(scope) or ma_schema.criteria(plan)
    if not rows:
        return None
    verdicts = {n: (v, e) for n, v, e in ma_schema.verify_rows(verify)}
    return [{'n': n, 'short': _short(text), 'title': text,
             'verdict': verdicts.get(n, (None, None))[0], 'evidence': verdicts.get(n, (None, None))[1]}
            for n, text, _tag in rows]


def _units(plan, lines):
    units = ma_schema.unit_details(plan)
    if not units:
        return None
    secs = {}
    for l in lines:
        if l.kind == 'stop' and l.f.get('unit'):
            secs[l.f['unit']] = secs.get(l.f['unit'], 0) + _int(l.f.get('secs'))
    return [{'id': u['id'], 'title': u['name'], 'status': u['status'], 'group': u['group'],
             'secs': secs.get(u['id'], 0), 'criteria': u['criteria'], 'files': u['files']} for u in units]


def _review(text):
    if text is None:
        return None
    found = ma_schema.review_findings(text)
    applied = ma_schema.review_applied(text)
    blockers = ma_schema.review_blockers(text)
    out = []
    for sev, where, body, mark in found:
        item = {'sev': sev, 'where': where, 'text': body, 'applied': ma_schema.finding_applied(where, applied)}
        if mark:
            item['mark'] = mark
        out.append(item)
    return {'blockers': sum(1 for f in found if f[0] == 'BLOCKER') if blockers is None else blockers, 'findings': out}


def _plan_reviews(task_dir):
    """One entry per distinct Run across archive/*/plan-review.md and plan-review.md; a later copy replaces an earlier one."""
    files = sorted(task_dir.glob('archive/*/plan-review.md')) + [task_dir / 'plan-review.md']
    runs = {}
    for i, path in enumerate(files):
        parsed = ma_schema.plan_review(_text(path))
        if parsed:
            runs[parsed['run'] if parsed['run'] is not None else ('none', i)] = parsed
    if not runs:
        return None
    ordered = sorted(runs.values(), key=lambda p: (p['run'] is None, p['run'] or 0))
    return [{'run': p['run'], 'verdict': p['verdict'], 'blockers': p['blockers'], 'should_fix': p['should_fix'],
             'nitpicks': p['nitpicks']} for p in ordered]


def _decisions(lines):
    """Rows of `ma_gate_report.decisions` with the time of the answer line (or of the ask when unanswered)."""
    pairs = [(l, (l.raw.strip()[11:16], l.kind, l.f)) for l in lines if l.kind in ('ask', 'answer')]
    at, prev = {}, []
    for i in range(len(pairs)):
        rows = ma_gate_report.decisions([p for _, p in pairs[:i + 1]])
        for j, row in enumerate(rows):
            if j >= len(prev) or prev[j][3] != row[3] or prev[j][5] != row[5] or j not in at:
                at[j] = pairs[i][1][0]
        prev = rows
    rows = ma_gate_report.decisions([p for _, p in pairs])
    if not rows:
        return []
    return [{'n': j + 1, 'at': at.get(j, ''), 'gate': r[0], 'q': r[1], 'choice': r[3], 'picked': PICKED.get(r[4], r[4])}
            for j, r in enumerate(rows)]


def _gate_report(text, decisions):
    if text is None:
        return None
    recommended = None
    if decisions is not None:
        yes = sum(1 for d in decisions if d['picked'] == 'yes')
        recommended = {'picked': yes, 'counted': yes + sum(1 for d in decisions if d['picked'] == 'no')}
    return {'recommended': recommended, 'summary': ma_schema.gate_report_summary(text),
            'improvements': [{'level': a, 'strength': b, 'text': c} for a, b, c in ma_schema.gate_report_improvements(text)]}


def build_report(project, task_dir, task, followed_by):
    """The report JSON of one task: `project` (Path), `task_dir` (Path), `task` (the monitor's task dict), `followed_by` (task ids)."""
    task_dir = Path(task_dir)
    intake, scope, plan = (_text(task_dir / n) for n in ('intake.md', 'scope.md', 'plan.md'))
    verify, review, report = (_text(task_dir / n) for n in ('verify.md', 'review.md', 'gate-report.md'))
    has_log = (task_dir / 'run-log.md').is_file()
    lines = read_lines(task_dir / 'run-log.md')
    decisions = _decisions(lines) if has_log else None
    return {
        'overview': _overview(task, task_dir, intake, scope, plan, lines, followed_by),
        'timeline': _timeline(task_dir, lines) if has_log else None,
        'criteria': _criteria(scope, plan, verify) if scope is not None or plan is not None else None,
        'units': _units(plan, lines) if plan is not None else None,
        'review': _review(review),
        'plan_review': _plan_reviews(task_dir),
        'decisions': decisions,
        'gate_report': _gate_report(report, decisions),
    }

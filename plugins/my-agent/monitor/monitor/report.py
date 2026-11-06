"""One task folder → the report JSON of the Report tab (twelve keys). Only reads files; a missing source gives a null key."""
import re
from pathlib import Path

from .mdfiles import read_intake
from .runlog import read_lines

import ma_gate_report
import ma_schema

SENTENCE = re.compile(r'^(.*?[.!?])(?:\s|$)')
TALLY_COST = 'Cost and tokens per stretch'
PICKED = {'yes': 'yes', 'no': 'no', 'delegated': 'delegated', 'typed (Other)': 'typed', 'prose reply': 'typed'}
GATE_MARKS = ('G1a', 'G1b', 'G3')
REVIEW_BODY_SEVS = ('SHOULD-FIX', 'NITPICK')   # the severities listed one by one at G3 (a BLOCKER stops the task earlier)
PLAN_REVIEW_FIX = re.compile(r'^Plan Review (BLOCKER|SHOULD-FIX|NITPICK)\s+(.*)$')
STATUS_WORD = {'done': 'done', 'stopped': 'aborted'}   # task status → verdict status; anything else is running
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


def _overview(task, task_dir, intake, scope, plan, lines, followed_by, ko):
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
    background, purpose = ma_schema.overview_texts(scope, plan)
    out = {'task': task.get('id') or task_dir.name, 'profile': task.get('profile'), 'status': task.get('status'),
           'delivered': delivered, 'base': base, 'follows': fields.get('Follows') or None,
           'followed_by': list(followed_by), 'request': fields.get('Request') or None,
           'background': background, 'purpose': purpose}
    for key in ('background', 'purpose'):
        if key in ko:
            out[key + '_ko'] = ko[key]
    return out


def _ko(task_dir, scope, plan):
    """{key: Korean text} of the task's Korean copy items that still match their English source (`report-ko.json`)."""
    items = ma_schema.ko_copy(_text(task_dir / ma_schema.KO_COPY))
    return ma_schema.ko_current(ma_schema.ko_sources(scope, plan), items) if items else {}


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


def _criteria(scope, plan, verify, ko=None):
    rows = ma_schema.criteria(scope) or ma_schema.criteria(plan)
    if not rows:
        return None
    verdicts = {n: (v, e) for n, v, e in ma_schema.verify_rows(verify)}
    out = []
    for n, text, _tag in rows:
        item = {'n': n, 'short': _short(text), 'title': text,
                'verdict': verdicts.get(n, (None, None))[0], 'evidence': verdicts.get(n, (None, None))[1]}
        if ko and f'c{n}' in ko:
            item.update(title_ko=ko[f'c{n}'], short_ko=_short(ko[f'c{n}']))
        out.append(item)
    return out


def _units(plan, lines, ko=None):
    units = ma_schema.unit_details(plan)
    if not units:
        return None
    secs = {}
    for l in lines:
        if l.kind == 'stop' and l.f.get('unit'):
            secs[l.f['unit']] = secs.get(l.f['unit'], 0) + _int(l.f.get('secs'))
    out = [{'id': u['id'], 'title': u['name'], 'status': u['status'], 'group': u['group'],
            'secs': secs.get(u['id'], 0), 'criteria': u['criteria'], 'files': u['files']} for u in units]
    for u in out:
        if ko and u['id'] in ko:
            u['title_ko'] = ko[u['id']]
    return out


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


def _plan_reviews(task_dir, lines):
    """One entry per distinct Run across archive/*/plan-review.md and plan-review.md; a later copy replaces an earlier one.
    `found` counts the findings of a run per severity; `fixed` those with an `applied` line in its Decisions or a
    run-log `fix … before=G1b` line `Plan Review <SEVERITY> <where> …`."""
    files = sorted(task_dir.glob('archive/*/plan-review.md')) + [task_dir / 'plan-review.md']
    runs = {}
    for i, path in enumerate(files):
        text = _text(path)
        parsed = ma_schema.plan_review(text)
        if parsed:
            runs[parsed['run'] if parsed['run'] is not None else ('none', i)] = (parsed, text)
    if not runs:
        return None
    fixes = [PLAN_REVIEW_FIX.match((l.f.get('what') or '').strip()) for l in lines
             if l.kind == 'fix' and l.f.get('before') == ma_schema.PLAN_EDIT_GATE]
    fixes = [m.groups() for m in fixes if m]
    out = []
    for parsed, text in sorted(runs.values(), key=lambda r: (r[0]['run'] is None, r[0]['run'] or 0)):
        decided = {(sev, where) for sev, where, outcome in ma_schema.plan_review_decisions(text) if outcome == 'applied'}
        found = {sev: 0 for sev in ma_schema.SEVERITIES}
        fixed = dict(found)
        for sev, where, _body, _mark in ma_schema.review_findings(text):
            found[sev] += 1
            if (sev, where) in decided or any(f_sev == sev and ma_schema.finding_applied(where, [rest]) for f_sev, rest in fixes):
                fixed[sev] += 1
        out.append({'run': parsed['run'], 'verdict': parsed['verdict'], 'blockers': parsed['blockers'],
                    'should_fix': parsed['should_fix'], 'nitpicks': parsed['nitpicks'], 'found': found, 'fixed': fixed})
    return out


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


def _review_rounds(task_dir, review):
    """The texts of the Review rounds: archived copies by folder name, then the current review.md; a copy equal to an
    earlier round or to the current file is skipped."""
    rounds = []
    for path in sorted(task_dir.glob('archive/*/review.md')):
        text = _text(path)
        if text is not None and text != review and text not in rounds:
            rounds.append(text)
    if review is not None:
        rounds.append(review)
    return rounds


def _fix_whats(lines):
    """The `what` of run-log `fix` lines after the last `step: n=8` that are Review fixes (no `before=`, no `Scope change:`)."""
    last = max((i for i, l in enumerate(lines) if l.kind == 'step' and l.f.get('n') == '8'), default=-1)
    return [l.f.get('what') or '' for l in lines[last + 1:]
            if l.kind == 'fix' and not l.f.get('before') and not (l.f.get('what') or '').startswith('Scope change:')]


def _review_state(task_dir, review, lines):
    """(review_totals, open findings of the latest round as (sev, where, text, mark)); (None, []) without any round."""
    rounds = _review_rounds(task_dir, review)
    if not rounds:
        return None, []
    found = {sev: 0 for sev in ma_schema.SEVERITIES}
    seen = set()
    for text in rounds:
        this = set()
        for sev, where, _body, mark in ma_schema.review_findings(text):
            if not (mark == 'carried' and (sev, where) in seen):
                found[sev] += 1
            this.add((sev, where))
        seen |= this
    latest = rounds[-1]
    applied = ma_schema.review_applied(latest) + _fix_whats(lines)
    open_items = [f for f in ma_schema.review_findings(latest) if not ma_schema.finding_applied(f[1], applied)]
    totals = {}
    for sev in ma_schema.SEVERITIES:
        n_open = min(found[sev], sum(1 for f in open_items if f[0] == sev))
        totals[sev] = {'found': found[sev], 'fixed': found[sev] - n_open, 'open': n_open}
    totals['rounds'] = len(rounds)
    return totals, open_items


def _passed(verify, total=0):
    """PASS rows of verify.md within the first `total` criteria (verify.md may also judge `Scope change:` lines after them)."""
    return sum(1 for n, verdict, _e in ma_schema.verify_rows(verify) if verdict == 'PASS' and (not total or n <= total))


def _verdict(task, intake, scope, plan, verify, lines, timeline, delivered):
    if not lines:
        return None
    commit = reason = step = None
    for l in lines:
        if l.kind == 'deliver' and (l.f.get('path') or '').startswith(ma_schema.DELIVERED_COMMIT):
            commit = l.f['path'][len(ma_schema.DELIVERED_COMMIT):]
        elif l.kind == 'abort' and l.f.get('why'):
            reason = l.f['why']
        elif l.kind == 'step' and l.f.get('n'):
            step = {'n': _int(l.f['n']), 'name': l.f.get('name', '')}
    status = STATUS_WORD.get(task.get('status'), 'running')
    if reason is None:
        reason = ma_schema.aborted_reason(intake)
    rows = ma_schema.criteria(scope) or ma_schema.criteria(plan)
    criteria = {'pass': _passed(verify, len(rows)), 'total': len(rows)} if rows and verify is not None else None
    g3 = next((l.ts for l in lines if l.kind == 'ask' and l.f.get('gate') == 'G3'), None)
    usd = [c['usd'] for c in timeline['cost'] if c['usd'] is not None]
    return {'status': status, 'delivered': delivered, 'commit': commit, 'tag': None, 'reason': reason or None,
            'step': step if status != 'done' else None, 'criteria': criteria,
            'secs': int(((g3 or lines[-1].ts) - lines[0].ts).total_seconds()), 'usd': round(sum(usd), 2) if usd else None}


def _waiting_gate(lines):
    """The latest ask line of G1a, G1b or G3 with no later answer of the same gate, or None."""
    waiting = None
    for i, l in enumerate(lines):
        if l.kind == 'ask' and l.f.get('gate') in GATE_MARKS \
                and not any(m.kind == 'answer' and m.f.get('gate') == l.f['gate'] for m in lines[i + 1:]):
            waiting = l
    return waiting


def _gate(task, task_dir, scope, plan, verify, review, lines, totals, open_items):
    if task.get('status') != 'running':
        return None
    ask = _waiting_gate(lines)
    if ask is None:
        return None
    gate = {'id': ask.f['gate'], 'at': _iso(ask.ts), 'q': ask.f.get('q', '')}
    if gate['id'] == 'G1a':
        rows = ma_schema.criteria(scope) or ma_schema.criteria(plan)
        gate.update(purpose=ma_schema.overview_texts(scope, plan)[1], criteria=len(rows),
                    non_goals=ma_schema.section_bullets(scope, 'Non-goals'))
    elif gate['id'] == 'G1b':
        lead = ma_schema.plan_lead(plan)
        units = [{'id': u['id'], 'title': u['title'], 'group': u['group']} for u in _units(plan, lines) or []]
        proto = (task_dir / 'prototype' / 'index.html').is_file()
        gate.update(summary=None if lead is None or lead.startswith('Profile:') else lead, units=units,
                    groups=len({u['group'] for u in units if u['group']}),
                    estimate=ma_schema.section_bullets(plan, 'Estimate'), models=ma_schema.models_table(plan),
                    prototype=f"/api/tasks/{task.get('key')}/prototype" if proto else None)
    else:
        rows = ma_schema.verify_rows(verify)
        criteria = ma_schema.criteria(scope) or ma_schema.criteria(plan)
        gate['verify'] = None if verify is None else {
            'verdict': ma_schema.verify_verdict(verify), 'run': ma_schema.run_number(verify), 'pass': _passed(verify, len(criteria)),
            'total': len(criteria) or len(rows), 'failed': [n for n, verdict, _e in rows if verdict == 'FAIL']}
        gate['review'] = None if review is None else {
            'blockers': _review(review)['blockers'], 'totals': totals,
            'open': [{'sev': sev, 'where': where, 'text': body, 'mark': mark}
                     for sev, where, body, mark in open_items if sev in REVIEW_BODY_SEVS]}
    return gate


def _takeaway(verdict, criteria, units, verify, timeline, gate_report):
    scope = delivered = nxt = None
    if criteria:
        scope = {'criteria': len(criteria), 'pass': sum(1 for c in criteria if c['verdict'] == 'PASS'),
                 'units': len(units or []), 'units_done': sum(1 for u in units or [] if u['status'] == 'done'),
                 'verify_run': ma_schema.run_number(verify),
                 'plan_rewrites': sum(1 for b in (timeline or {}).get('backs', []) if b['to'] == 3)}
    if verdict:
        delivered = {k: verdict[k] for k in ('status', 'delivered', 'commit', 'step')}
    items = (gate_report or {}).get('improvements') or []
    if items:
        pick = next((i for i in items if i['strength'] == 'clear'), items[0])
        nxt = {'text': pick['text'], 'clear': sum(1 for i in items if i['strength'] == 'clear'),
               'weak': sum(1 for i in items if i['strength'] == 'weak')}
    if scope is None and delivered is None and nxt is None:
        return None
    return {'scope': scope, 'delivered': delivered, 'next': nxt}


def build_report(project, task_dir, task, followed_by):
    """The report JSON of one task: `project` (Path), `task_dir` (Path), `task` (the monitor's task dict), `followed_by` (task ids)."""
    task_dir = Path(task_dir)
    intake, scope, plan = (_text(task_dir / n) for n in ('intake.md', 'scope.md', 'plan.md'))
    verify, review, report = (_text(task_dir / n) for n in ('verify.md', 'review.md', 'gate-report.md'))
    has_log = (task_dir / 'run-log.md').is_file()
    lines = read_lines(task_dir / 'run-log.md')
    decisions = _decisions(lines) if has_log else None
    ko = _ko(task_dir, scope, plan)
    overview = _overview(task, task_dir, intake, scope, plan, lines, followed_by, ko)
    timeline = _timeline(task_dir, lines) if has_log else None
    criteria = _criteria(scope, plan, verify, ko) if scope is not None or plan is not None else None
    units = _units(plan, lines, ko) if plan is not None else None
    gate_report = _gate_report(report, decisions)
    totals, open_items = _review_state(task_dir, review, lines)
    verdict = _verdict(task, intake, scope, plan, verify, lines, timeline, overview['delivered']) if has_log else None
    return {
        'overview': overview,
        'timeline': timeline,
        'criteria': criteria,
        'units': units,
        'review': _review(review),
        'plan_review': _plan_reviews(task_dir, lines),
        'decisions': decisions,
        'gate_report': gate_report,
        'verdict': verdict,
        'gate': _gate(task, task_dir, scope, plan, verify, review, lines, totals, open_items) if has_log else None,
        'takeaway': _takeaway(verdict, criteria, units, verify, timeline, gate_report),
        'review_totals': totals,
    }

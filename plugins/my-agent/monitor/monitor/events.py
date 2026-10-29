"""run-log lines → log events, step entries, gate facts and counters (plan Task 2 mapping rules).

Gates here are only what the run-log says (pending asks, G2 answers); taskview
finishes them with scope.md, plan.md and intake.md.
"""
from dataclasses import dataclass, field
from datetime import datetime

import ma_schema

PHASE_START = {1: '① Define', 3: '② Plan', 5: '③ Build', 7: '④ Accept'}
PHASE_NAME = {1: '① Define', 2: '② Plan'}   # `profile back=`: the phase number the change returns to
WORKERS = set(ma_schema.UNIT_AGENTS)


@dataclass
class Events:
    log: list = field(default_factory=list)
    step_enter: list = field(default_factory=list)   # (datetime, step, rev, session)
    gates: dict = field(default_factory=dict)
    answered: dict = field(default_factory=dict)     # gate -> last choice
    waiting: dict = None
    running: list = field(default_factory=list)
    revs: list = None
    vfail: int = 0
    vfail_max: int = 0
    sstop: int = 0
    cost_usd: str = None
    started: datetime = None
    last: datetime = None


def alias(model_id):
    """`claude-sonnet-5-5` → `sonnet` (ma_schema.family); other ids pass through, `-` is None."""
    if not model_id or model_id == '-':
        return None
    return ma_schema.family(model_id) or model_id


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def build_events(lines) -> Events:
    e = Events()
    lines = [l for l in lines if l]
    if not lines:
        return e
    e.started, e.last = lines[0].ts, lines[-1].ts
    step, rev = None, 0
    phases_seen = set()
    calls = {}        # agent -> [unpaired items]
    by_id = {}        # agent id -> item
    asks = {}         # (gate, qn or None) -> open popup item (G1a/G1b/G3/E/Q); one per question of a popup
    g2_open = []      # open G2 popup items
    revs, back_wanted = [], None
    verdicts = []     # True per FAIL; None marks a revision, which starts the count again (D5)
    stops = {}        # (rev, unit) -> worker stops; a stop without unit= (not a plan unit) counts on its own id
    costs = {}        # session -> [first, last]

    def item(l, k, a, tx, **kw):
        it = {'t': l.ts.strftime('%H:%M'), 'ts': l.ts.strftime('%Y-%m-%d %H:%M:%S'), 's': step,
              'r': rev, 'k': k, 'a': a, 'tx': tx}
        it.update(kw)
        e.log.append(it)
        return it

    for l in lines:
        f = l.f
        if l.kind == 'step':
            n = _int(f.get('n'))
            if n is None:
                continue
            step = n
            if 'rev' in f and _int(f['rev']) is not None:
                rev = _int(f['rev'])
            e.step_enter.append((l.ts, n, rev, f.get('session')))
            if back_wanted is not None:
                back_wanted['back'] = n
                back_wanted = None
            if n in PHASE_START and (n, rev) not in phases_seen:
                phases_seen.add((n, rev))
                item(l, 'phase', 'router' if n == 1 else 'recorder', f'{PHASE_START[n]} start')
            if f.get('back'):        # back to Execute after a Verify FAIL, Review BLOCKER or G3 rework (B2)
                item(l, 'phase', 'recorder', f"back to {f.get('name') or n} · {f['back']}",
                     sub=f"archive {f['archive']}" if f.get('archive') else None)
        elif l.kind == 'call':
            a = f.get('agent', '').removeprefix('my-agent:')
            iso = f.get('isolation')
            it = item(l, 'agent', a, f.get('agent', ''), sub=f'isolation: {iso}' if iso not in (None, '-') else None,
                      model=None, actual=None, effort=None, tok=None, dur=None, c=None, res=None, end=None,
                      live=True, mm=False, id=None)
            calls.setdefault(a, []).append(it)
        elif l.kind == 'start':
            a = f.get('agent', '').removeprefix('my-agent:')
            pending = calls.get(a)
            it = pending.pop() if pending else item(l, 'agent', a, f.get('agent', ''), sub=None, actual=None,
                                                    tok=None, dur=None, c=None, res=None, end=None, live=True, mm=False)
            it.update(id=f.get('id'), model=alias(f.get('configured')), effort=f.get('effort'))
            if it['id']:
                by_id[it['id']] = it
        elif l.kind == 'stop':
            it = by_id.get(f.get('id'))
            if not it:
                continue
            tokens, secs = _int(f.get('tokens')), _int(f.get('secs'))
            it.update(live=False, actual=alias(f.get('actual')), res=f.get('result'), end=f.get('end'),
                      tok=f'{round(tokens / 1000)}k' if tokens is not None else None,
                      dur=round(secs / 60) if secs is not None else None, tokens=tokens,
                      usage={'input_tokens': _int(f.get('in')) or 0, 'output_tokens': _int(f.get('out')) or 0,
                             'cache_creation_input_tokens': _int(f.get('cw')) or 0,
                             'cache_read_input_tokens': _int(f.get('cr')) or 0} if 'in' in f else None,
                      actual_id=f.get('actual'))
            it['mm'] = bool(it['model'] and it['actual'] and it['model'] != it['actual'])
            if it['a'] == 'verifier' and it['res']:
                verdicts.append(ma_schema.verify_failed(it['res']))
            if it['a'] in WORKERS and it['end'] in ma_schema.INTERRUPTED and it['r'] == rev:
                key = (rev, f.get('unit') or 'id:' + str(f.get('id')))
                stops[key] = stops.get(key, 0) + 1
                e.sstop = max(e.sstop, stops[key])
            for g in g2_open:
                if g.get('id') == it['id'] and g['sub'] is None:
                    g['sub'] = 'not run (denied?)'
        elif l.kind == 'ask':
            gate = f.get('gate')
            if gate == 'G2':
                g2_open.append(item(l, 'popup', 'perms', f"G2 {f.get('q', '')}".strip(), sub=None,
                                    id=f.get('id'), tool=f.get('tool'), agent=f.get('agent')))
            elif gate:
                asks[(gate, f.get('qn'))] = item(l, 'popup', 'gatekeeper', f"{gate} {f.get('q', '')}".strip(), sub=None)
        elif l.kind == 'answer':
            gate = f.get('gate')
            if gate == 'G2':
                for g in reversed(g2_open):
                    if g['sub'] in (None, 'not run (denied?)') and (not f.get('id') or g.get('id') == f.get('id')):
                        g['sub'] = f.get('result') or f.get('choice')
                        break
                e.answered['G2'] = f.get('result') or f.get('choice')
            elif any(g == gate for g, _ in asks):
                key = (gate, f.get('qn'))     # no qn on the answer: the latest open ask of the gate
                if key not in asks:
                    key = [k for k in asks if k[0] == gate][-1]
                sub = f.get('choice')
                if f.get('by') == ma_schema.ANSWERED_BY_L1:
                    sub = f'{sub} · answered by L1'
                asks.pop(key)['sub'] = sub
                e.answered[gate] = f.get('choice')
        elif l.kind == 'revision':
            n = _int(f.get('rev'))
            if f.get('before'):      # a plan rewritten before G1b: no new rev (B1)
                item(l, 'phase', 'recorder', f"plan rewrite before {f.get('before')} · {f.get('why', '')}".strip(' ·'))
                continue
            done = next((r for r in revs if r['rev'] == n), None) if n is not None else None
            if done is not None:     # `state=done`: the same revision finished its invalidation (B4)
                done['state'] = f.get('state') or done['state']
                continue
            rev = n if n is not None else rev + 1
            entry = {'at': l.ts.strftime('%H:%M'), 'from': step, 'back': None, 'why': f.get('why'),
                     'archive': f.get('archive'),
                     'invalid': [s.strip() for s in f.get('invalidated', '').split(',') if s.strip()],
                     'keep': f.get('keep'), 'rev': rev, 'state': f.get('state')}
            revs.append(entry)
            back_wanted = entry
            verdicts.append(None)
            item(l, 'rev', 'gatekeeper', f"rev{rev} {f.get('why', '')}".strip(), sub=f.get('keep'))
        elif l.kind == 'fix' and (f.get('what') or '').startswith('Scope change:'):
            item(l, 'phase', 'recorder', f.get('what'))
        elif l.kind == 'fix' and f.get('before') == ma_schema.PLAN_EDIT_GATE:
            item(l, 'phase', 'recorder', f"plan edit by L1 · {f.get('what', '')}".rstrip(' ·'))
        elif l.kind == 'delegate' and f.get('state') in ma_schema.DELEGATE_STATES:
            how = f" ({f['how']})" if f.get('how') else ''
            item(l, 'phase', 'recorder', f"delegated approval {f['state']}{how}")
        elif l.kind == 'profile' and f.get('from') and f.get('to'):
            back = f.get('back')
            tail = f" · back to {PHASE_NAME.get(_int(back), back)}" if back not in (None, '', '-') else ''
            item(l, 'phase', 'recorder', f"profile {f['from']} → {f['to']}{tail}")
        elif l.kind == 'cost':
            s = f.get('session', '')
            try:
                usd = float(f.get('usd'))
            except (TypeError, ValueError):
                continue
            costs.setdefault(s, [usd, usd])[1] = usd
        elif l.kind == 'deliver':
            item(l, 'phase', 'recorder', f"deliver · {f.get('path', '')}".rstrip(' ·'))
        elif l.kind == 'abort':
            item(l, 'phase', 'recorder', f"abort · {f.get('why', '')}".rstrip(' ·'))

    for gate, _ in asks:
        e.gates[gate] = 'wait'
    if 'G2' in e.answered:
        e.gates['G2'] = 'ok'
    pending_g2 = [g for g in g2_open if g['sub'] is None]
    if asks:
        (gate, _), it = max(reversed(list(asks.items())), key=lambda x: x[1]['ts'])
        e.waiting = {'gate': gate, 'q': it['tx'][len(gate) + 1:]}
    elif pending_g2:
        e.waiting = {'gate': 'G2', 'q': pending_g2[-1]['tx'][3:]}
        e.gates['G2'] = 'wait'
    e.running = [{'a': it['a'], 'id': it['id'], 'sub': it['sub'], 'model': it['model'], 'effort': it.get('effort'), 'since': it['t']}
                 for it in e.log if it['k'] == 'agent' and it['live']]
    if revs:
        e.revs = [{'at': e.started.strftime('%H:%M')}] + [{k: v for k, v in r.items() if k != 'rev'} for r in revs]
    streak = 0
    for failed in verdicts:
        streak = streak + 1 if failed else 0
        e.vfail_max = max(e.vfail_max, streak)
    e.vfail = streak
    if costs:
        e.cost_usd = '%.2f' % sum(last - first for first, last in costs.values())
    return e

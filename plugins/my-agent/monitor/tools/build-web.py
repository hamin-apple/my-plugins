"""webapp-v22.html → my-agent-monitor/web/index.html (plan Task 7 edits)."""
import re, sys
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / 'dev/my-plugins/plugins/my-agent/.superpowers/brainstorm/29416-1792798606/content/webapp-v22.html'
DST = Path(__file__).resolve().parent.parent / 'web' / 'index.html'
s = SRC.read_text(encoding='utf-8')

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit(f'expected {count} match(es), got {n}: {old[:80]!r}')
    s = s.replace(old, new)

def cut(start, end, new):
    """replace from `start` up to (not incl.) `end`"""
    global s
    i = s.index(start); j = s.index(end, i)
    s = s[:i] + new + s[j:]

# chrome
rep('${etag(run.a)}', '${etag(run.a, run.effort)}')
rep("const mtag = m => `<span class=\"mtag ${m.split(' ')[0]}\">${esc(m)}</span>`;", "const mtag = m => { m = m || '–'; return `<span class=\"mtag ${m.split(' ')[0]}\">${esc(m)}</span>`; };")
rep('<title>my-agent monitor (mock-up v22)</title>', '<title>my-agent monitor</title>\n<link rel="icon" href="data:,">')
rep('\n  <span class="mock-tag" id="mock-tag"></span>', '')
rep("  $('mock-tag').textContent = L('mock-up · fake data', '목업 · 가짜 데이터');\n", '')
rep("const esc = s => String(s)", "const esc = s => (s == null ? '–' : String(s))")
rep("const prof = t => L(...PROF[t.profile]);", "const prof = t => PROF[t.profile] ? L(...PROF[t.profile]) : '–';")

# data: fetched from the server
cut('/* ---------- mock tasks ---------- */', '/* ---------- mock-ups', 
    '/* ---------- tasks: summaries from /api/tasks, full task JSON from /api/tasks/<key> ---------- */\n'
    'let TASKS = [];\nconst FULL = {};\n\n')
cut('/* ---------- mock-ups (plan.md ## Mock-up, approved at G1b) ---------- */', '/* line diff (LCS) */',
    'const mocksOf = t => t.mocks || [];\n')

# effort from the record, the definition as fallback
rep("const etag = a => EFFORT[a] ? ` <span class=\"etag\" title=\"effort\">${EFFORT[a]}</span>` : '';",
    "const etag = (a, eff) => (eff || EFFORT[a]) ? ` <span class=\"etag\" title=\"effort\">${eff || EFFORT[a]}</span>` : '';")
rep("${etag(e.a)}", "${etag(e.a, e.effort)}", 1)
rep("${EFFORT[e.a] ? ' · effort ' + EFFORT[e.a] : ''}", "${(e.effort || EFFORT[e.a]) ? ' · effort ' + (e.effort || EFFORT[e.a]) : ''}")
rep("const LV_OF = id => LEVELS.find(l => l.comps.some(c => c[0] === id));",
    "const LV_OF = id => LEVELS.find(l => l.comps.some(c => c[0] === id)) || LEVELS[2];\n"
    "const compName = (lv, id) => (lv.comps.find(c => c[0] === id) || [id, id])[1];")
rep("${esc(lv.comps.find(c => c[0] === e.a)[1])}", "${esc(compName(lv, e.a))}", 2)

# state keyed by task key
rep("const st = { task: TASKS[0].id, tab: 'status', filter: 'all', comp: 'coder', file: 'plan.md' };\n"
    "const cur = () => TASKS.find(t => t.id === st.task);",
    "const st = { task: null, tab: 'status', filter: 'all', comp: 'coder', file: 'plan.md' };\n"
    "const cur = () => FULL[st.task];")
rep('data-task="${t.id}" aria-current="${t.id === st.task}"', 'data-task="${t.key}" aria-current="${t.key === st.task}"', 2)
rep('<option value="${t.id}" ${t.id === st.task ? \'selected\' : \'\'}>', '<option value="${t.key}" ${t.key === st.task ? \'selected\' : \'\'}>')
rep("  $('side-note').innerHTML = L('Tasks found in <code>docs/agent/</code> of 3 projects.', '프로젝트 3곳의 <code>docs/agent/</code>에서 찾은 작업입니다.');",
    "  const np = new Set(TASKS.map(t => t.project)).size;\n"
    "  $('side-note').innerHTML = TASKS.length ? L(`Tasks found in <code>docs/agent/</code> of ${np} project${np === 1 ? '' : 's'}.`, `프로젝트 ${np}곳의 <code>docs/agent/</code>에서 찾은 작업입니다.`)\n"
    "    : L('No tasks yet. my-agent lists projects in <code>~/dev/agent-tasks/projects.txt</code>.', '아직 작업이 없습니다. my-agent가 <code>~/dev/agent-tasks/projects.txt</code>에 프로젝트를 적습니다.');")
rep("  $('live-txt').textContent = st.liveWait ? L('Live · waiting for your answer', '실시간 · 사람의 답을 기다리는 중') : L('Live · checks docs/agent/ every 2s', '실시간 · 2초마다 docs/agent/ 확인');",
    "  $('live-txt').textContent = st.offline ? L('Server not reachable', '서버에 연결할 수 없음') : st.liveWait ? L('Live · waiting for your answer', '실시간 · 사람의 답을 기다리는 중') : L('Live · checks docs/agent/ every 2s', '실시간 · 2초마다 docs/agent/ 확인');\n"
    "  $('live-dot').classList.toggle('run', !st.offline && !st.liveWait && TASKS.some(t => t.status === 'running'));")

# null-safe numbers and missing records
rep("const mainOf = (t, R) => R === 'all' ? (t.revs ? Object.values(t.mainR).reduce(",
    "const mainOf = (t, R) => R === 'all' ? (t.revs ? Object.values(t.mainR || {}).reduce(")
rep("  : t.revs ? (t.mainR[R] || {}) : (R === 0 ? (t.main || {}) : {});",
    "  : t.revs ? ((t.mainR || {})[R] || {}) : (R === 0 ? (t.main || {}) : {});\n"
    "const hasMain = t => !!(t.revs ? t.mainR : t.main);")
rep("  evs.forEach(e => { const s = steps[e.s]; if (!s.start) s.start = e.t;",
    "  evs.forEach(e => { const s = steps[e.s]; if (!s) return; if (!s.start) s.start = e.t;")
rep("  models[L('opus · main session', 'opus · 메인 세션')] = { calls: 0, tok: mt[0], min: evs.length ? mins(revEnd(t, R)) - mins(evs[0].t) : 0, cost: mt[1], live: t.status === 'running' ? 1 : 0, main: true };",
    "  models[L('opus · main', 'opus · main')] = { calls: 0, tok: mt[0], min: evs.length ? mins(revEnd(t, R)) - mins(evs[0].t) : 0, cost: mt[1], live: t.status === 'running' ? 1 : 0, main: true, nil: !hasMain(t) };")
rep("const money = c => '$' + c.toFixed(2);", "const money = c => c == null ? '–' : '$' + (+c).toFixed(2);")
rep("<td class=\"n\">${bar(r.tok, maxTok)}${r.tok}k</td><td class=\"n\">${fmtMin(r.min)}</td><td class=\"n\">${money(r.cost)}</td></tr>`).join('')}",
    "<td class=\"n\">${r.nil ? '–' : bar(r.tok, maxTok) + r.tok + 'k'}</td><td class=\"n\">${r.nil ? '–' : fmtMin(r.min)}</td><td class=\"n\">${r.nil ? '–' : money(r.cost)}</td></tr>`).join('')}")
rep("    ${t.log.filter(isMM).map(e =>",
    "    ${(t.unpriced || []).length ? `<p class=\"note\">${L('Not in prices.json: ', 'prices.json에 없는 모델: ')}${t.unpriced.map(esc).join(', ')}</p>` : ''}\n    ${t.log.filter(isMM).map(e =>")
rep("  const ratio = t.tokens / t.est,", "  const ratio = t.est ? t.tokens / t.est : 0,")
rep("<small class=\"ks\">/ ${t.est}k ${L('estimate', '예상')}</small></div>\n      <div class=\"bar ${ratio >= 1 ? 'warn' : ''} ${t.status === 'running' ? 'live' : ''}\" data-p=\"${Math.min(1, ratio)}\"><i></i></div><div class=\"ks\">${Math.round(ratio * 100)}% ${L('of estimate', '사용')}</div></div>",
    "<small class=\"ks\">/ ${t.est ? t.est + 'k' : '–'} ${L('estimate', '예상')}</small></div>\n      <div class=\"bar ${ratio >= 1 ? 'warn' : ''} ${t.status === 'running' ? 'live' : ''}\" data-p=\"${Math.min(1, ratio)}\"><i></i></div><div class=\"ks\">${t.est ? Math.round(ratio * 100) + '%' : '–'} ${L('of estimate', '사용')}</div></div>")
rep("statusline ${cu('cost-' + t.id, +t.cost, '$')}", "statusline ${t.cost == null ? '–' : cu('cost-' + t.id, +t.cost, '$')}")
rep("money(num(e.c))", "money(e.c)", 2)
rep("costSoFar = done.reduce((a, x) => a + num(x.c), 0);", "costSoFar = done.reduce((a, x) => a + num(x.c), 0);")
rep("  if (!mock && !isDiff && !t.files.some(f => f.p === st.file)) st.file = t.files[0].p;\n  const f = mock || isDiff ? { p: 'mock', t: '', pv: '' } : t.files.find(x => x.p === st.file);",
    "  if (!mock && !isDiff && !t.files.some(f => f.p === st.file)) st.file = t.files.length ? t.files[0].p : null;\n  const f = mock || isDiff ? { p: 'mock', t: '', pv: '' } : t.files.find(x => x.p === st.file) || { p: '–', t: '', pv: '' };")
rep("  const d = t.deliver, M = mocksOf(t);",
    "  const d = t.deliver || { kind: 'none', label: null, items: [] }, M = mocksOf(t);\n"
    "  const dLabel = d.label || (d.kind === 'file' ? L('saved where the scope said', '범위 문서가 정한 위치에 저장') : t.status === 'stopped' ? L('stopped · nothing delivered', '중단 · 결과물 없음') : t.status === 'running' ? L('after G3', 'G3 뒤에 저장') : L('none', '없음'));")
rep("Final deliverable · ${esc(d.label)}", "Final deliverable · ${esc(dLabel)}")

# empty log
rep("function timeline(t) {\n", "function timeline(t) {\n  if (!t.log.length) return `<p class=\"note\">${L('No run-log records yet.', '아직 run-log 기록이 없습니다.')}</p>`;\n")
rep("function replay(t) {\n  const n = t.log.length;\n", "function replay(t) {\n  const n = t.log.length;\n  if (!n) return `<p class=\"note\">${L('No run-log records yet.', '아직 run-log 기록이 없습니다.')}</p>`;\n")
rep("function compView() {\n  const t = cur(), e = t.log[st.ri || 0]",
    "function compView() {\n  const t = cur(); if (!t || !t.log || !t.log.length) return `<p class=\"note\">${L('No run-log records yet.', '아직 run-log 기록이 없습니다.')}</p>`;\n  const e = t.log[st.ri || 0]")
rep("${curStep}. ${esc(STEP_NAME[curStep])}", "${curStep ?? '–'}. ${esc(STEP_NAME[curStep])}")

# nothing to show / unreadable task
rep("function renderAll() { renderChrome(); renderList(); renderHead(); renderStatus(); renderArch(); renderFiles(); renderLog();",
    "function renderAll() { renderChrome(); renderList();\n"
    "  const t = cur();\n"
    "  if (!t || t.error) {\n"
    "    $('task-head').innerHTML = t ? `<h2>${esc(t.id)}</h2><span class=\"where\"><code>${esc(t.project)}/docs/agent/${esc(t.id)}/</code></span>` : '';\n"
    "    $('p-status').innerHTML = t ? `<div class=\"now-box\"><h4>${L('Could not read this task', '이 작업을 읽을 수 없음')}</h4><p class=\"note\">${esc(t.error)}</p></div>`\n"
    "      : `<p class=\"note\">${st.offline ? L('Server not reachable', '서버에 연결할 수 없음') : L('No tasks yet.', '아직 작업이 없습니다.')}</p>`;\n"
    "    ['p-arch', 'p-files', 'p-log'].forEach(id => $(id).innerHTML = '');\n"
    "  } else { renderHead(); renderStatus(); renderArch(); renderFiles(); renderLog(); }")

# task switching waits for the full task
rep("  if (b.dataset.task) { st.task = b.dataset.task; st.ri = 0; st.rev = null; entering(); vt(() => { renderAll(); }); setTimeout(() => scramble(document.querySelector('#task-head h2')), 30); }",
    "  if (b.dataset.task) { selectTask(b.dataset.task); }")
rep("$('task-select').addEventListener('change', e => { st.task = e.target.value; renderAll(); });",
    "$('task-select').addEventListener('change', e => selectTask(e.target.value));")

# the fake live block → polling
cut('/* ---------- fake live updates for the running task ---------- */', '</script>', r'''/* ---------- live data: poll the local server every 2 s ---------- */
const POLL_MS = 2000;
let lastSig = '';
async function getJSON(url) { const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw new Error(r.status + ' ' + url); return r.json(); }
async function loadTask(key) {
  const t = await getJSON('/api/tasks/' + encodeURIComponent(key).replace(/%2F/g, '/'));
  const old = FULL[key];
  if (old && old.log && t.log) {   /* follow the newest record only if replay was already at the end */
    const seen = new Set(old.log.map(e => e.ts + e.k + e.tx));
    t.log.forEach(e => { e.isNew = !seen.has(e.ts + e.k + e.tx); });
    if (key === st.task && !st.playing && st.ri === old.log.length - 1 && t.log.length > old.log.length) st.ri = t.log.length - 1;
  }
  FULL[key] = t;
  return t;
}
async function poll() {
  try {
    const data = await getJSON('/api/tasks');
    TASKS = data.tasks;
    if (!TASKS.some(t => t.key === st.task)) st.task = (TASKS.find(t => t.status === 'running') || TASKS[0] || {}).key || null;
    if (st.task) await loadTask(st.task);
    st.offline = false;
  } catch (err) { st.offline = true; }
  st.liveWait = TASKS.some(t => t.status === 'running' && t.waiting);
  const sig = JSON.stringify([TASKS, st.task && FULL[st.task], st.offline]);
  if (sig !== lastSig) { const first = !lastSig; lastSig = sig; if (first) entering(); renderAll(); if (first) setTimeout(() => scramble(document.querySelector('#task-head h2')), 30); }
}
async function selectTask(key) {
  st.task = key; st.ri = 0; st.rev = null;
  if (!FULL[key]) { try { await loadTask(key); } catch (err) { st.offline = true; } }
  lastSig = JSON.stringify([TASKS, FULL[key], st.offline]);
  entering(); vt(() => renderAll()); setTimeout(() => scramble(document.querySelector('#task-head h2')), 30);
}
poll(); setInterval(poll, POLL_MS);
''')


# HH:MM differences wrap at midnight
rep("const mins = hm => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };",
    "const mins = hm => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };\n"
    "const dm = (a, b) => (((mins(b) - mins(a)) % 1440) + 1440) % 1440;   /* minutes from a to b, across midnight */")
rep("${mins(t.now) - mins(run.since)}", "${dm(run.since, t.now)}", 2)
rep("min: evs.length ? mins(revEnd(t, R)) - mins(evs[0].t) : 0", "min: evs.length ? dm(evs[0].t, revEnd(t, R)) : 0")
rep("steps[n].min = Math.max(0, mins(end) - mins(steps[n].start));", "steps[n].min = dm(steps[n].start, end);")
rep("const t0 = mins(t.log[0].t), t1 = Math.max(mins(t.now), t0 + 1),", "const t0 = mins(t.log[0].t), t1 = t0 + Math.max(1, dm(t.log[0].t, t.now)),")

# a task from before run-log v0.19 has no step
rep("    : `<div class=\"kv2\">${t.step}. ${esc(STEP_NAME[t.step])} <span", "    : `<div class=\"kv2\">${t.step ? t.step + '. ' + esc(STEP_NAME[t.step]) : '–'} <span")
rep("L(`at ${t.step}. ${STEP_NAME[t.step]}`, `${t.step}. ${STEP_NAME[t.step]}에서`)", "(t.step ? L(`at ${t.step}. ${STEP_NAME[t.step]}`, `${t.step}. ${STEP_NAME[t.step]}에서`) : '–')")

# leftover guard: no mock data names may remain
for bad in ['const TASKS = [', 'const MOCKS', 'QUEUE', 'MOCKS[']:
    if bad in s:
        sys.exit('leftover: ' + bad)
DST.write_text(s, encoding='utf-8')
print('written', DST, len(s))

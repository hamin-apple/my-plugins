# my-agent monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only local web page on the Mac that shows every my-agent task (dashboard, architecture, deliverables, log replay) from the files my-agent writes.

**Architecture:** A Python standard-library package `monitor/` reads the project list, each task folder, its `run-log.md` and the main-session transcript, and builds one JSON object per task in exactly the shape the mock-up's `TASKS` entries have. `server.py` serves that JSON and `web/index.html`. `web/index.html` is mock-up v22 with the fake data and fake live queue replaced by a 2-second fetch.

**Tech Stack:** Python 3.13 (macOS `python3`), standard library only (`http.server`, `json`, `unittest`, `hashlib`, `pathlib`), plain HTML/CSS/JS, no build step.

**Spec:** `~/dev/my-agent/my-agent-monitor-design.md` (v0.1, approved). Data contract: spec 5.2 and `~/dev/my-agent/my-agent-architecture.md` v0.19 4.7.2 ("line format", "G2 records"). Screen: `~/dev/my-agent/.superpowers/brainstorm/29416-1792798606/content/webapp-v22.html`.

## Global Constraints

- Project root: `~/dev/my-agent-monitor/` (new). The monitor writes only inside this folder.
- Never write to, lock or rename anything under a project's `docs/agent/`, a transcript, or `~/dev/agent-tasks/`. Open files read-only.
- Server binds `127.0.0.1` only. Default port `8765`; if busy, try `8766`…`8775`.
- Python standard library only. Tests: `python3 -m unittest` from the project root.
- Project list: `~/dev/agent-tasks/projects.txt`, one path per line (override with env `MA_PROJECTS_FILE`).
- Transcripts: `~/.claude/projects/*/<session>.jsonl` (override root with env `MA_CLAUDE_PROJECTS`).
- Prices: `~/dev/my-agent-monitor/prices.json`, USD per 1M tokens, keys are model-ID prefixes.
- run-log line: `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`; values with spaces in double quotes; unknown kinds ignored; a line without `rev` takes the latest `revision:` rev (rev0 if none).
- A task that fails to parse is returned as `{"id", "project", "error": "<message>"}`; other tasks are unaffected.
- Values not in the records are `null` in JSON and shown as `–`; never invented.
- Titles stay English; other UI text follows the EN/Korean toggle; text read from records is never translated (spec 4).
- Git: `git init` the new project in Task 1. Each "Commit" step runs only after the user approves committing (user's git rule).

## Review Focus

1. A run-log line written half-way (no trailing newline, or cut mid-quote) while the monitor reads it — the line is skipped this round and parsed on the next poll; the task never shows "error".
2. A task folder from before v0.19 (no `step:` lines, old popup lines) — shows the task with steps as `–`, no crash.
3. A transcript that is huge (hundreds of MB) or missing — the poll stays under 2 s after the first read (incremental read); missing gives main-session row `null`.
4. A project path in `projects.txt` that no longer exists, or a line with trailing spaces / `~` — skipped or expanded, other projects still listed.
5. Live refresh while the user is mid-replay or has a file selected — selection, replay position and sidebar state are kept; no re-animation.

Tests for each are named in the owning task (Task 1: 1; Task 2: 2; Task 4: 3; Task 5: 4; Task 7: 5; Task 8 re-checks 1 live).

---

## File Structure

```text
~/dev/my-agent-monitor/
├── server.py                  # entry point: python3 server.py [--port N]
├── monitor/
│   ├── __init__.py
│   ├── runlog.py              # line parser → Line records
│   ├── mdfiles.py             # intake.md, .active, scope.md, plan.md, verify.md readers
│   ├── events.py              # Line records → log events, steps, gates, counters
│   ├── transcript.py          # main-session usage per time window, incremental
│   ├── prices.py              # prices.json → cost
│   ├── taskview.py            # one task folder → task dict (mock-up TASKS shape)
│   └── registry.py            # projects.txt → task folders; list + cache by mtime
├── web/index.html             # mock-up v22 wired to the API
├── prices.json
├── tools/feed-fixture.py      # appends run-log lines to a fixture copy for live testing
├── tests/
│   ├── fixtures/projects/…    # 5 tasks of the mock-up as real folders
│   └── test_*.py
└── README.md
```

## Task JSON shape (contract between Python and `web/index.html`)

Same fields the mock-up's `TASKS` entries use; Task 7 reads exactly these.

```text
task = {
  id, key, project, profile ('dev'|'research'|'general'), title, status ('running'|'done'|'stopped'),
  step (1-8, 9 when done), started ('HH:MM' or 'MM-DD HH:MM'), elapsed (minutes), now ('HH:MM'),
  tokens (k, int), est (k, int|null), cost (statusline USD str|null),
  gates {G1a,G1b,G2,G3: 'ok'|'wait'|'skip'|'todo'},
  running [{a, id, sub, model, since}], waiting {gate, q}|null,
  revs [{at} , {at, from, back, why, archive, invalid[], keep}] | null,
  main {step: [k, usd]}  or  mainR {rev: {step: [k, usd]}},  mainApprox: true,
  log [{t, ts, s, k ('phase'|'agent'|'popup'|'rev'), a, r, tx, sub, model, actual, effort,
        tok ('84k'), dur (min), c (usd), res, end, live, mm}],
  files [{p, s, t, pv, todo, live}], deliver {kind, label, items[[path, size, time]]},
  crit {total, res ['p'|'f'|'r']}, vfail, vfailMax, sstop,
  mocks [{r, at, kind, body, proto}], unpriced [model ids], error?
}
```

`key` = first 8 hex of sha1(project path) + `/` + task id.

---

### Task 1: Scaffold, fixtures, run-log line parser

**Files:**
- Create: `monitor/__init__.py`, `monitor/runlog.py`, `tests/test_runlog.py`, `tests/fixtures/projects/…`, `README.md` (run + test commands only), `.gitignore` (`__pycache__/`)

**Interfaces:**
- Produces: `Line = NamedTuple(ts: datetime, kind: str, f: dict[str, str], raw: str)`; `parse_line(text: str) -> Line | None`; `read_lines(path: Path) -> list[Line]` (ignores a last line without `\n`).

Fixtures: build the five mock-up tasks (`TASKS` in webapp-v22.html) as real folders under `tests/fixtures/projects/{claude-sessions,agent-tasks,obsidian-notes,work-notes,flight-search}/docs/agent/<task-id>/` with `intake.md`, `scope.md`, `plan.md` (incl. `## Estimate`, `## Mock-up`, `## Approval`, `## Revisions`), `verify.md`, `run-log.md` in the v0.19 line format, `work/` files, and for `261024-hitl-survey` an `archive/261024-144700-rev1/`. Add `tests/fixtures/projects.txt` listing the five paths and `tests/fixtures/claude-projects/x/<session>.jsonl` with assistant usage entries for `261024-cli-json-output`. Set file mtimes with `os.utime` in a `tests/fixtures/make_mtimes.py` called from `tests/__init__.py`, matching the mock-up `files[].t`.

- [ ] **Step 1:** `git init ~/dev/my-agent-monitor`, create the folders above.
- [ ] **Step 2: Write failing tests** in `tests/test_runlog.py`:
  - `test_parses_kv_and_quotes`: `parse_line('2026-10-24 16:01:15 ask: gate=G2 tool=Bash q="npm i x"')` → `kind=='ask'`, `f=={'gate':'G2','tool':'Bash','q':'npm i x'}`.
  - `test_unknown_kind_kept`: kind `foo` parses (callers ignore it).
  - `test_garbage_returns_none`: `'hello'`, `''`, `'2026-10-24 16:01 ask'` → `None`.
  - `test_unclosed_quote_returns_none`: `'2026-10-24 16:01:15 ask: q="npm i'` → `None` (Review Focus 1).
  - `test_read_lines_skips_partial_last_line`: file ending without `\n` → last line not returned.
- [ ] **Step 3:** Run `python3 -m unittest tests.test_runlog -v` → FAIL (module missing).
- [ ] **Step 4:** Implement `parse_line` with `shlex.split` on the part after `<kind>:` (`ValueError` → `None`) and `datetime.strptime(..., '%Y-%m-%d %H:%M:%S')`; `read_lines` opens with `'r', encoding='utf-8', errors='replace'`.
- [ ] **Step 5:** Run → PASS.
- [ ] **Step 6:** Commit `feat: run-log line parser and fixtures` (after user OK).

### Task 2: Markdown readers and run-log → events

**Files:**
- Create: `monitor/mdfiles.py`, `monitor/events.py`, `tests/test_mdfiles.py`, `tests/test_events.py`

**Interfaces:**
- Consumes: `Line`, `read_lines` (Task 1).
- Produces:
  - `read_intake(p: Path) -> dict` keys `status` ('active'|'done'|'aborted'), `profile`, `location`, `title` (first `Request:` line), `delivered: list[str]`.
  - `read_active(docs_agent: Path) -> dict|None` keys `task, phase, session, started`.
  - `read_criteria(scope_or_plan: Path) -> int` (numbered items under `## Completion criteria` or `## Criteria`).
  - `read_verify(p: Path) -> list[str]` ('p'/'f' per `- <n>. PASS|FAIL`).
  - `read_plan(p: Path) -> dict` keys `estimate_k: int|None` (first `<n>k` on a line containing `token` in `## Estimate`), `approved_at: str|None`, `mockup: str|None`, `revisions: list[str]`.
  - `build_events(lines: list[Line]) -> Events` where `Events` has `log: list[dict]` (task JSON `log` items), `step_enter: list[(datetime, step, rev, session)]`, `gates: dict`, `waiting`, `running`, `revs`, `vfail`, `vfail_max`, `sstop`, `cost_usd: str|None`, `started: datetime|None`, `last: datetime|None`.

Mapping rules (decided here):
- `step:` → current step for following lines; no log item. Phase start (first `step:` of steps 1, 3, 5, 7) → `k='phase'`, `a='router'` for step 1 else `'recorder'`, `tx` = `"<① Define…> start"`.
- `call:`+`start:`+`stop:` → one `k='agent'` item; pair `start` to the latest unpaired `call` of the same agent; `stop` by `id`. `a` = agent without `my-agent:`; `model` = configured, `actual` = stop's actual alias (`claude-sonnet-…` → `sonnet`); `mm` = model ≠ actual; `live` = no stop yet; `tok` = `f"{round(tokens/1000)}k"`; `dur` = minutes; `c` = null (cost added in Task 5).
- `ask:`/`answer:` gate G1a/G1b/G3/E → one `k='popup'`, `a='gatekeeper'`; G2 → `a='perms'`. `sub` = answer choice; no answer yet → `waiting={gate,q}`. G2 with no answer and its agent already stopped → `sub='not run (denied?)'`.
- `revision:` → `k='rev'`, starts rev N; `revs` entries take `from` = step at that moment, `back` = next `step:` n.
- Gates: G1a ok if scope Confirmation present (profile general → 'skip'); G1b ok if plan approved; any pending ask on that gate → 'wait'; G2 ok if any G2 answer; G3 ok if intake status done; else 'todo'.
- `vfail` = trailing streak of verifier stops with result starting `FAIL`; `vfail_max` = longest streak; `sstop` = stops with `end` in (`partial`,`error`) for `coder|researcher|writer` in the current rev.
- `cost_usd` = sum over sessions of (last `cost:` − first `cost:`) as `"%.2f"`.

- [ ] **Step 1: Write failing tests:**
  - `test_intake_fields` (fixture `261023-hooks-notify-note` → status `done`, profile `research`, delivered `['docs/notes/claude-hooks-notify.md']`).
  - `test_criteria_and_verify` (hooks-notify: 5 and `['p']*5`).
  - `test_plan_estimate_and_approval` (cli-json-output: 600, approved `'2026-10-24 15:55'`).
  - `test_agent_pairing_and_live` (cli-json-output: coder-1 `live` True, coder-2 `tok=='84k'`, `res=='DONE'`).
  - `test_mismatch` (hooks-notify writer: `model=='sonnet'`, `actual=='haiku'`, `mm` True).
  - `test_waiting_and_g2` (synthetic lines: G3 ask without answer → `waiting=={'gate':'G3','q':…}`, `gates['G3']=='wait'`; G2 ask+answer → popup `a=='perms'`, `sub=='allowed'`).
  - `test_g2_denied_guess` (G2 ask, then that agent's stop, no answer → `sub=='not run (denied?)'`).
  - `test_revision_steps` (hitl-survey: two `revs`, rev1 `from==5`, `back==3`; events after revision have `r==1`).
  - `test_escalation_counters` (synthetic: FAIL, FAIL, ALL PASS, FAIL → `vfail==1`, `vfail_max==2`; flight-watch: `sstop==2`).
  - `test_pre_v019_log` (Review Focus 2: a run-log with only old-style lines and no `step:` → `build_events` returns `log==[]`, `step_enter==[]`, no exception).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_mdfiles tests.test_events -v` → FAIL.
- [ ] **Step 3:** Implement the readers and `build_events` with the rules above.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: markdown readers and run-log events` (after user OK).

### Task 3: Prices

**Files:**
- Create: `monitor/prices.py`, `prices.json`, `tests/test_prices.py`

**Interfaces:**
- Produces: `load_prices(path: Path) -> dict`; `cost(prices, model_id: str, usage: dict) -> float|None` (usage keys `input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens`; longest matching prefix; `None` if no prefix matches).

`prices.json` shape: `{"checked": "YYYY-MM-DD", "models": {"claude-opus-5": {"input": n, "output": n, "cache_write": n, "cache_read": n}, …}}`. Fill values from the current Anthropic pricing page when implementing and set `checked`.

- [ ] **Step 1: Write failing tests:** `test_prefix_match` (a model id `claude-sonnet-5-5-20260101` uses the `claude-sonnet-5` row), `test_unknown_model_none`, `test_cost_formula` (1M input + 1M output at 3/15 → 18.0).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_prices -v` → FAIL.
- [ ] **Step 3:** Implement `load_prices` and `cost`; write `prices.json` with current list prices and `checked`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: price table` (after user OK).

### Task 4: Main-session transcript usage

**Files:**
- Create: `monitor/transcript.py`, `tests/test_transcript.py`

**Interfaces:**
- Consumes: `cost` (Task 3), `Events.step_enter` (Task 2).
- Produces: `class TranscriptCache` with `usage_by_window(session: str, windows: list[(start: datetime, end: datetime, key)]) -> dict[key, dict[model, usage]]`. Finds `<root>/*/<session>.jsonl`; keeps a byte offset per file and only parses new complete lines on later calls; counts each assistant `message.id` once (last usage wins); timestamps from the entry's `timestamp` (UTC → local).

- [ ] **Step 1: Write failing tests:**
  - `test_window_sum` (fixture transcript: step 5 window of cli-json-output → expected input/output totals written in the fixture README).
  - `test_dedupe_message_id` (two lines same `message.id` → counted once).
  - `test_missing_session_returns_empty` (→ `{}`; Review Focus 3).
  - `test_incremental_read` (Review Focus 3: append 1 line to a temp copy, second call reads only from the stored offset — assert via a spy on `file.seek` called with the previous size, and totals include the new line).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_transcript -v` → FAIL.
- [ ] **Step 3:** Implement `TranscriptCache`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: main-session usage from transcript` (after user OK).

### Task 5: Task view and registry

**Files:**
- Create: `monitor/taskview.py`, `monitor/registry.py`, `tests/test_taskview.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `build_task(project: Path, task_dir: Path, prices, tcache, now: datetime) -> dict` (task JSON shape above). Wraps everything in try/except → `{"id","key","project","error"}`.
  - `class Registry(projects_file: Path)` with `list_tasks() -> list[dict]` (summaries: `id,key,project,profile,status,step,title,waiting`) and `get_task(key: str) -> dict|None`. Rebuilds a task only when the max mtime of its folder (incl. `run-log.md`) or its transcript size changed.

Rules: `files` = every file/dir in the task folder except `archive/` contents (one `archive/` row with a tree preview); `s` = step whose window contains the mtime; `pv` = first 4000 chars of text files ≤ 200 KB; missing `verify.md`/`review.md` → `todo` rows. `mocks` from current `plan.md` and each `archive/*/plan.md` (`r` from folder suffix `rev<N>` minus 1 for the archived one, `at` = that plan's approval). `deliver` from `intake.delivered` (`kind='file'`, size and mtime if the path exists, else `'–'`), `kind='none'` when aborted with nothing delivered. Agent `c` = `cost(prices, actual, usage)` with usage from the stop line's `in`/`out`/`cw`/`cr` (absent → `c=null`); `unpriced` lists actual models with `None` cost. `main`/`mainR` from `TranscriptCache` windows per `step_enter`; `mainApprox: true`.

- [ ] **Step 1: Write failing tests:**
  - `test_fixture_tasks_match_mockup`: for each of the 5 fixtures, `build_task` equals the mock-up values for `status, step, profile, gates, crit, vfail, sstop, revs` (literal expected dicts in the test).
  - `test_files_steps_and_todo` (cli-json-output: `verify.md` todo, `plan.md` at step 3).
  - `test_mocks_with_archive` (hitl-survey: 2 mocks, r 0 and 1).
  - `test_broken_task_isolated`: a fixture copy with an unreadable `intake.md` (`chmod 000`) → that task has `error`, others in `list_tasks()` don't.
  - `test_registry_skips_missing_and_expands_home` (Review Focus 4: `projects.txt` with `~/nonexistent  `, a blank line and a valid path → only the valid project's tasks).
  - `test_rebuild_only_on_change`: second `get_task` without changes does not call `build_task` (patch and count).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_taskview tests.test_registry -v` → FAIL.
- [ ] **Step 3:** Implement `build_task` and `Registry`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: task view and registry` (after user OK).

### Task 6: Server

**Files:**
- Create: `server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Registry`, `load_prices`, `TranscriptCache`.
- Produces: HTTP `GET /` → `web/index.html`; `GET /api/tasks` → `{"tasks": [summary…], "now": "HH:MM"}`; `GET /api/tasks/<key>` → task JSON or 404; any other method → 405. `main(argv)` parses `--port`, binds `127.0.0.1`, falls back 8765→8775, prints the URL.

- [ ] **Step 1: Write failing tests** (start server on port 0 in a thread with `MA_PROJECTS_FILE` = fixture list): `test_list`, `test_task_by_key`, `test_unknown_key_404`, `test_post_405`, `test_binds_localhost_only` (server address is `127.0.0.1`).
- [ ] **Step 2:** Run `python3 -m unittest tests.test_server -v` → FAIL.
- [ ] **Step 3:** Implement with `ThreadingHTTPServer`; JSON with `ensure_ascii=False`, `Cache-Control: no-store`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: local read-only server` (after user OK).

### Task 7: Web page from mock-up v22

**Files:**
- Create: `web/index.html` (copy of webapp-v22.html, then edit)

**Interfaces:**
- Consumes: `/api/tasks`, `/api/tasks/<key>` (Task 6).

Edits to the copy:
- Delete `const TASKS = [...]`, `const MOCKS = {...}`, and the "fake live updates" block (`T0`, `QUEUE`, `qi`, its `setInterval`). Title `my-agent monitor`; remove the `mock-up · fake data` tag.
- `let TASKS = []`; `mocksOf = t => t.mocks || []`; `st.task` keyed by `key` instead of `id` (`data-task`, `task-select`, `cur()`).
- `async function poll()`: fetch the list, fetch the selected task (and running ones for the sidebar rail), replace entries in `TASKS`, mark log items not seen before as `isNew`, then `renderAll()`; run every 2000 ms; on fetch error set the live text to `L('Server not reachable','서버에 연결할 수 없음')` and keep the last data. Live dot on only while any task is running.
- Effort tag: `etag(e.a)` → use `e.effort || EFFORT[e.a]`.
- Models table: main-session label `L('opus · main session (approx.)', 'opus · 메인 세션 (근사)')`; when `t.unpriced.length`, a note `L('Not in prices.json: ', 'prices.json에 없는 모델: ') + list`; `null` values render `–`.
- Task with `error`: Dashboard shows one card `L('Could not read this task', '이 작업을 읽을 수 없음')` + the error text; other tabs empty.
- Keep: language toggle, sidebar resize/collapse, Components window, replay keys, all effects, the BARS/CU/lastTyped guards against re-animation.

- [ ] **Step 1:** Make the edits; extract the `<script>` and run `node --check` → no error.
- [ ] **Step 2:** `python3 server.py` with `MA_PROJECTS_FILE=tests/fixtures/projects.txt MA_CLAUDE_PROJECTS=tests/fixtures/claude-projects`; open the page in Playwright; screenshot each tab for the 5 tasks into `~/dev/.playwright-mcp/`; compare with mock-up v22 screenshots — same values.
- [ ] **Step 3:** Console has 0 errors.
- [ ] **Step 4 (Review Focus 5):** In Log replay at position 5 with a file selected in Deliverables, wait 3 polls → `st.ri` still 5, `st.file` unchanged, `document.querySelectorAll('.tl-bar')` not re-animated (no `animation-name` running outside `body.entering`), sidebar width unchanged.
- [ ] **Step 5:** Commit `feat: web page wired to the API` (after user OK).

### Task 8: Live feed tool and README

**Files:**
- Create: `tools/feed-fixture.py`; Modify: `README.md`

**Interfaces:**
- Produces: `python3 tools/feed-fixture.py <task-dir-copy> --every 3` appends the remaining lines of a script (the mock-up's 5 queue steps for cli-json-output, in v0.19 format) one by one, writing `verify.md` at the matching point.

- [ ] **Step 1:** Copy the cli-json-output fixture to a temp dir, point a temp `projects.txt` at it, run the server and the feed tool.
- [ ] **Step 2:** In the browser: the Now tile moves 5 → 6 → 5 → 7 → 8, G3 shows `awaiting`, sidebar icon `?`, new console lines type in once, no re-animation of existing bars.
- [ ] **Step 3:** Partial-line check (Review Focus 1): the tool writes the last line in two chunks 1 s apart → no "error" card at any poll.
- [ ] **Step 4:** README: how to run (`python3 server.py`), env overrides, how to update `prices.json`, that my-agent v0.19 must be implemented for real data.
- [ ] **Step 5:** Commit `chore: live feed tool and README` (after user OK).

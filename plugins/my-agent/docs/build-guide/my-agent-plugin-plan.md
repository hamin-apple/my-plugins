# my-agent Plugin Skeleton Implementation Plan (steps 0–1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `~/dev/my-agent` into a loadable Claude Code plugin with the monitor inside, the run-log writers and record hooks, a SKILL.md skeleton with the general profile, and the probe results that steps 2–8 depend on.

**Architecture:** The repository is the plugin and a one-plugin local marketplace (§4.5.1). The record hooks (`subagent-log`, `permission-log`, `session-notice`) and the Recorder CLI (`run-log.py`) share one small library for finding `.active` and writing run-log lines. The monitor's existing parser (`monitor/monitor/runlog.py`, `events.py`) is the test oracle for every line they write. A temporary probe (raw-input logger hook, probe agent, probe skill) runs in headless sessions in `~/dev/labs/my-agent-sandbox/` and settles the unverified items before the SKILL.md skeleton is written.

**Tech Stack:** Python 3.13 standard library only (`json`, `shlex`, `unittest`, `pathlib`, `subprocess`, `http.client`), Markdown, Claude Code 2.1.310 (`claude plugin validate`, `claude -p --plugin-dir`).

**Spec:** `~/dev/my-agent/my-agent-architecture.md` v0.20 — §6 steps 0–1, with §2 F16–F18, §4.4, §4.5.1, §4.7–4.7.4, §4.8.2, §4.13. Monitor: `~/dev/my-agent/my-agent-monitor-design.md` v0.2 §6.1. Plugin facts: plugins-reference (fetched 2026-10-25).

## Global Constraints

- Repo root `~/dev/my-agent/`. `git init` in Task 1; **no commits** until the user asks (user decision 2026-10-25). Every "Commit" step below is "leave uncommitted".
- Python standard library only. Scripts start with `#!/usr/bin/env python3`. File names English, hyphens; a module that must be imported uses underscores (CLAUDE.md fallback).
- Hook commands are shell form: `python3 "${CLAUDE_PLUGIN_ROOT}"/l4-tools-guards/hooks/<script>.py <mode>`.
- Record hooks always exit 0, never set `onFailure`, write nothing and print nothing when no `.active` is found (§4.7.2 "실패해도 막지 않음", §4.5.1 "바로 끝냅니다").
- run-log line: `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`; quoting per §4.7.2 (double quotes; `\"` and `\\` inside; newline → one space). A line the monitor's `parse_line` cannot read is a bug.
- `.active` is four `key: value` lines: `task`, `phase`, `session`, `started` (§4.7.3). Lookup order: git root of `cwd` → `~/dev/agent-tasks/active-index.json` (§4.8.2).
- Monitor tests: `cd ~/dev/my-agent/monitor && python3 -m unittest`. Plugin tests: `cd ~/dev/my-agent && python3 -m unittest discover -s l4-tools-guards/tests`.
- `claude plugin validate --strict ~/dev/my-agent` passes at the end of every task that touches `.claude-plugin/`, `hooks.json`, a `SKILL.md` or an agent file.
- Nothing outside `~/dev/` is written. Plugin install, `~/.claude/settings.json`, and my-dev's frontmatter are Task 12 and need the user's approval in chat first.
- `~/dev/my-agent-monitor/` is left untouched (copy, not move).
- Probe sessions: headless `claude -p` only, in `~/dev/labs/my-agent-sandbox/`, `--model haiku`, items 1–6, 8, 11 plus the G2 `agent_id` question. Items 7 and 9 get a written procedure only; 10 (workflow) is deferred to step 6 (user decision).

## Review Focus

1. A session with no my-agent task (every session once the plugin is installed) fires every record hook — each exits 0 with no output and creates no file. Tests: Task 6 `test_no_active_*`, Task 7 `test_no_active_*`.
2. Broken input — malformed stdin JSON, a missing or half-written subagent transcript, an unwritable run-log — exits 0 and leaves a `log-error` line when the run-log is writable. Tests: Task 6 `test_bad_stdin`, `test_missing_transcript`.
3. A value with `"`, `\`, `'`, a newline, or empty, written by any writer, parses back to the same value (newline → space) with the monitor parser. Test: Task 4 `test_roundtrip_hard_values`.
4. `cwd` is a subfolder of the project, or a non-git folder that `active-index.json` maps to a location — the right `.active` is found; a stale index entry pointing at a missing folder is ignored. Test: Task 4 `test_find_*`.
5. A port in 8765–8775 held by another program (the old `~/dev/my-agent-monitor` server, or anything else) — `monitor-up.py` skips it, never stops it, and starts on the next free port. Test: Task 3 `test_skips_foreign_port`, `test_stop_ignores_foreign`.

---

## File Structure

```text
~/dev/my-agent/
├── .claude-plugin/plugin.json        # name, version, author, skills ["./"], agents (probe only, Task 9), hooks path
├── .claude-plugin/marketplace.json   # my-agent-dev → source "."
├── .gitignore
├── SKILL.md                          # /my-agent (Task 10; placeholder in Task 1)
├── skills/monitor/SKILL.md           # /my-agent:monitor (Task 3)
├── l1-orchestration/phases/{define,plan,build,accept}.md   # Task 10
├── l1-orchestration/profiles/general.md                    # Task 10
├── l4-tools-guards/
│   ├── lib/ma_active.py              # find .active (Task 4)
│   ├── lib/ma_logline.py             # format/append run-log lines (Task 4)
│   ├── scripts/run-log.py            # L1 Recorder CLI (Task 5)
│   ├── hooks/hooks.json              # Task 8
│   ├── hooks/subagent-log.py         # Task 6
│   ├── hooks/permission-log.py       # Task 7
│   ├── hooks/session-notice.py       # Task 7
│   ├── probe/                        # Task 9: probe-log.py, probe-hooks.json, agents/probe-worker.md, skill/SKILL.md, run-probes.sh, results.md
│   └── tests/test_*.py, tests/helpers.py
├── monitor/                          # copy of ~/dev/my-agent-monitor + health, prices override, monitor-up.py (Tasks 2–3)
├── maintenance-notes.md, feedback.md # Task 11
└── (existing) docs/, *.md design docs
```

---

### Task 1: Repository and empty plugin

**Files:**
- Create: `.gitignore`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `l4-tools-guards/hooks/hooks.json`, `SKILL.md` (placeholder)

**Interfaces:**
- Produces: a plugin that `claude plugin validate --strict` accepts; later tasks add keys to `plugin.json`.

- [ ] **Step 1:** `git init` in `~/dev/my-agent`. `.gitignore`: `.DS_Store`, `__pycache__/`, `.superpowers/`, `monitor/tests/fixtures/projects/`, `monitor/tests/fixtures/claude-projects/`, `monitor/tests/fixtures/projects.txt`. Confirm no `CLAUDE.md` at the repo root.
- [ ] **Step 2:** `plugin.json` = §4.5.1 manifest with `"version": "0.1.0"`, `"author": {"name": "jahoonjin"}`, `"skills": ["./"]`, `"hooks": "./l4-tools-guards/hooks/hooks.json"`, and **no `agents` key yet**. `marketplace.json` = §4.5.1 verbatim. `hooks.json` = `{"hooks": {}}`. `SKILL.md` = the §4.7.1 frontmatter **without `hooks:`** and a one-line body "Skeleton; filled in Task 10".
- [ ] **Step 3:** Run `claude plugin validate --strict ~/dev/my-agent` and `claude plugin validate --strict ~/dev/my-agent/.claude-plugin/marketplace.json`.
  Expected: `Validation passed` for both. If a warning remains, fix it and ledger the fix.
- [ ] **Step 4:** Leave uncommitted.

Rulings to ledger: `version`/`author` added against §4.5.1 "version은 두지 않습니다" — `--strict` fails on a missing version, and plugins-reference says `version` does not pin a plugin loaded in place from a local-path marketplace. Frontmatter `hooks:` left out until step 2 — `plan-approved-check.py` does not exist yet, and an `onFailure: block` hook pointing at a missing script would block every tool. `agents` omitted — validate fails on paths that do not exist; the 8 agents arrive in step 4.

### Task 2: Monitor inside the plugin, `/api/health`, prices override

**Files:**
- Create: `monitor/` (copy of `~/dev/my-agent-monitor/` without `.git`, `.superpowers`, `__pycache__`, generated fixtures)
- Modify: `monitor/server.py`, `monitor/monitor/registry.py`, `monitor/README.md`
- Test: `monitor/tests/test_server.py`, `monitor/tests/test_registry.py`

**Interfaces:**
- Produces: `GET /api/health` → `200 {"app": "my-agent-monitor", "root": "<absolute monitor folder>"}`. `registry.default_prices_file() -> Path`: `$MA_TASKS_DIR/prices.json` (default `~/dev/agent-tasks/prices.json`) when that file exists, else `<monitor>/prices.json`.

- [ ] **Step 1:** Copy with `rsync -a --exclude .git --exclude .superpowers --exclude __pycache__ ~/dev/my-agent-monitor/ ~/dev/my-agent/monitor/`. Run the monitor tests. Expected: `Ran 50 tests … OK`.
- [ ] **Step 2: Failing tests**
  - `test_health`: GET `/api/health` → status 200, JSON `{"app": "my-agent-monitor", "root": str(ROOT)}` where `ROOT` is the folder holding `server.py`.
  - `test_prices_override_used_when_present`: with `MA_TASKS_DIR` set to a temp dir containing `prices.json`, `default_prices_file()` returns that path.
  - `test_prices_default_when_absent`: with an empty `MA_TASKS_DIR`, it returns `ROOT / 'prices.json'`.
- [ ] **Step 3:** Run them. Expected: FAIL (404 / no attribute `default_prices_file`).
- [ ] **Step 4:** Implement the route and `default_prices_file()`; `Registry.__init__` uses it when `prices_file` is not given. README: run path `monitor/`, the override, `/api/health`.
- [ ] **Step 5:** Run the monitor tests. Expected: `Ran 53 tests … OK`.
- [ ] **Step 6:** Leave uncommitted.

### Task 3: `monitor-up.py` and `/my-agent:monitor`

**Files:**
- Create: `monitor/monitor-up.py`, `skills/monitor/SKILL.md`
- Test: `monitor/tests/test_monitor_up.py`

**Interfaces:**
- Consumes: `/api/health` (Task 2).
- Produces: CLI `monitor-up.py [--open | --no-open] [--ports A-B]`, `monitor-up.py status`, `monitor-up.py stop`. Exactly one line on stdout, always exit 0:
  - `monitor: http://127.0.0.1:<port>/ (started)` / `(running)`
  - `monitor: not running` (status), `monitor: stopped <port>` / `monitor: nothing to stop` (stop)
  - `monitor: not started (<reason>)`
- State: `$MA_TASKS_DIR/monitor.json` = `{"port", "pid", "root", "started"}`; log `$MA_TASKS_DIR/monitor.log`. Default ports `8765-8775`.

- [ ] **Step 1: Failing tests** (spawn the real `server.py` on test ports 8791–8794, `MA_TASKS_DIR` and `MA_PROJECTS_FILE` in a temp dir, `--no-open`; kill any spawned pid in `tearDown`):
  - `test_starts_when_none`: output matches `^monitor: http://127\.0\.0\.1:8791/ \(started\)$`; `monitor.json` has that port and a live pid; `/api/health` root equals the monitor folder.
  - `test_second_call_reports_running`: second call prints `(running)` with the same port and does not start a second process.
  - `test_skips_foreign_port`: a plain `http.server` on 8791 → started on 8792; the foreign server still answers.
  - `test_status_and_stop`: `status` prints the URL; `stop` prints `monitor: stopped 8791`, the pid is gone, `monitor.json` is removed; `status` then prints `monitor: not running`.
  - `test_stop_ignores_foreign`: `monitor.json` naming the foreign server's port → `monitor: nothing to stop`, foreign server alive.
  - `test_all_ports_busy`: every port in `--ports 8791-8791` foreign → `monitor: not started (no free port in 8791-8791)`, exit 0.
- [ ] **Step 2:** Run. Expected: FAIL (file missing).
- [ ] **Step 3:** Implement. Health check with `http.client`, timeout 0.5 s; port free = bind test on `127.0.0.1`; spawn `python3 server.py --port N` with `start_new_session=True`, stdout/stderr to `monitor.log`; wait up to 3 s for health. Open the browser (`open <url>`) only after a fresh start, or always with `--open`; never with `--no-open`.
- [ ] **Step 4:** `skills/monitor/SKILL.md`: frontmatter `name: monitor`, a one-line description, `disable-model-invocation: true`, `argument-hint: '[status|stop]'`. Body: run `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/monitor-up.py" --open` with no argument, `… status` or `… stop` for those arguments, then report the line in Korean. Anything else: say the arguments are `status` and `stop`.
- [ ] **Step 5:** Run the monitor tests (Expected: `Ran 59 tests … OK`) and `claude plugin validate --strict ~/dev/my-agent` (Expected: passed).
- [ ] **Step 6:** Leave uncommitted.

### Task 4: Shared library — `.active` lookup and run-log lines

**Files:**
- Create: `l4-tools-guards/lib/ma_active.py`, `l4-tools-guards/lib/ma_logline.py`, `l4-tools-guards/tests/helpers.py`
- Test: `l4-tools-guards/tests/test_lib.py`

**Interfaces:**
- Produces:
  - `ma_active.Active` (NamedTuple): `location: Path, task: str, phase: str, session: str, started: str, task_dir: Path, log: Path` (`log = task_dir / 'run-log.md'`).
  - `ma_active.find_active(cwd: str, tasks_dir: Path = None) -> Active | None`. `tasks_dir` defaults to `$MA_TASKS_DIR` or `~/dev/agent-tasks`.
  - `ma_logline.format_line(kind: str, fields: list[tuple[str, object]], now: datetime = None) -> str` (no trailing newline; `None` → `-`; `True`/`False` → `true`/`false`).
  - `ma_logline.append(log: Path, line: str) -> None` (one `write` of `line + '\n'`, creates the file, not the folder).
  - `ma_logline.log_error(active: Active, where: str, exc: BaseException) -> None` (writes `log-error: where=… error="…"`, swallows its own failure).
  - `helpers.py`: `make_task(root, task='261025-probe-task', phase='1', session='s-test') -> Path`, `parse(line) -> dict` (monitor `parse_line(...).f`), `run_hook(script, mode, payload: dict | str, cwd) -> CompletedProcess`, `REPO`.

- [ ] **Step 1: Failing tests**
  - `test_find_git_root`: `cwd` = `<repo>/src/deep` with `<repo>/.git/` and `<repo>/docs/agent/.active` → `Active.task == '261025-probe-task'`, `task_dir == <repo>/docs/agent/261025-probe-task`.
  - `test_find_git_worktree_file`: `.git` is a file (`gitdir: …`) → the folder holding it counts as the git root.
  - `test_find_via_index`: non-git `cwd` = `<tmp>/home/sub`, `active-index.json` = `{"<tmp>/home": "<tmp>/loc"}`, `.active` under `<tmp>/loc/docs/agent/` → found.
  - `test_find_stale_index`: the index maps to a folder with no `.active` → `None`.
  - `test_find_none`: no git root, no index → `None`; a `.active` without a `task:` line → `None`.
  - `test_roundtrip_hard_values`: for `q` in `['npm i x', 'say "hi"', 'a\\b', "it's", 'two\nlines', '', 'plain']`, `parse(format_line('ask', [('gate','G2'), ('q', q)]))['q'] == q.replace('\n', ' ')`.
  - `test_line_shape`: `format_line('step', [('n',5),('name','Execute'),('rev',0),('session',None)], datetime(2026,10,25,9,0,0)) == '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=-'`.
- [ ] **Step 2:** Run. Expected: FAIL (`ModuleNotFoundError: ma_active`).
- [ ] **Step 3:** Implement. Git root = nearest ancestor of `cwd` (itself included) with a `.git` entry; no `git` subprocess. Index keys match `cwd` or any ancestor, nearest first. Quote a value when it is empty or has whitespace, `"`, `'` or `\`.
- [ ] **Step 4:** Run. Expected: `OK`.
- [ ] **Step 5:** Leave uncommitted.

Ruling to ledger: `'` also forces quotes — the spec names only spaces and `"`, but an unquoted `'` makes `shlex` raise, and the monitor would drop the line.

### Task 5: `run-log.py` (L1 Recorder)

**Files:**
- Create: `l4-tools-guards/scripts/run-log.py`
- Test: `l4-tools-guards/tests/test_run_log.py`

**Interfaces:**
- Consumes: Task 4.
- Produces: CLI `run-log.py <kind> [key=value ...] [--model MODEL_ID] [--cwd DIR]`.
  - Kinds: `step ask answer revision cost stale base abort deliver resume rules-changed merge fix`. Anything else: exit 2.
  - `step` needs `n` and `name`. It gets `rev` (the latest `revision:` rev, else `0`) and `session` (`$CLAUDE_CODE_SESSION_ID`, else `.active` `session`) unless given.
  - `--model` adds `model=<id>`. When the id does not contain `opus`, it prints `MISMATCH: main session configured opus, actual <id>`.
  - After appending, it prints the appended line, then one line per `stop:` line written since the previous L1 line that carries `mismatch=1`: `MISMATCH: <agent> configured <c>, actual <a>`. An L1 line is any line whose kind is not `call`, `start`, `stop` or `log-error`, and is not `ask`/`answer` with `gate=G2`.
  - No `.active`: prints `run-log: no active my-agent task under <cwd>` and exits 1.

- [ ] **Step 1: Failing tests** (all go through the monitor oracle `helpers.parse` or `build_events`):
  - `test_step_fills_rev_and_session`: with a `revision: rev=1` line and `CLAUDE_CODE_SESSION_ID=s-9`, `run-log.py step n=3 name=Plan` → the last line parses to `n=3 name=Plan rev=1 session=s-9`; `build_events` has `step_enter[-1][1] == 3`.
  - `test_ask_answer_pair`: `ask gate=G1b q="계획을 승인할까요?"`, then `answer gate=G1b choice=승인` → `build_events(...).answered['G1b'] == '승인'`, `gates` has no `G1b: wait`.
  - `test_unknown_kind`: exit 2, nothing written.
  - `test_main_mismatch`: `--model claude-sonnet-5-5` → stdout has `MISMATCH: main session configured opus, actual claude-sonnet-5-5`.
  - `test_reports_subagent_mismatch_once`: a hook-written `stop: … mismatch=1` line after the last L1 line → the next call prints it, and the call after that does not.
  - `test_no_active`: exit 1, message, no file created.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the plugin tests. Expected: `OK`.
- [ ] **Step 5:** Leave uncommitted.

### Task 6: `subagent-log.py` (call / start / stop)

**Files:**
- Create: `l4-tools-guards/hooks/subagent-log.py`
- Test: `l4-tools-guards/tests/test_subagent_log.py`, `l4-tools-guards/tests/fixtures/agent-transcript.jsonl`

**Interfaces:**
- Consumes: Task 4. Hook stdin JSON (fields used: `cwd`, `tool_name`, `tool_input`, `agent_type`, `agent_id`, `agent_transcript_path`, `last_assistant_message`, `permission_mode`).
- Produces lines (§4.7.2):
  - `call: agent= model= effort= isolation= background=`. Written only when `tool_input.subagent_type` starts with `my-agent:`.
  - `start: agent= id= configured= effort= mode=`
  - `stop: id= actual= tokens= in= out= cw= cr= secs= result= end= [mismatch=1]`
- `configured`/`effort`: taken from the latest `call:` line for that agent if its value is not `-`, else from the definition file's frontmatter. The definition file is the `plugin.json` `agents` entry named `<name>.md`, under the plugin root `Path(__file__).resolve().parents[2]`. When it is not found, write `configured=unknown` and a `log-error` line. With `CLAUDE_CODE_EFFORT_LEVEL` set, write `effort=<v>(env)`.
- `stop`:
  - Usage is summed over assistant entries deduped by `message.id` (the last entry wins), as `in`/`out`/`cw`/`cr` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`). `tokens` is their sum.
  - `actual` is the most common model, ignoring `<synthetic>`. `secs` is the last minus the first entry timestamp.
  - `result` is the first non-empty line of `last_assistant_message`, cut to 80 characters (or `-`).
  - `end=error` when `last_assistant_message` is empty or the last assistant entry has `isApiErrorMessage: true`; otherwise `end=ok`.
  - `mismatch=1` when the model family (opus/sonnet/haiku/fable) of the `start:` line's `configured` differs from `actual`'s.

- [ ] **Step 1: Failing tests** (`run_hook` with real stdin; `tasks_dir` isolated with `MA_TASKS_DIR`):
  - `test_call_written_for_my_agent`: `{"tool_name":"Agent","tool_input":{"subagent_type":"my-agent:probe-worker","model":"opus","isolation":"worktree","run_in_background":true}}` → `call: agent=my-agent:probe-worker model=opus effort=- isolation=worktree background=true`.
  - `test_call_ignored_for_others`: `subagent_type: "Explore"` → nothing written, exit 0.
  - `test_start_uses_call_model_then_definition`: with the call above → `configured=opus`; with no call, a temp `plugin.json` + definition `model: haiku`, `effort: low` → `configured=haiku effort=low`.
  - `test_start_unknown_definition`: → `configured=unknown` and a `log-error` line.
  - `test_stop_from_transcript`: fixture with 3 assistant entries, two sharing one `message.id`, models `claude-haiku-5-5` → `tokens`, `in`/`out`/`cw`/`cr` equal the hand-computed sums from the fixture, `actual=claude-haiku-5-5`, `secs` equal to the fixture's span, `result=DONE`, `end=ok`; `build_events` gives the agent item `res == 'DONE'`, `live == False`.
  - `test_stop_mismatch`: `start` configured `sonnet`, transcript model `claude-opus-5-5` → `mismatch=1`.
  - `test_stop_without_start`: still written; no `mismatch`.
  - `test_missing_transcript`: path that does not exist → `stop` line with `tokens=-` etc., `end=error`, plus `log-error`, exit 0.
  - `test_bad_stdin`: `"not json"` → exit 0, nothing written (no `.active` known) and stdout empty.
  - `test_no_active_all_modes`: each mode with a `cwd` that has no task → exit 0, empty stdout, no file created.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. One top-level `try/except BaseException` → `log_error` when an `Active` was found, then `sys.exit(0)`.
- [ ] **Step 4:** Run the plugin tests. Expected: `OK`.
- [ ] **Step 5:** Leave uncommitted.

Ruling to ledger: `end=partial` (maxTurns) is not detectable from documented SubagentStop input; written as `ok` until probe extra P-c shows a signal — cost if wrong: E's "slice twice stopped" undercounts until then.

### Task 7: `permission-log.py` and `session-notice.py`

**Files:**
- Create: `l4-tools-guards/hooks/permission-log.py`, `l4-tools-guards/hooks/session-notice.py`
- Test: `l4-tools-guards/tests/test_permission_log.py`, `l4-tools-guards/tests/test_session_notice.py`

**Interfaces:**
- Consumes: Task 4.
- `permission-log.py ask` (PermissionRequest) writes `ask: gate=G2 agent=<a> id=<i> tool=<tool_name> q="<summary>"`:
  - `agent`/`id` come from the input's `agent_type`/`agent_id`. Without them, use the latest `start:` with no `stop:` if exactly one is open, else `agent=main id=-`.
  - `summary`: Bash → `command`; Edit/Write/Read → `file_path`; otherwise compact JSON of `tool_input`. Cut to 200 characters.
- `permission-log.py answer` (PostToolUse) writes `answer: gate=G2 id=<i> result=allowed`. It does this only when the newest G2 `ask:` with no later G2 `answer:` for its id has the same `tool` and `q` as this call; otherwise nothing.
- `session-notice.py` (SessionStart) prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <msg>}}` when `.active` is found, and nothing otherwise.
  - `msg` is §4.8.2 verbatim: "미완료 my-agent 작업 `<task>`, phase `<phase>`. 다른 일을 하기 전에 `/my-agent continue`를 실행할 것. `plan.md`에 승인 줄이 없으면 위임과 쓰기를 하지 말 것."
  - When `source == "fork"` and `.active` `session` ≠ the input `session_id`, `msg` = "원래 세션이 이 작업을 진행 중. 이 세션에서 이어받으려면 `/my-agent continue`".

- [ ] **Step 1: Failing tests**
  - `test_ask_bash_with_quotes`: Bash `command` `echo "a\b" > x` → line parses with `q == 'echo "a\\b" > x'`; `build_events(...).waiting == {'gate': 'G2', 'q': …}`.
  - `test_ask_guesses_running_agent`: one open `start:` → `agent=my-agent:coder id=<its id>`; two open → `agent=main id=-`.
  - `test_answer_matches_only_same_call`: after the ask, PostToolUse with the same Bash command → `answer: gate=G2 id=… result=allowed` and `build_events(...).answered['G2'] == 'allowed'`; a different command → nothing.
  - `test_answer_once`: a second identical PostToolUse → no second answer.
  - `test_no_active_ask_and_answer`: exit 0, empty stdout, no file.
  - `test_notice_text`: `.active` present, `source=startup` → JSON with the exact message above.
  - `test_notice_fork_other_session`: `source=fork`, different `session_id` → the fork message.
  - `test_no_active_notice`: → empty stdout, exit 0.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the plugin tests. Expected: `OK`.
- [ ] **Step 5:** Leave uncommitted.

### Task 8: `hooks.json`

**Files:**
- Modify: `l4-tools-guards/hooks/hooks.json`
- Test: `l4-tools-guards/tests/test_hooks_json.py`

**Interfaces:**
- Produces: the §4.5.1 table minus `scope-guard` (step 3), plus the two G2 rows from §4.7.2:

  | Event | matcher | command tail |
  |---|---|---|
  | PreToolUse | `Agent` | `subagent-log.py call` |
  | SubagentStart | `^my-agent:` | `subagent-log.py start` |
  | SubagentStop | `^my-agent:` | `subagent-log.py stop` |
  | PermissionRequest | (none) | `permission-log.py ask` |
  | PostToolUse | (none) | `permission-log.py answer` |
  | SessionStart | `startup\|resume\|clear\|compact\|fork` | `session-notice.py` |

  Each is `{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/l4-tools-guards/hooks/<script> <mode>", "timeout": 10}`; no `onFailure`.

- [ ] **Step 1: Failing test** `test_hooks_table`: load `hooks.json` and assert the six (event, matcher, command tail) rows exactly; every referenced script exists; no hook has `onFailure`.
- [ ] **Step 2:** Run. Expected: FAIL (empty hooks).
- [ ] **Step 3:** Write `hooks.json`.
- [ ] **Step 4:** Run the plugin tests (Expected: `OK`) and `claude plugin validate --strict ~/dev/my-agent` (Expected: passed, no unquoted-variable warning).
- [ ] **Step 5:** Leave uncommitted.

### Task 9: Probe (§6 step 0)

**Files:**
- Create: `l4-tools-guards/probe/probe-log.py`, `probe/probe-hooks.json`, `probe/agents/probe-worker.md`, `probe/skill/SKILL.md`, `probe/run-probes.sh`, `probe/results.md`; sandbox `~/dev/labs/my-agent-sandbox/` (git repo, one commit, `docs/agent/.active` + task folder for `261025-probe-task`)
- Modify (temporary, reverted in Step 7): `.claude-plugin/plugin.json` (`hooks` becomes an array adding `./l4-tools-guards/probe/probe-hooks.json`; `agents: ["./l4-tools-guards/probe/agents/probe-worker.md"]`; `skills: ["./", "./l4-tools-guards/probe/"]`)
- Modify: `my-agent-architecture.md` §2 (F19…), the [미확인] lines that a probe settled, §4.13 list

**Interfaces:**
- `probe-log.py <event>`: if `cwd` is under `~/dev/labs/my-agent-sandbox`, appends `{"event", "time", "input": <stdin JSON>, "env": {CLAUDE_PLUGIN_ROOT, CLAUDE_CODE_EFFORT_LEVEL}}` to `~/dev/labs/my-agent-sandbox/.probe/<event>.jsonl`; always exit 0.
- `probe-hooks.json`: probe-log on PreToolUse (all), PostToolUse (all), PermissionRequest, SubagentStart, SubagentStop, SessionStart.
- `probe-worker.md`: `name: probe-worker`, `model: haiku`, `effort: low`, `tools: Bash, Read`, `maxTurns: 3`, body "Run the command you are given, print its output, then reply DONE."
- `probe/skill/SKILL.md`: `name: probe-skill`, `disable-model-invocation: true`, frontmatter `PreToolUse` hook `python3 "${CLAUDE_PLUGIN_ROOT}"/l4-tools-guards/probe/probe-log.py skill-pretool`, body "Ask my-agent:probe-worker to run `pwd`, then stop."

- [ ] **Step 1:** Build the probe files and the sandbox. `claude plugin validate --strict ~/dev/my-agent`. Expected: passed.
- [ ] **Step 2:** `run-probes.sh` runs these from the sandbox. Each command is `claude -p --plugin-dir ~/dev/my-agent --model haiku --output-format stream-json --verbose "<prompt>" > .probe/run-<n>.json`, with every prompt naming the exact Agent call to make:

  | Run | Prompt asks for | Answers |
  |---|---|---|
  | r1 | Agent `my-agent:probe-worker` "run `pwd`" | probe 1 (Start/Stop fire), real `call:`/`start:`/`stop:` lines in the task run-log, probe-8 env, 4.7.2 #4 (effort in transcript) |
  | r2 | the same with `isolation: "worktree"` | probe 2 (`cwd` at Stop), probe 5 (agent's `pwd` is a worktree) |
  | r3 | `/my-agent:probe-skill` | probe 4 (`skill-pretool` lines with `agent_id`), probe 8 (did the frontmatter command run at all) |
  | r4 | background Agent "run `sleep 45; echo late`", then end the turn at once | probe 6 (SubagentStop for it? transcript `finished`) |
  | r5 | no prompt beyond `/my-agent:monitor status` (init event lists skills) | probe 11 (`skills`/`slash_commands` in the init event contain `my-agent:my-agent` and `my-agent:monitor`) |
  | r6 | Agent probe-worker "run `touch /tmp/ma-probe-x`" with `--permission-mode default` | G2 extra: PermissionRequest input has `agent_id`? |
  | r7 | Agent probe-worker with `maxTurns` exhausted (a 5-step task) | extra P-c: any SubagentStop field showing maxTurns |

  Expected: each run file ends with a `result` event; every `.probe/*.jsonl` has at least the lines its row needs (r4 and r7 may legitimately show the absence).
- [ ] **Step 3:** Check the real hooks' output from r1/r2: `run-log.md` of the sandbox task parses with the monitor and `build_events` shows the agent with `live == False`. Expected: yes for r1; record what r2 shows.
- [ ] **Step 4:** Write `probe/results.md`: one row per probe — question, run, evidence (file + field), answer. Items 7 and 9 get the manual procedure (from §4.13) instead; item 10 "deferred to step 6".
- [ ] **Step 5:** Update `my-agent-architecture.md`: add F19… for each confirmed fact with source `probe r<n>`; replace each settled `[미확인]` with the answer; adjust §4.13's list to what remains open.
- [ ] **Step 6:** Any probe answer that contradicts Tasks 4–8 (for example a worktree `cwd`, or `agent_id` present in PermissionRequest) gets a ledgered ruling and a RED→GREEN fix in the owning task's test file now.
- [ ] **Step 7:** Revert `plugin.json` to the Task 1–8 state (probe files stay in `probe/` as §4.7 says). `claude plugin validate --strict`. Expected: passed.
- [ ] **Step 8:** Leave uncommitted.

### Task 10: SKILL.md skeleton and the general profile

**Files:**
- Modify: `SKILL.md`
- Create: `l1-orchestration/phases/{define,plan,build,accept}.md`, `l1-orchestration/profiles/general.md`
- Test: `l4-tools-guards/tests/test_skill_md.py`

**Interfaces:**
- Consumes: `run-log.py` (Task 5), `monitor-up.py` (Task 3), probe answers (Task 9; probe 8 decides whether frontmatter hooks may use `${CLAUDE_PLUGIN_ROOT}`).
- Produces: SKILL.md per §4.7.1 (frontmatter still without `hooks:`) whose body has, in this order:
  1. Core rules in the first ~5,000 tokens (§4.7.1 table): popup rule, the 5 gates, the level table, the `.active` rule, "read the phase file when a phase starts".
  2. The arguments table.
  3. Intake:
     - task ID (§4.7.3)
     - the location popup (Q10)
     - the `.gitignore` popup
     - the `.active` four lines and `active-index.json`
     - `projects.txt`
     - `monitor-up.py`
     - `intake.md` with `Status: active`, `Location:` and a `my-agent:` commit line
     - `run-log.py step n=1 name=Intake`
  4. status, continue and abort (§4.8.2).
  5. Recorder rules: when to call `run-log.py`, `ask:` before every popup, `answer:` after.
  6. Phase and profile files are read with `${CLAUDE_SKILL_DIR}/l1-orchestration/…`.
- Research and dev profiles: Router says they are not built yet and offers the general profile or stopping (popup).
- `profiles/general.md` and the four phase files hold the §4.3/§4.4 general-profile rules:
  - no separate G1a; the scope summary goes at the top of `plan.md`
  - Plan Review may be skipped under 3 files
  - Verify and Review are never skipped
  - the G1b order with the mock-up pasted in full
  - G3 with the delivery table
  - E conditions
  - the agents to call by `my-agent:` name. They exist from step 4; the phase files say so in one line.

- [ ] **Step 1: Failing tests** `test_skill_md`:
  - frontmatter parses, `name == 'my-agent'`, no `hooks` key;
  - `SKILL.md` under 500 lines;
  - the first 20,000 characters contain the headings `질문 규칙`, `게이트`, `레벨`, `.active`;
  - every `${CLAUDE_SKILL_DIR}/…` and `${CLAUDE_PLUGIN_ROOT}/…` path in SKILL.md and the phase files exists;
  - every `run-log.py <kind>` mentioned uses a kind `run-log.py` accepts.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the files (Korean prose, as the design docs).
- [ ] **Step 4:** Run the plugin tests (Expected: `OK`) and `claude plugin validate --strict ~/dev/my-agent` (Expected: passed).
- [ ] **Step 5:** Smoke run in the sandbox (needs no agents):
  - `claude -p --plugin-dir ~/dev/my-agent --model haiku "/my-agent status"`. Expected: it reports the probe task and does not crash.
  - The same with `--output-format stream-json --verbose`, after removing `.active`. Expected: the init event lists `my-agent:my-agent`.
- [ ] **Step 6:** Leave uncommitted.

### Task 11: Maintenance notes and feedback file

**Files:**
- Create: `maintenance-notes.md` (L1–L4 sections; L4 holds:
  - the Q8 remaining risk (§4.8.2)
  - the `/plugin` Errors tab
  - `validate --strict`
  - the deferred `end=partial`
  - the probe items still open
  - the settings backup and rollback rule for Task 12)
- Create: `feedback.md` (header and an empty open list, format per §4.11)
- Modify: `my-agent-architecture.md` — the status line says the steps 0–1 implementation exists (date), and §6 marks steps 0–1 done with pointers to `probe/results.md`

- [ ] **Step 1:** Write the files. Then run the full checks: plugin tests, monitor tests, and `claude plugin validate --strict` for the plugin and the marketplace. Expected: all OK/passed.
- [ ] **Step 2:** Leave uncommitted.

### Task 12: Install and my-dev switch-off (approval-gated)

Stop here and ask the user in chat before each item. Nothing in this task runs without an explicit yes.

- [ ] `claude plugin marketplace add ~/dev/my-agent` and `claude plugin install my-agent@my-agent-dev` (writes `~/.claude/plugins/`, `~/.claude/settings.json`; back up `settings.json` first).
- ~~`disable-model-invocation: true` in `~/dev/my-dev/SKILL.md`~~ — removed 2026-10-25: my-dev is not part of the plugin (design v0.22). Install moves to after steps 2–7 (design §6 step 9).
- [ ] After install: new session → `/my-agent status` and `/my-agent:monitor status` both respond; `/plugin` Errors tab empty.

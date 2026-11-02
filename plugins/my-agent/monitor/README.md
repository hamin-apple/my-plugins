# my-agent monitor

A read-only local web page that shows every my-agent task: Dashboard, Architecture, Deliverables and Log replay.
Spec: `~/dev/my-plugins/plugins/my-agent/docs/build-guide/my-agent-monitor-design.md` (v0.4, 6.1: this folder lives inside the my-agent plugin). Plan: `~/dev/my-plugins/plugins/my-agent/docs/build-guide/my-agent-monitor-plan.md`. The monitor reads run-log lines and task files with the plugin's `l4-tools-guards/lib/ma_schema.py` (added to `sys.path` by `monitor/__init__.py`).

The monitor only reads. It never writes to a project's task folder (`<task_dir>`: the setting `task_dir`, default `.my-agent`; `docs/agent` is the former layout), a transcript, or the my-agent data folder.

## Run

```sh
cd ~/dev/my-plugins/plugins/my-agent/monitor
python3 server.py              # http://127.0.0.1:8765/ (if busy: 8766 … 8775)
python3 server.py --port 9000
```

my-agent starts it for you with `monitor-up.py` (Router at Intake, or `/my-agent:monitor`).
`GET /api/health` answers `{"app": "my-agent-monitor", "root": "<this folder>"}` so `monitor-up.py` can tell its own server from anything else on the port.

`GET /api/tasks` returns `{"tasks": [...], "now": "HH:MM"}` with one summary per task in `tasks`; each summary has `elapsed` (minutes, read-only, recomputed on every request for a running task, `null` if the task could not be read). The menu bar app's List uses it.

`GET /api/tasks/<key>/report` (the key is `<hash>/<task-id>`, so the path has three parts after `/api/tasks/`) returns the data of the Report tab as one JSON object with the keys `overview` (`background`, `purpose`), `timeline`, `criteria`, `units`, `review`, `plan_review` (per run with `found`/`fixed`), `decisions`, `gate_report`, `verdict`, `gate` (the waiting gate's payload), `takeaway` and `review_totals`. A key whose source file does not exist yet is `null` (a task with only `intake.md` has `overview` and `null` for every other key). An unknown key answers `404 {"error": "no such task"}`; only GET is accepted (other methods answer 405). It reads task files and writes nothing (`monitor/report.py`). `/api/tasks` and `/api/health` are unchanged.

`GET /api/tasks/<key>/prototype` returns the task's `prototype/index.html` as `text/html` (read-only; `nosniff` and a `sandbox allow-scripts` Content-Security-Policy). An unknown task answers `404 {"error": "no such task"}`, a task without the file `404 {"error": "no prototype"}`. The G1b gate view links to it.

### Opening the monitor

`monitor-up.py` opens a new window by default (about 1200x800), or a tab.

- Setting: `<data folder>/monitor-config.json`, `{"open": "window"}` or `{"open": "tab"}`. Missing, broken or unknown values mean `window`.
- Per run: `--window` or `--tab` beats the file. `--task <sha1 8>/<task-id>` opens the page with that task selected (`/#task=<key>`). `--open` always opens, `--no-open` never does.
- Autostart: `"autostart": false` in the same file (default true; missing, unreadable or any value other than JSON `false` means true) makes a call without `--open` print `monitor: not started (autostart off)` and start nothing, including the menu bar app's own `--no-open` launch. `--open`, `status`, `stop` and `set-browser` ignore it.
- Browser: `"browser": "default" | "safari" | "chrome"` in the same file (other keys are kept). Missing, broken or unknown means `default` (the system default browser, detected as below). `safari` always uses Safari (window: sized new window; tab: `open -a Safari`), `chrome` always uses Chrome (window: app window; tab: `open -b com.google.chrome`). If the chosen browser fails to open, the default browser's tab is used. Per run: `--browser default|safari|chrome` beats the file (an unknown value is ignored). `monitor-up.py set-browser <value>` writes the key; the menu bar app uses it.
- Window by default browser (`browser` is `default`): Safari opens a sized new Safari window, and a default browser that was never changed (no http entry in LaunchServices) counts as Safari. Chrome, Edge, Brave, Chromium and Vivaldi open an app window. Any other browser, an unreadable LaunchServices file, or Safari automation being refused opens a tab.
- Note: if Safari is not running and takes longer than 5 s to start, the window attempt times out and the tab fallback runs, so both a Safari window and a tab can appear.
- Not macOS: the page opens as one tab through Python `webbrowser.open`; `window`, `browser` and the Safari/Chrome rules above do not apply. If no browser opens, the one-line output is the same (`started`) and the page can be opened by hand.

Menu bar app: [../../my-agent-tray/macos/menubar/README.md](../../my-agent-tray/macos/menubar/README.md). Opening from Shortcuts: [shortcuts-review.md](shortcuts-review.md).

The server binds `127.0.0.1` only. The page polls every 2 s.

| Source | Default | Override |
|---|---|---|
| Project list (one path per line; my-agent writes absolute paths, a hand-added `~/…` line also works) | `<data folder>/projects.txt` | `MA_PROJECTS_FILE` |
| Main-session transcripts | `~/.claude/projects/*/<session>.jsonl` | `MA_CLAUDE_PROJECTS` |
| Prices | `<data folder>/prices.json` if it exists, else `l4-tools-guards/lib/prices.json` | `MA_TASKS_DIR` (the data folder) |

The data folder is the my-agent plugin setting `data_dir` (default `~/dev/log/my-agent`). Order: `MA_TASKS_DIR`, then the setting, then `~/dev/log/my-agent`; a leading `~` is expanded. `monitor-up.py --data-dir <folder>` takes the setting for the commands the my-agent skill runs, and passes the resolved folder to the server it starts. `monitor.json`, `monitor.log` and `monitor-config.json` sit directly in the data folder. A running server keeps the folder it started with: after changing the folder, run `/my-agent:monitor stop` and start the monitor again.

The main session's usage of a finished task is read from `main-usage.json` in its task folder when it exists (my-agent writes it at the end of a task with `usage-snapshot.py`) and costed with the current `prices.json`, because Claude Code deletes transcripts after `cleanupPeriodDays` (default 30 days). Without it, they come from the transcript, and turn into `–` once the transcript is gone.
The dashboard, Models table, step cards and replay show USD only (no token counts); the raw counts stay in the run-log `stop:` lines and `main-usage.json`.
Only `<task_dir>/*/` is listed. The server keeps the `task_dir` value `monitor-up.py` started it with; after you change the setting, run `/my-agent:monitor stop` once (`monitor-up.py` names a mismatch instead of reusing the server silently). A server started by the menu bar app uses the default. Finished tasks moved to `<task_dir>/.archived/` by `l4-tools-guards/scripts/archive-tasks.py` leave the list (architecture 4.8.2 "Task records over time").

Real data needs my-agent v0.19 (run-log `step:` lines, `ask:`/`answer:` lines, G2 hook, token split on `stop:`).
Older task folders still show, with steps as `–`.

## Prices

`l4-tools-guards/lib/prices.json` holds USD per 1M tokens, keyed by model-ID prefix (the longest prefix wins):
`input`, `output`, `cache_write` (5-minute TTL), `cache_read`. Edit it by hand when prices change and set `checked`.
The table is read through `l4-tools-guards/lib/ma_prices.py`, which `usage-snapshot.py` also uses.
A model with no row is costed as `–` and listed under the Models table.

## Test

```sh
python3 -m unittest
```

Fixtures under `tests/fixtures/` (the mock-up's five tasks) are regenerated on each run by `tests/fixtures/build_fixtures.py`.

Live check with a copy of one fixture:

```sh
S=$(mktemp -d) && cp -Rp tests/fixtures/projects/claude-sessions "$S"/ && echo "$S/claude-sessions" > "$S/projects.txt"
MA_PROJECTS_FILE="$S/projects.txt" MA_CLAUDE_PROJECTS=tests/fixtures/claude-projects python3 server.py --port 8780 &
python3 tools/feed-fixture.py "$S/claude-sessions/docs/agent/261024-cli-json-output" --every 3
```

## Report tab

The fifth tab, `5 Report`, shows one task on one page and is the gate view (the `5` is a label, not a shortcut). It fetches `/api/tasks/<key>/report` when opened and again on every poll while it is open, so a running task updates. Parts, in order:

- **Banner:** the verdict of a finished task (done in green with the commit and `N of M criteria pass · BLOCKER n/m · SHOULD-FIX n/m · NITPICK n/m · duration · $cost`; aborted in grey with the reason), or the waiting gate of a running task in red (an `ask: gate=G1a|G1b|G3` run-log line without a later `answer:`), or the current phase and step in orange. These are the dashboard's status colors (running, waiting, stopped). The numbers count up once per task, never on a poll.
- **Overview:** two labeled rows, Background and Purpose.
- **Key Takeaway:** three labeled lines, Scope / Delivered / Next, each with a sub-line of numbers.
- **Disclosure rows** with a one-line summary on the right: Completion criteria, Work units, Phase timeline (open), Follow-up, Decisions · review · cost. A click expands a row into the detail rows (evidence, files and tests, the gate marks and back-to points, the suggested improvements, request, cost per stretch, review findings, plan-review verdicts, decisions, gate report, task chain); open rows stay open across polls.
- **Gate view:** G1a shows the scope summary, criteria count and non-goals; G1b the plan summary, work units, estimate, Models rows and a link to the prototype (or "no prototype"); G3 the Verify and Review results with found/fixed counts and the open SHOULD-FIX and NITPICK items.

The hash `#task=<key>&tab=report` selects the task and the tab; `#task=<key>` alone still works. The tab uses the macOS system font stack; the other tabs are unchanged. The top bar has a theme switch (`Auto` / `Light` / `Dark`), remembered per browser, so the page can be checked in both modes.

A `null` key shows `Not written yet: <file>`. The counters and bars animate only when the tab is entered or the task changes, never on a poll; with `prefers-reduced-motion` the final values appear at once.

## Opening a local HTML file

`open-html.py <file> [--data-dir DIR]` sits next to `monitor-up.py`. It opens a local `.html`/`.htm` file with the same opener (`monitor/opener.py`), using the `open` (`window`/`tab`) and `browser` keys of `<data folder>/monitor-config.json`; on other platforms it opens one tab through `webbrowser`. It prints one line and always exits 0: `window`, `tab`, or `failed: <reason>` (`no such file <path>`, `not an HTML file <path>`, `no browser opened`, or an exception message). It writes nothing. my-agent uses it to show a prototype (`SKILL.md` "Gate reports").

`open-html.py --report <task folder> [--url] [--ports A-B] [--data-dir DIR]` opens the running monitor (it never starts one) on that task's Report tab, `http://127.0.0.1:<port>/#task=<key>&tab=report`, in a window or tab per `monitor-config.json`, and prints the same one line (`window`, `tab` or `failed: <reason>`, for example when the monitor is not running or does not list the task); exit 0. With `--url` it prints the URL and opens nothing. The health comparison is `monitor/locate.py`, shared with `monitor-up.py`. my-agent runs it at G1a, G1b and G3.

## Page

`web/index.html` is built from mock-up v22 by `tools/build-web.py` (string edits that fail loudly if the mock-up changed).
Edit the page directly for small fixes; re-run the script only when starting again from a new mock-up.

Status colors: running is orange, waiting for an answer is red, done is blue, stopped is dark gray, and passed steps are green. The file and agent activity marks (the live dot, the file being written, a running agent) are orange too. Log replay steps use the same colors as the Dashboard. The values are the `--st-*` variables in `web/index.html` and are the same as the menu bar app's (`../../my-agent-tray/macos/menubar/Sources/ListModel.swift`, `statusPalette`). Blinking is unchanged.

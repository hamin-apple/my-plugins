# my-agent monitor

A read-only local web page that shows every my-agent task: Dashboard, Architecture, Deliverables and Log replay.
Spec: `~/dev/my-plugins/plugins/my-agent/docs/build-guide/my-agent-monitor-design.md` (v0.4, 6.1: this folder lives inside the my-agent plugin). Plan: `~/dev/my-plugins/plugins/my-agent/docs/build-guide/my-agent-monitor-plan.md`. The monitor reads run-log lines and task files with the plugin's `l4-tools-guards/lib/ma_schema.py` (added to `sys.path` by `monitor/__init__.py`).

The monitor only reads. It never writes to a project's `docs/agent/`, a transcript, or the my-agent data folder.

## Run

```sh
cd ~/dev/my-plugins/plugins/my-agent/monitor
python3 server.py              # http://127.0.0.1:8765/ (if busy: 8766 … 8775)
python3 server.py --port 9000
```

my-agent starts it for you with `monitor-up.py` (Router at Intake, or `/my-agent:monitor`).
`GET /api/health` answers `{"app": "my-agent-monitor", "root": "<this folder>"}` so `monitor-up.py` can tell its own server from anything else on the port.

`GET /api/tasks` returns `{"tasks": [...], "now": "HH:MM"}` with one summary per task in `tasks`; each summary has `elapsed` (minutes, read-only, recomputed on every request for a running task, `null` if the task could not be read). The menu bar app's List uses it.

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
Only `docs/agent/*/` is listed. Finished tasks moved to `docs/agent/.archived/` by `l4-tools-guards/scripts/archive-tasks.py` leave the list (architecture 4.8.2 "Task records over time").

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

## Page

`web/index.html` is built from mock-up v22 by `tools/build-web.py` (string edits that fail loudly if the mock-up changed).
Edit the page directly for small fixes; re-run the script only when starting again from a new mock-up.

Status colors: running is orange, waiting for an answer is red, done is blue, stopped is dark gray, and passed steps are green. The file and agent activity marks (the live dot, the file being written, a running agent) are orange too. Log replay steps use the same colors as the Dashboard. The values are the `--st-*` variables in `web/index.html` and are the same as the menu bar app's (`../../my-agent-tray/macos/menubar/Sources/ListModel.swift`, `statusPalette`). Blinking is unchanged.

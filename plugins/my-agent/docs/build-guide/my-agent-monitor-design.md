# my-agent monitor design

- Status: design v0.3 (2026-10-28, aligned with architecture v0.27: code location corrected; 5.2 line format gains `unit=`, the `revision` state, `Scope change`, and the back-to-Execute `back=`/`archive=`; the monitor reads through L4 `lib/ma_schema.py`). v0.2 (2026-10-25). Built after v0.1 was approved (`~/dev/my-agent-monitor/`). v0.2 adds the decision to put it in the plugin (section 6.1, architecture v0.20 Q14). The same day, probe results (architecture v0.21) added `session=` to `start:` and `mode=` and `effort=` to `stop:`. The monitor does not need to read these fields.
- Code location: `monitor/` inside the plugin (`~/dev/my-plugins/plugins/my-agent/monitor/`, section 6.1). The first build lived in `~/dev/my-agent-monitor/`.
- Screen reference: mock-up v22 `~/dev/my-agent/.superpowers/brainstorm/29416-1792798606/content/webapp-v22.html`
- Related document: `my-agent-architecture.md` v0.19. The "changes on the my-agent side" in section 7 are applied in v0.19.

## 1. What it is and why it is needed

my-agent runs several subagents in parallel through 4 phases, 8 steps and 5 gates (G1a, G1b, G2, G3, E). Progress is spread over the files in the task folder (`<project>/docs/agent/<task-id>/`) and `run-log.md`, so a terminal alone does not show the following at a glance.

1. Which step it is in now, who is working, and whether it is waiting for the person's answer
2. Which components of the my-agent architecture (L1~L4) were used
3. The deliverable, the interim deliverables (mock-up), and the work files
4. Replaying the per-step record for each task-id

The monitor shows these four things as a local web page on the Mac. **It only reads.** It does not interfere with my-agent's progress or change files.

## 2. Goals · non-goals · failure conditions

**Goals**

- Show a running task with changes reflected within 2 seconds.
- Replay finished and aborted tasks on the same screen (record replay).
- Show tokens, time and cost (estimate) per step and per model.

**Non-goals**

- Actions such as answering gates or starting and aborting tasks. The person answers only in the terminal popup.
- Sharing with other devices or other people, remote access
- Exact billed amounts. Cost is only an estimate at list price and the statusline value (for reference).
- Support for other operating systems

**Failure conditions (counted as failure even if it works)**

- The monitor writes anything to, or locks, the task folder, run-log or transcript and so affects my-agent's progress
- The whole screen stops when one task cannot be read because its record files differ slightly in format. Only that task should show "read error", and the rest should still show.
- A value on screen differs from the record. A value not in the record is not made up; it stays `–`.

## 3. Constraints

- macOS, with Chrome as the reference browser
- The server listens only on `127.0.0.1` and uses only the Python 3 standard library. There must be no dependencies to install.
- The frontend is one HTML file (+ JS/CSS files if needed), with no build step. The web font (IBM Plex) loads from Google Fonts; offline, system fonts take its place.
- `~/dev/tools/claude-sessions` is read-only. The monitor does not reuse its code (the price table is its own file).
- The server writes no files. Only the launch script `monitor-up.py` writes `<data folder>/monitor.json` and `monitor.log` (section 6.1). The data folder is the plugin setting `data_dir` (default `~/my-agent`; `$MA_TASKS_DIR` wins; architecture 4.7).

## 4. Screen (fixed by mock-up v22)

Mock-up v22 is the reference for the screen. The build starts from the mock-up's HTML/CSS/render code and replaces only the fake data (`TASKS`, `MOCKS`, the fake live updates `QUEUE`) with the server API.

**Common**

- Top bar: `my-agent monitor`, live indicator, task selector (narrow screens), EN/Korean switch
- Left sidebar: task list (All/Running/Done/Aborted filters, an 8-cell mini bar of steps)
  - Drag the edge to resize (200~480px); double-click to reset
  - Collapse/expand. Collapsed, each task shows only a status icon (● running, ? waiting for an answer, ✓ done, ■ aborted)
- Task header: task-id, status, task title, profile · path · start · elapsed
- 4 tabs: Dashboard / Architecture / Deliverables / Log

**Language**

- Titles (tabs, sections, tile names, table headers, phase · step · gate names, level names, component description lines) are always in English.
- Other UI text can switch between EN and Korean. The default is EN; the choice is saved in the browser.
- Text read from the records (task title, run-log content, deliverable names, mock-up, file contents) is not changed.

**1 Dashboard**

- Left: step list. The 8 steps under the 4 phases as one-line cards (time · tokens · cost), gate lines (passed / awaiting / pending), rev chips (`rev0 · archived`, `rev1 · current`) and step marks (`↺ rev1`, `from rev0`)
  - Clicking a step jumps to that step's first record in the Log tab replay.
- Right: 6 tiles in 2 columns. Order: Now, Elapsed / Criteria, Tokens / Escalation, Cost
  - Now: the current step and the running subagents (model, effort); when waiting for an answer, that gate
  - Criteria: passed / total, one cell per criterion
  - Tokens: used / estimated, progress bar (the estimate is for reference, not an E condition)
  - Escalation (E): consecutive Verify FAIL n/3, slice stops n/2. Normal / Caution / E raised from these two values only
  - Cost: estimated total per model and the statusline value (small, labeled "statusline")
- Bottom: Models table (calls, tokens, time, cost per model, including the main session row), MISMATCH warning

**2 Architecture**

- 4 components per level L1~L4. Those used in this task are bright, with a record count, and a dot if running now
- Names are lowercase: L1 router · orchestrator · gatekeeper · recorder, L4 tools · hooks · permissions · scripts
- L2 and L3 cells have two lines (role / model · effort)
- Clicking one shows, on the right, a description, model and effort, and its records in this task

**3 Deliverables**

- Left: final deliverable, interim deliverables (the mock-up approved at G1b; with several revs, a line-by-line `⇄ compare`), work file tree
- Right: preview of the clicked file (fixed)

**4 Log**

- Header line: Replay / Parallel timeline switch next to `4 · Log`; at the far right, `run-log.md · task-id` and `↗ Components`
- Replay: first/previous/next/auto play, speed 0.5×~4×, slider, keyboard (← → Space Home End)
  - Step list on the left, console (level-colored tags) and event cards (model, effort, MISMATCH, the mock-up at G1b time) in the middle, the work files at that moment on the right (newly written files get a typing effect)
- `↗ Components`: opens "components at this moment" in a separate window. It follows the replay position and remembers the window size and position.
- Parallel timeline: subagent calls as bars (model color, `×N` for N rows, red border for MISMATCH), step bands and gate marks, maximum concurrency. Clicking a bar jumps to that moment in the replay

**Effects**

- Everything in the mock-up: counting-up numbers, progress bars, blinking running dots, screen transition animations, task-id letter scramble, and so on
- Live updates do not re-animate what is already drawn (a problem fixed in mock-up v13).
- With `prefers-reduced-motion`, effects are off.

## 5. Data sources

| Screen value | Read from |
|---|---|
| Projects to watch | project list file (5.1) |
| Task list, status, title, profile, location, start | `intake.md` (`Status:`, `Profile:`, `Location:`, the request line), folder name (task-id) |
| Running task | `docs/agent/.active` (task, phase, session, started) |
| Step entry, time per step | run-log `step:` lines (5.2, changes on the my-agent side) |
| Subagent calls · model · effort · tokens · time · result · MISMATCH | run-log `call:` / `start:` / `stop:` lines (architecture section 4.7.2) |
| Main session tokens | main transcript (5.3) |
| Gates, popup questions and choices | run-log popup lines, `scope.md ## Confirmation`, `plan.md ## Approval` |
| rev | run-log `revision:` lines, `plan.md`/`scope.md ## Revisions`, `archive/` |
| Criteria | `scope.md` completion criteria (for the general profile, the scope summary at the top of `plan.md`), `verify.md` verdicts |
| Escalation | verifier `stop:` results in the run-log (consecutive FAIL), worker stop records |
| Estimated tokens | `plan.md ## Estimate` |
| Cost estimate | tokens × `prices.json` (5.4) |
| Cost statusline | run-log `cost:` lines |
| File tree, write times, preview | task folder files and their modification times |
| Mock-up and version compare | `plan.md ## Mock-up`, `archive/*/plan.md ## Mock-up` |
| Final deliverable | `Delivered:` in `intake.md`, run-log `deliver` lines |

### 5.1 Project list

- File: `<data folder>/projects.txt` (`$MA_PROJECTS_FILE` overrides the file). One project path (task location) per line
- After my-agent sets the task location in Intake, it adds a line if the path is not listed. It never removes lines.
- For each line the monitor looks for `<path>/docs/agent/*/intake.md`. If the path is gone, it skips it.

### 5.2 run-log lines (the contract the monitor reads)

The monitor's parser interprets only the lines below and ignores lines it does not know. Line reading uses `split_line` from L4 `lib/ma_schema.py` as is (architecture section 4.7 "single source of formats"). This format also goes, with the same content, into section 4.7.2 of the architecture document (section 7), and `run-log.py`, `subagent-log.py` and the monitor test against the same example file (fixture).

**Line format:** one record per line. `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>`. A value with spaces is wrapped in double quotes. Inside a value, `"` is written `\"` and `\` is written `\\`; line breaks become spaces (architecture section 4.7.2). A line without rev takes the rev of the latest `revision:` line (rev0 if none).

```text
2026-10-24 15:56:02 step: n=5 name=Execute rev=0 session=4f2a…
2026-10-24 15:56:10 call: agent=my-agent:coder model=- effort=- isolation=worktree background=true unit=u1
2026-10-24 15:56:11 start: agent=my-agent:coder id=a81c… configured=sonnet effort=medium session=4f2a…
2026-10-24 16:04:40 stop: id=a81c… unit=u1 actual=claude-sonnet-5-5 tokens=84213 in=61020 out=9870 cw=8113 cr=5210 secs=509 result=DONE end=ok mode=auto effort=medium
2026-10-24 16:01:15 ask: gate=G2 agent=my-agent:coder id=a81c… tool=Bash q="npm i fast-json-stable-stringify"
2026-10-24 16:01:31 answer: gate=G2 id=a81c… result=allowed
```

| Line | Writer | Fields the monitor uses |
|---|---|---|
| `step:` **(new)** | run-log.py, each time a step is entered | time, step number (1~8), rev, session ID. A back-to-Execute line has `back=` (reason) and `archive=` (archived verdicts) |
| phase entry | run-log.py | time, phase |
| `ask:` / `answer:` **(split)** | run-log.py | gate (G1a/G1b/G3/E), question, choice. An `ask:` with no `answer:` after it yet means "waiting for an answer" |
| `ask: gate=G2` / `answer: gate=G2` **(new)** | plugin hooks `PermissionRequest` / `PostToolUse` | requesting agent, tool, input summary, `result=allowed`. If there is no `answer:` by the time that agent ends, show "not run (denied?)" |
| `call:` / `start:` / `stop:` | subagent-log.py | agent_type, agent_id, work unit (`unit=`), model (expected and actual), effort, isolation, tokens, time, first line of the result, MISMATCH, how it ended (`end=ok|partial|error`). Consecutive FAILs count verifier lines whose `result=` starts with `Verdict: FAIL` and restart when the rev changes; worker stops count per (rev, `unit=`) |
| `revision:` | run-log.py | rev number, what changed, archive folder. `before=G1b` means a plan rewrite before approval (rev unchanged). A `state=pending` line and the `state=done` line with the same rev merge into one revision |
| `fix:` | run-log.py | what was fixed. `what="Scope change: …"` shows as an adjustment within the approved scope |
| `cost:` | run-log.py | `session=`, `usd=` (cost_usd) |
| `stale:`, `abort`, `deliver`, `resume`, `base:`, `log-error` | architecture document | for display |

### 5.3 Main session tokens

- Find `~/.claude/projects/*/<session>.jsonl` from the session ID in the `step:` line.
- Sum the usage of the assistant responses (input, output, cache write, cache read) in that step's span (this `step:` line's time ~ the next `step:` line's time) per model. If one response is split over several lines, count it once by response ID.
- If the same session did work unrelated to my-agent, that share is included too. The Models table on screen shows the main session row as "opus · main".
- A finished (done or stopped) task with `main-usage.json` in its task folder is read from that file instead (the same sums, saved by L1 at the end of the task with `usage-snapshot.py`; architecture 4.8.2 "Task records over time"). Claude Code deletes transcripts after `cleanupPeriodDays` (default 30 days), so without the file the numbers would turn into `–` later. The window and line rules live in L4 `lib/ma_usage.py`, which the monitor and the snapshot share.
- If neither the file nor the transcript is found, the main session row stays `–`.

### 5.4 Price table

- File: `prices.json` in the monitor folder (default). If `<data folder>/prices.json` exists, that one is used (section 6.1). For each model ID prefix (e.g. `claude-opus-5`): input, output, cache write and cache read prices (USD / 1M tokens) and the date checked
- The person updates it by hand. A model not in the table gets cost `?`, and one line "model not in the price table" appears below the Models table.

## 6. Structure

```text
~/dev/my-plugins/plugins/my-agent/monitor/
├── server.py          # http.server, 127.0.0.1, read-only JSON API + static files
├── monitor-up.py      # check whether it is already up, start it · open the window (section 6.1)
├── monitor/           # reads the project list, intake, run-log, transcript and file tree into the task model (runlog · events · mdfiles · taskview etc.; imports L4 lib/ma_schema)
├── web/index.html     # the screen, started from mock-up v22
├── prices.json
├── menubar/           # menu bar app (optional)
├── tools/             # screen generator (running it again drops direct edits to web/index.html)
├── tests/fixtures/    # fake tasks built in the real output formats (build_fixtures.py)
└── README.md          # how to run
```

- **API:** two endpoints are enough: the task list (summary) and one task (full model). The screen fetches again every 2 seconds.
- **Read cost:** only tasks whose file modification times changed are read again. Transcripts are read on from the last read position.
- **Run:** `python3 server.py`, then open it in the browser. The port is 8765; if it is in use, the next number up to 8775.

### 6.1 Putting it in the plugin and auto start (v0.2)

The detailed behavior is in section 4.7.4 of the architecture document. Only the changes on the monitor side are listed here.

- **Location:** the code moved to `monitor/` inside the plugin (now `~/dev/my-plugins/plugins/my-agent/monitor/`). The reading code was renamed from `reader/` to the `monitor/` package.
- **`GET /api/health`:** returns `{"app": "my-agent-monitor", "root": <absolute path of the monitor folder>}`. The launch script uses it to recognize a server that is already up.
- **`monitor-up.py`:** if already up, prints only the URL; otherwise starts the server on a free port. Takes `--open`, `--no-open`, `--window`, `--tab`, `--task <key>`, `status`, `stop`. The open mode (`window`/`tab`) is chosen from the option, then `<data folder>/monitor-config.json`, then the default `window`. The browser (`default`/`safari`/`chrome`) is chosen from the `--browser` option, then `browser` in the config file, then the default `default` (detects the default browser); `monitor-up.py set-browser <value>` rewrites only `browser` in the config file. If the chosen browser does not open, a tab in the default browser is used instead. It exits 0 in every case.
- **Task link:** opening `/#task=<key>` (key is `<8-char sha1>/<task-id>`, URL-encoded) selects that task. If the key is wrong or the task is finished, the usual selection rules apply.
- **Menu bar app:** a small app in `monitor/menubar/` shows the number of running tasks and a line per task, and runs `monitor-up.py` (`monitor/menubar/README.md`).
- **Price table override:** if `<data folder>/prices.json` exists, it is used instead of `prices.json` in the monitor folder.
- **Who starts it:** the my-agent Router right after it sets the task location in Intake, and the person calling `/my-agent:monitor` directly.
- **Lifetime:** the server stays up after the session ends. `/my-agent:monitor stop` turns it off.

## 7. Changes on the my-agent side (applied in architecture document v0.19)

1. **Project list registration:** after setting the task location in Intake, add it to `<data folder>/projects.txt` if missing (section 4.8.2 "task location")
2. **`step:` line:** run-log.py records time, step, rev and session ID each time a step (1~8) is entered (the L1 Recorder row of the table in section 4.7.2)
3. **Split popup records in two:** `ask:` right before the popup shows, `answer:` after the answer comes. Today the question and choice are recorded in one line, so there is no record while waiting for the answer (the L1 Recorder row of the table in section 4.7.2)
4. **Line format:** put the format from 5.2 into section 4.7.2
5. **G2 record hooks:** add `PermissionRequest` (→ `ask: gate=G2`) and `PostToolUse` (→ `answer: gate=G2 result=allowed`, only when the tool and input match the earlier G2 `ask:`) to the plugin hooks. The matcher and the `.active` lookup are the same as subagent-log, and they never block on failure (exit 0). A denial cannot be seen directly, so it is not recorded (section 4.4 G2, section 4.7.2)
6. **Worker stop records:** so that E's "same work unit stopped twice" can be counted (from v0.3 the unit is told apart by `unit=`), the `stop:` line carries `end=ok|partial|error` (partial when maxTurns is hit; then there is no SubagentStop, so the sweep writes it from the meta file, architecture F22) (sections 4.7.2, 4.8)
7. **Verdict file format:** `verify.md` has one `PASS`/`FAIL` line per criterion number; `scope.md` completion criteria are a numbered list (section 4.3 or 4.4)

## 8. What the user decided

- Screen: mock-up v22 (all of section 4)
- Mac local web page, Python server
- Tokens removed from the E conditions (architecture v0.17), effort fixed per agent (v0.18)
- Finding projects: my-agent registers them in the list
- 8 steps: the Recorder writes `step:` lines
- Main session tokens: the monitor reads the transcript
- Price table: the monitor's own `prices.json`
- G2: recorded by hooks (`PermissionRequest` + `PostToolUse`). A denial is shown as an inference
- Code in `~/dev/my-agent-monitor/`, this document in `~/dev/my-agent/`
- (v0.2) Move it into `monitor/` inside the plugin; it starts along with my-agent (when the Router starts a task). Also keep a `/my-agent:monitor` skill for manual start

## 9. What I decided (please confirm)

- The project list file is at `<data folder>/projects.txt`, because that folder already holds `active-index.json` (v0.3: the data folder replaced the earlier fixed folder under `~/dev`; the server gets it from `monitor-up.py` in `CLAUDE_PLUGIN_OPTION_DATA_DIR`, the menu bar app from its login item)
- A task whose records are malformed shows "read error" for that task only; the rest keep showing
- The server uses only the standard library; the frontend has no build
- 2-second polling (instead of file watching), because it is simple and the Mac's built-in Python is enough
- The run-log line format (5.2), and splitting popup records into `ask:`/`answer:`, because showing "waiting for an answer" needs a record at question time
- (v0.2) Recognize a server already up by `root` in `/api/health`, and skip ports other programs use
- (v0.2) Open the browser only when the server was newly started, so that a new tab does not open every time a task starts
- (v0.2) Keep the server up after the session ends, because several sessions share one server and it does almost nothing once the screen is closed
- (v0.2) Keep the state file, the log and the price table override in the data folder (a fixed folder under `~/dev` at v0.2), because that is where `projects.txt` lives and no plugin files need to change

## 10. Left to the builder

- API paths and JSON shape, port number
- run-log parser structure, as long as it keeps the 5.2 contract and the fixture tests
- How transcripts are read on and cached
- How many files to split the mock-up code into

## 11. Testing

- Build the mock-up's 5 fake tasks (running dev, research with a rev1 revision, a finished task with a MISMATCH, a finished general profile task, aborted by E) in `tests/fixtures/` in the real folder layout, and check that the screen values match the mock-up.
- Check live updates with a script that appends run-log lines to the running task fixture every few seconds (including that animations do not run again).
- With one deliberately broken run-log line and a missing transcript, check that only that task shows an error.
- After my-agent is built, follow one real task to the end.

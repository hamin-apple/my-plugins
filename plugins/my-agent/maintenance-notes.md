# my-agent maintenance notes

For each level, record "current state · dependence on external behavior · points to watch" (design doc section 4.11). Add each fix to the section of its level, with the date.

## L1 orchestration (`SKILL.md`, `l1-orchestration/`)

**Current state (2026-10-25)**

- `SKILL.md`: core rules (question rules, gates, levels, `.active`, data and instructions, phase files), arguments, Intake, status, continue, abort, Recorder rules, failure handling, in-flight revision.
- `phases/define.md` · `plan.md` · `build.md` (with workflow rules) · `accept.md` (with G3 in the dev profile), `profiles/general.md` · `research.md` · `dev.md`. The Router reads the request and picks the profile (does not ask), unless the call starts with a profile flag (`--general`, `--research`, `--dev`).
- 2 frontmatter hooks: `plan-approved-check.py` (G1b), `verdict-fresh-check.py` (verdict freshness before a commit or a deliverable copy). They apply only after `/my-agent` has actually run (F28).
- SKILL.md and the phase files call the check before anything leaves (`secret-scan.py`) and the retrospective. The retrospective (`accept.md`) runs in this order: tally (`gate-report.py tally` → `gate-tally.md`), interpretation by `my-agent:gate-analyst` (→ `gate-report.md`), copy (`gate-report.py copy`), raising improvements (`feedback.py`) (2026-10-26).

**Dependence on external behavior**

- After compaction, only the first 5,000 tokens of the skill are attached again. Keep the core rules within the first 16,000 characters of SKILL.md (about 4,000 tokens of English) (`test_skill_md` checks this).
- `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` in the skill body are replaced, but variables inside phase files read with Read are not. SKILL.md tells L1 to replace them.
- `$CLAUDE_CODE_SESSION_ID` is available in the main session's Bash (F27). The `session:` in `.active` and the `step:` lines use this value.

**Points to watch**

- Write run-log commands in the full form `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" <kind> key=value…`. `test_skill_md` actually runs every command.
- L1 rules fixed during interactive validation (2026-10-25): popups in phase and profile files use the choices as written (a Sonnet L1 changed the order of the dev NIT popup). Do not put `$(` or backticks in commands that contain `git` (the verdict hook cannot tell whether it is a commit). L1 runs on the session model (F13). `run-log.py` reads `model=` in `step:` from the transcript.
- Keep file markers in line with the monitor parser: `- Approved <YYYY-MM-DD HH:MM> G1b` under `## Approval`, `Confirmed <…>` under `## Confirmation`, the numbered list under `## Completion criteria`, `Status:`/`Location:`/`Profile:`/`Request:` in `intake.md`.
- Translated to English (2026-10-28, ARCH v0.28): every file under `plugins/` is English except the monitor's EN/Korean UI strings (`monitor/web/index.html`, `monitor/tools/build-web.py`). File-format headings changed (`## Completion criteria`, `## Work units`, `Work unit: u<n>`, `## Reference files`, `- Deliverable location:`, `- Save path:`), so task folders from before this change do not parse. SKILL.md Question rules: speak the language of the request; every agent definition writes prose in that language. The core-rules budget in `test_skill_md` is now 16,000 characters (English density).
- Review applied (2026-10-28, `docs/handoff/my-agent-review-2026-10-27.md`, ARCH v0.27): the user decided to fix things directly in a normal session instead of the my-agent dev profile (ARCH 4.11 "how to fix the system").
  - Added a "Change requests" section to the core rules (B6). It must stay within the first 6,000 characters.
  - In-flight revision: the run-log `revision` line is the reference. A revision of the same task starts with a `state=pending` line and ends with `revision rev=<N> state=done`, and `## Revisions` is always at the very end of `plan.md` (the trailing `invalidated:` is gone). A rewrite before approval (G1b `Request changes`, Plan Review `REVISE`) keeps a `-rev<N>-draft` archive and writes a `revision rev=<current rev> before=G1b` line. `continue` first finishes any rev without `state=done`.
  - `Scope change:` also writes a `fix what="Scope change: …" files=plan.md` line (the tally counts it separately).
  - `accept.md` "Back to Execute": on Verify FAIL, Review BLOCKER or G3 rework, copy the verdicts to `archive/<time>-run<n>/`, set only the affected units to `pending`, `.active phase: 3`, `step n=5 … back= archive=`. For a small fix that only got Review again, L1 writes `## Applied after review` (A3).
  - Work units are `### u<n> <name>`, and the first line of a delegation prompt is `Work unit: u<n> <name>` (the hook records it as `unit=`). `Prototype: requested` only inside the `## Prototype` section. The plan-review skip line is `SKIPPED <reason>`. The dev deliverable is written `Delivered: commit:<sha>`.
  - In the general profile, if there are two or more document units, the last writer unit merges them into `work/final.md`. That unit is handed off at 6 Merge, as in research (L1 only checks).
  - Independent review applied (same day): archive `mkdir` and `cp` use absolute paths without `cd` (before approval the G1b hook blocks relative paths after `cd`; checked by hand). Consecutive Verify FAILs are the number of `Verdict: FAIL` since the last ALL PASS or revision, not `Run:` (same as the monitor). An Execute that was sent back does not redo the `base` and change popups and does not use worktrees. A merge unit becomes `pending` along with any earlier unit that is `pending`. In a rewritten plan, architect marks the kept units `done`. `revision … state=pending` gets `to=<phase>` (used when `continue` finishes an interrupted revision). Rewrite before approval also covers applying Plan Review findings and the prototype `Plan change`.
- Task records over time (2026-10-28, ARCH v0.29 4.8.2): the last item of the retrospective (`accept.md` item 9) and Abort item 2 (right after the `abort` line) run `usage-snapshot.py` while `.active` still names the task. Exit 3 is reported in one line and undoes nothing. `test_usage_snapshot_before_active_cleanup` checks the order. A retrospective cut off before item 9 leaves no snapshot; `archive-tasks.py` takes one before moving the task.
- Profile flag (2026-10-28, v0.3.2, ARCH v0.30, Q19): only the first word of the argument is a flag; the same text later in the request is part of the request. The flag check runs before Intake item 1, and the `--dev` git check runs in item 3 once the work location is known. Three popups: invalid flag (`Let the Router pick (Recommended)` / `Abort`; `Let the Router pick` drops the flag and handles the rest as if called without it), `--dev` outside a git repository (`Proceed as general (Recommended)` / `Abort`), and a flag without a request (`Type the request in Other (Recommended)` / `Abort`). `Abort` in these popups stops the call and creates nothing. The `(set by you)` / `(Router)` mark is judged from whether the first word of `Request:` in `intake.md` is a valid profile flag; the `intake.md` format is unchanged. Known effect: the monitor task title (first `Request:` line, `monitor/monitor/mdfiles.py`) and the `Request:` in the `status` table start with the flag (for example `--research Compare SQLite…`). `argument-hint` has the same value in SKILL.md and in ARCH 4.7.1. The tests `test_argument_hint_matches_profiles_and_phases`, `test_arguments_table_names_every_flag`, `test_arch_doc_argument_hint_matches_skill_md` and `test_arch_doc_names_every_flag` catch a mismatch between the hint, the Arguments table, the design document and the profile folder. Regenerate `docs/index.html` with `python3 tools/build-docs.py`. Scenarios not rerun (dev, general, research); they are rerun later as a separate task.

## L2 design · judging (`l2-design-judge/agents/`)

**Current state (2026-10-25):** `architect`, `plan-reviewer`, `verifier`, `reviewer`, `gate-analyst` (added 2026-10-26, interprets the decision tally in the retrospective; effort raised from medium to high on 2026-10-27). Model, effort and tools follow the table in section 4.5 (`test_agents` checks this). The check lists per profile (general / research / dev) are written directly in the body.

**Settled**

- The L2 agent list in the monitor `web/index.html` has no gate-analyst (left as is by the 2026-10-26 decision).
- Judge checks: `tests/judge-fixtures/run-judge-check.sh` (paid, one verifier run per note). Run it after changing verifier or reviewer. 2026-10-25: 4/4 matched.
- Result first lines: plan-reviewer `READY FOR APPROVAL` | `REVISE`, verifier `Verdict: ALL PASS` | `Verdict: FAIL` (followed by `- <n>. PASS|FAIL <evidence>`), reviewer `BLOCKER <count>`.
- The first line of the last message becomes the run-log `result=`, and the monitor reads it with `ma_schema.verify_failed` (starts with `Verdict: FAIL`). Without a verdict word on the first line, the verdict does not show on screen (F26). Before 2026-10-28 the monitor checked `startswith('FAIL')`, so consecutive FAILs were always 0 (review A1).
- 2026-10-28: every definition file has frontmatter `level: L2|L3` (Claude Code does not use it; validate passes; `test_agents` checks it against the folder and `ma_schema.AGENTS`). architect: carries `## Revisions` over as is (scope-guard blocks otherwise), `### u<n>` units and the ID rules, `Kind:` as the first line of `## Mock-up`, `## Existing work` (`| Target | Decision | Reason |`) after `## Estimate` and before `## Approval`. verifier: the completion criteria file is `scope.md`, or `plan.md` if there is none. gate-analyst: the three-section format of `gate-tally.md` is written in the definition. Verdict words must match the `ma_schema` constants (`test_schema`).

## L3 workers (`l3-workers/agents/`)

**Current state (2026-10-25):** `explorer` (maxTurns 30, writes no files → L1 saves the report to `explore.md`), `researcher` (40), `writer` (40), `coder` (60, does not commit).

**Settled**

- Every worker has `maxTurns`. When it is hit, no SubagentStop comes and sweep records `end=partial` (F22).
- researcher note items are only `- <claim> · <source URL> · "<quote>"` or `- Not found: …`. verifier and writer use the same format.
- Inside a workflow too, with `agentType: 'my-agent:<name>'` the definition file and hooks apply as is (F29).
- 2026-10-28: researcher, writer and coder get `Work unit: u<n> <name>` as the first line of the delegation prompt ("Input" in the definition file). The `PARTIAL <reason>` a worker writes itself and the maxTurns `end=partial` are different things (ARCH 4.7.2).

## L4 tools · guards (`l4-tools-guards/`)

**Current state (2026-10-25)**

- Plugin hooks (`hooks/hooks.json`): `scope-guard.py` (all tools, read and write scope of `my-agent:` agents, `onFailure: block`; gate-analyst reads only `gate-tally.md` and `gate-report.md` and writes only `gate-report.md`, 2026-10-26), `subagent-log.py` (call/start/stop), `permission-log.py` (G2 ask/answer), `session-notice.py` (SessionStart). Recording hooks always exit 0 and have no `onFailure`.
- Skill hooks: `plan-approved-check.py`, `verdict-fresh-check.py`. Even after approval, `plan-approved-check` returns `ask` for writes outside the task location, agent-tasks and the declared deliverable location (because auto mode does not ask, 2026-10-25). The retrospective copy folder (`ma_gate_report.report_dir()`, `$MA_GATE_REPORT_DIR`) also passes without asking (2026-10-26). The three blocking hooks block with exit 2 on error.
- `lib/ma_bash`: for a Bash command, the write targets, read paths, copy sources, and whether it changes git. Writes it cannot catch (`python -c` etc.) are remaining risk (section 4.4). It follows shell keywords, `bash -c`/`eval` and `cd`; forms it cannot follow (command substitution, open heredoc, variable paths, variable `cd`, symlink + write) give None (blocked). git uses an allow list of read subcommands.
- `ma_bash.http_sends`: whether curl or wget sends data (including short option bundles `-sd`, `-XPOST`, `--data=…`). scope-guard applies it only to verifier (user decision 2026-10-25). If curl options grow, fix `CURL_SEND_*`.
- `lib/ma_path`: path comparison (`under`, `same`) is case-folded. Every path comparison in the hooks uses it (closes the gap of bypassing with `Docs/agent` on macOS volumes, final review C3).
- `lib/ma_plan`: reads the approval line in plan.md, `Prototype: requested` (only inside the `## Prototype` section) and the work units. It delegates to `ma_schema`. scope-guard blocks architect writes that add these two lines anew or delete or change `## Revisions` lines (C2, 2026-10-28 A2).
- `permissions/permissions.json`: G2 ask/deny. Merged into the user settings (`~/.claude/settings.json`) at install on 2026-10-25 (backup `settings.json.backup-20261025-141535`). The sandbox `.claude/settings.json` has the same copy. When rules change, fix both places and `test_permissions` together. "Write outside the working directory" has no rule string and is left to Claude Code's default confirmation. The form where a git option comes before the subcommand (`git -C … commit`) is caught by rules with `*` in the middle, like `Bash(git * commit*)`. Prefix rules alone let it pass (2026-10-25, both ask and deny checked interactively).
- `scripts/run-log.py`: L1 records. Before writing it runs sweep to close workers ended by maxTurns and prints `PARTIAL:`/`MISMATCH:`. The main model in `step:` lines is read from the last main assistant entry of `<projects>/*/<session>.jsonl` (`ma_subagent.main_model`, last 4MB only); `--model` is used only when that is missing.
- `lib/`: `ma_active` (finds `.active`; for a worktree, goes to the main tree; inside a repository the index looks only at its root line, C1), `ma_logline` (line format), `ma_subagent` (transcript totals, `stop:` lines, sweep). An agent called again with `SendMessage` restarts with the same id, so `stop:` is written as many times as `start:`, and a run called again counts from the last `start:` time −2 seconds (`run_since`, F33). sweep closes only the first run (the meta file keeps the first run's finished as is). user entries come in during a run too, so runs are not split by user entries. `ma_gate_report` (run-log decision tally, cost and tokens per `cost:` stretch, copy folder `report_dir()`, 2026-10-26).
- `scripts/`: `run-log.py`, `feedback.py`, `secret-scan.py`, `check-run.py` (scenario pass condition), `gate-report.py` (retrospective tally `tally` and copy `copy`, exit codes 0/1/2/3, 2026-10-26). Exit code 3 (could not write `gate-tally.md` or the copy) is an addition not in the 261026 plan spec (0/1/2), and is written in ARCH 4.11 and `accept.md`.
- Tests: `python3 -m unittest discover -s l4-tools-guards/tests` (226 tests, 2026-10-28). Scenarios are in `tests/scenarios/`.
- Single source of formats (2026-10-28, review C): `lib/ma_schema.py` holds the agents and levels, verdict words, status values, gates, model families, run-log line reading, finding a `## section`, and plan.md marker lines. `ma_logline`, `ma_plan`, `ma_subagent`, `ma_gate_report`, the three hooks, `run-log.py`, `check-run.py`, `feedback.py` and the monitor use it. When a word changes, change it together with the definition files and L1 files, and run `test_schema`.
- 2026-10-28: rebuilt scope-guard as level default rules + role rules (D2). `subagent-log` records `unit=` in `call:` (prompt) and `stop:` (first user entry of the transcript), and sweep does the same. `unit=` in the `PARTIAL:` of `run-log.py`. An unreadable run-log line gives a `run-log.py` stderr warning and a `check-run` failure (`log-format`); if `.active` has no `task:`, the G1b and verdict hooks warn (systemMessage) and scope-guard blocks (C9). `check-run` also checks `units` (every unit done|stale) and `revisions` (`state=done` for each rev). `feedback.py` gets `list` and `done <n> "<what was fixed>"`. The `gate-tally.md` metrics get the counts of in-scope adjustments, rewrites before approval and in-flight revisions.
- The plugin cannot ship `permissions.json`, so the person merges it into `~/.claude/settings.json`. This is written in the install section of both READMEs (2026-10-28).
- Task records over time (2026-10-28): `lib/ma_usage.py` reads the main transcript and sums usage per (rev, step) window (the last window of a finished task ends 1 s after the last run-log line). The monitor's `transcript.py` and `taskview.py` use the same `parse_entry`, `windows` and `sum_windows`, so a snapshot equals what the monitor showed from the transcript (checked on two real tasks). `scripts/usage-snapshot.py` (L1, or `--task-dir` by hand) writes `main-usage.json`; with a session's transcript missing it writes nothing and keeps an existing file (exit 3). `scripts/archive-tasks.py` (person-run, `--days N`, default 30, `--dry-run`) moves done/aborted tasks to `docs/agent/.archived/<task-id>/`, never the task in `.active`, and snapshots first when it can. Tests: `test_usage.py`.

**Dependence on external behavior (probe results, `probe/results.md`)**

- A subagent ended by maxTurns gets no SubagentStop. sweep looks at `"finished": true` in `~/.claude/projects/<project>/<session>/subagents/agent-<id>.meta.json` and the `stop_reason` (≠ `end_turn`) of the last assistant entry in the transcript. If this file format changes, `end=partial` disappears. `MA_CLAUDE_PROJECTS` can change the path.
- **Limit of sweep:** it counts every end other than `end_turn` as partial. Cuts for reasons other than maxTurns also count toward E's "a work unit stopped twice".
- A worktree agent's `cwd` is `.claude/worktrees/agent-<id>`, and `.git` is a `gitdir:` file. `ma_active.main_worktree` follows it.
- `SubagentStart` has no `permission_mode`. The permission mode is recorded in `mode=` of `stop:`.
- `PermissionRequest` input has `agent_id`. A denial has no event, so it is not recorded.

**Probe items still open**

- 6: whether background agents end when the session ends — interactive procedure (`probe/results.md`).
- 7: `claude-sessions` notifications for G1·G3 popups — interactive procedure.
- 9: whether the status line amount includes subagent cost — interactive procedure.

**Remaining risk (Q8)**

- The G1b hard gate is a skill hook, so it is absent in a new session before `/my-agent` is invoked. The `SessionStart` notice is only an instruction. If work done without approval shows up in a retrospective, reconsider moving it to a plugin hook.
- If a `Skill` call is denied in `-p` or in a permission prompt, the skill hooks are not registered either (F28). In that session G1b is guarded only by the `SessionStart` notice.

**Where to diagnose**

- Load errors show in the **Errors** tab of `/plugin`, not in `/hooks`.
- Every time the manifest, agent frontmatter or `hooks.json` changes, run `claude plugin validate --strict .` (plugin folder) and `claude plugin validate --strict ~/dev/my-plugins` (marketplace).
- If records are missing, look at `log-error` lines in the run-log, hook output and the `claude --debug` log.

**Install and rollback (Task 12, after user approval)**

- Before install, copy `~/.claude/settings.json` to `~/.claude/settings.json.bak-<YYMMDD-hhmmss>`.
- Install: `claude plugin marketplace add ~/dev/my-plugins`, `claude plugin install my-agent@my-plugins`. After install, do not also use `--plugin-dir` (the same name gets loaded twice).
- Rollback: `claude plugin disable my-agent@my-plugins` (all hooks go away) → if needed, `claude plugin uninstall my-agent@my-plugins` and `claude plugin marketplace remove my-plugins` → restore the backed-up `settings.json`.
- When a self-edit breaks a hook: in a normal terminal, `claude plugin disable my-agent@my-plugins` → `git checkout -- <file>` → `claude plugin enable my-agent@my-plugins`.

## Monitor (`monitor/`, outside the levels)

- `monitor-up.py` starts it on the first free port in 8765–8775. State is in `~/dev/agent-tasks/monitor.json`, output in `monitor.log`. Stop it with `/my-agent:monitor stop`.
- How it opens is set by `~/dev/agent-tasks/monitor-config.json` (`window`/`tab`). The menu bar app is `monitor/menubar/`; remove the login item with `login-item.sh uninstall`.
- If `~/dev/agent-tasks/prices.json` exists, it is used as the price table.
- Mini window (2026-10-27): a left click on the menu bar icon opens the List/Detail mini window; a right or Ctrl click opens the existing menu. Only the view settings (`mode`, `pinned`, `frame.list`, `frame.detail`) are saved in the UserDefaults suite `my-agent.monitor-menubar` (clear with `defaults delete my-agent.monitor-menubar`). The `/api/tasks` summary gained a read-only `elapsed` field.
- The mini window's Detail relies on the global `selectTask` in `web/index.html` and on reading the `#task=` hash at first load. Changing the name or format of either breaks Detail selection. `tests/test_web_contract.py` catches this.
- The List blinking (the symbol and current bar cell of running and waiting-for-answer rows) matches the web `.dot.run` `pulse` (1.4 seconds, opacity .3). If the web value changes, change `menubar/Sources/Views.swift` to match. It stops under Reduce Motion.
- List height and status colors (2026-10-27): the status colors live in two places, `--st-*` in `web/index.html` and `statusPalette` in `menubar/Sources/ListModel.swift`. `test_palette_matches_web` in `tests/test_menubar.py` checks that they match. Change one, change the other.
- `--ok`/`--run`/`--gate`/`--l1-soft` are also used outside status (gate results, L1 markers, etc.), so leave them alone when changing status colors.
- The web has no tone for a task without status. The server always sends one of the three statuses (`monitor/taskview.py:173`).
- The List height is computed from the `ListMetrics` constants, and the view fixes its height with the same constants. If the row shape changes, adjust the constants too.
- The List height animation goes: release constraints → animate → in completion, fix and save the height. Changing the order loses the animation or saves an intermediate frame.
- Mini window List rows do not draw the step name. `stepLabel` remains because `--print-list` (`renderList`) uses it.
- First click (2026-10-28): when another app is in front, the first click on the mini window applies directly to filters, List/Detail, pin and rows. `FirstClickHostingView` accepts first mouse; List rows are not handled by the SwiftUI scroll container, so `FirstClickWindow` resends only clicks released in place after the window becomes key (drags that moved more than 4pt are not resent). There is no GUI test.
- Icon left-click toggle (2026-10-28): if the window is in front (no other window overlapping it, or pinned), hide it; otherwise open it or bring it to the front. Whether it is in front is checked with `CGWindowListCopyWindowInfo(.optionOnScreenAboveWindow)`, not `NSApp.isActive` (a status item click does not always activate the app). The Dock (level 20) and the menu bar have transparent full-screen windows, so only windows below Dock level count. When hiding, `NSApp.hide` is ignored for an inactive app, so `orderOut` is used, and `hide` only when active, to give focus back. `show()` uses `NSApp.activate()` because `NSApp.activate(ignoringOtherApps:)` is often refused (then on a menu bar click the active app's window comes back on top and every click only reopens), and also calls `orderFrontRegardless` so it still comes to the front. The left click is decided on mouse-down (`sendAction(on: [.leftMouseDown, .rightMouseUp])`). Checked with synthesized CGEvent down/up clicks while Terminal was in front: to front → hide → open, 3 times. Follow-up (2026-10-28): after selecting the window (app active), clicking the icon made the app inactive before the click arrived, the Terminal window came back on top, and the first click was ignored. So it records whether the window was in front at `willResignActive` (within 1 second) and when the pointer entered the icon (`NSTrackingArea` mouseEntered, within 10 seconds), and hides if either is true. `FirstClickWindow` also switched to `NSApp.activate()`. Checked: covered by Terminal 8 times, after selecting the window 5 times, consecutive clicks 8 times, all correct (the synthesized clicks move the pointer to the icon first, then down/up).
- 2026-10-28: the monitor adds `l4-tools-guards/lib` to `sys.path` (`monitor/__init__.py`) and reads run-log lines, sections and verdict words with `ma_schema`. If the plugin folder layout changes, fix this path too. Consecutive Verify FAILs are counted by `Verdict: FAIL` and restart on ALL PASS or a rev change; worker stops are per (rev, unit) (a stop without `unit=` is separate per id). `back=` in `step:` becomes a "back to Execute" log item, and suffixes like `-b` in archive folder names also go into the mock-up history. `before=` in a `revision` line shows as "plan rewrite before approval", and `state=done` of the same rev shows merged into one revision. `fix what="Scope change: …"` also shows. A mock-up is shown by its `Kind:` first line, a prototype by the `## Prototype` section, and `Delivered: commit:<sha>` as a commit. Removed the unused `mdfiles.read_active`, and rebuilt the test fixtures in the real output formats (`tests/build_fixtures.py`).
- Task records over time (2026-10-28): a finished task with `main-usage.json` is costed from that file (current prices) and its transcript is no longer watched: the registry keeps no sessions for it and `TranscriptCache.keep` forgets unwatched sessions on each list. The registry also drops cache entries of folders that left the list. Only `docs/agent/*/intake.md` is listed, so `.archived/` stays out. Depends on Claude Code `cleanupPeriodDays` (default 30 days): a finished task with no snapshot shows main tokens as `–` once its transcript is deleted. The README now gives the real `/api/tasks` shape `{tasks, now}`.
- Known display issues: a call with only `call:` and no `start:` (an agent that was denied or failed to start) keeps showing as "running". The `result=-` of an empty partial shows as `-` in the result column.

## Install (2026-10-25)

- (First install record) `claude plugin marketplace add ~/dev/my-agent` (name `my-agent-dev`, added to `extraKnownMarketplaces` in the user settings as a directory source), `claude plugin install my-agent@my-agent-dev` (user scope, 0.1.0).
- `claude plugin list` showed `Read from: /Users/jahoonjin/dev/my-agent` (for the path after the move, see the next section). It is a directory source, so fixes apply right away in a new session (or after `/reload-plugins`) (F17). `--plugin-dir` is no longer used.
- In a new session, 8 `my-agent:` agents and the `my-agent:my-agent` skill show. (9 after gate-analyst was added on 2026-10-26.) `/my-agent:monitor` has `disable-model-invocation`, so it is not in the model's list and shows only when the person invokes it.
- The global setting is `"model": "sonnet"`, so L1 runs on the session model (Sonnet) (F13). To use opus as designed, open the session with opus.

## Moved to my-plugins (2026-10-25)

- Moved the plugin folder from `~/dev/my-agent` to `~/dev/my-plugins/plugins/my-agent`. `~/dev/my-plugins` is the marketplace (`my-plugins`) and a git repository. Other plugins go in `plugins/<name>`, with an entry added to `.claude-plugin/marketplace.json`.
- Marketplace relative paths point only inside that folder (no `..`, symlinks to outside are not read). Pointing to an outside folder takes a `command` source, so moving was chosen.
- Reinstall: `marketplace remove my-agent-dev` → `marketplace add ~/dev/my-plugins` → `install my-agent@my-plugins`. `claude plugin list` shows `Read from: /Users/jahoonjin/dev/my-plugins/plugins/my-agent`.
- The plugin version (`my-agent:` in `intake.md`) looks only at the plugin folder: `git -C "${CLAUDE_PLUGIN_ROOT}" log -1 --format=%h -- .` (`test_plugin_version_scoped_to_plugin_folder`). Commits to other plugins do not trigger the rule-change popup in `continue`.
- Places where the old path remains: dated plans, probe results and validation records (records of that time, not changed), `~/dev/my-agent-monitor/` (a folder left untouched).

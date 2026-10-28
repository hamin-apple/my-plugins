# ④ Accept: 7 Verify · 8 Review → G3

Verify and Review are never skipped, in any profile.

## 7. Verify

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=7 name=Verify --model <main session model ID> --data-dir "<data folder>"`
2. Hand it to `my-agent:verifier`. Pass: the file with the completion criteria (`scope.md` if it exists, otherwise `plan.md`; `plan.md` in the general profile and for a dev small task), the `Scope change:` lines under `## Approval`, the deliverable path, and the result path `verify.md`. Do not pass the workers' explanations.
3. `verify.md` format: first line `Verdict: ALL PASS` or `Verdict: FAIL`, then one line per criterion, `- <n>. PASS|FAIL <evidence>`.
4. On FAIL, do "Back to Execute" below and go to Execute in ③ Build with the list of failed criteria. On 3 FAILs in a row, go to E (SKILL.md "Failure handling"). The count in a row is the number of `Verdict: FAIL` since the last `Verdict: ALL PASS` (or Revise this task). Count the `result=` of verifier `stop:` lines in the run-log from the end (the monitor counts the same way). `Run:` is only the judgment round, so it goes up after a PASS too.

## Back to Execute

Do this every time you go back to ③ Build for Verify FAIL, Review BLOCKER (when it is not a small fix), or G3 `Rework`. The next judgment overwrites `verify.md`·`review.md`, so keep the current judgment first.

1. Copy `verify.md` and `review.md` (if present) with `cp -p` (absolute paths) to `archive/<date +%y%m%d-%H%M%S value>-run<Run: value of verify.md>/` and compare with `cmp`. If they differ, stop and report.
2. In `plan.md`, set `Status:` to `pending` for the work units tied to the failed criteria (or the shortfalls named at G3). If there is a last writer unit that combines a document deliverable, set it to `pending` too when any earlier unit becomes `pending`. Leave the rest as `done`.
3. Change `phase:` in `.active` to `3` and read `build.md`. Add the reason and the archive folder to the Execute step line: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=5 name=Execute back="<Verify FAIL criterion numbers / Review BLOCKER / G3 Rework>" archive=<archive folder> --model <main session model ID> --data-dir "<data folder>"` (instead of `build.md` step 5 item 1). In an Execute reached this way, skip `build.md` step 5 item 2 (base point, uncommitted-changes popup), and run coder in sequence in the main tree without a worktree (the already merged changes are uncommitted, so a worktree cannot see them).

## 8. Review → Deliver

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=8 name=Review-Deliver --model <main session model ID> --data-dir "<data folder>"`
2. Hand it to `my-agent:reviewer`. Pass: the deliverable path, the `plan.md` path, and the result path `review.md`. The first line of the result is `BLOCKER <count>`.
3. If there is 1 BLOCKER or more: if it is a small fix (the L1 exception in the SKILL.md level table), L1 fixes it (`fix` line) and gets a new judgment. If only Review was redone, without Verify, add a `## Applied after review` section at the end of the new `review.md` with Edit and list each fix on its own line as `- <what was fixed> (<file>)` (without this section, the hook blocks the G3 save and commit because `verify.md` is older than the change). If it is not a small fix, do "Back to Execute".
4. **G3 report (chat):** summary of the result, list of failures and unhandled items, the diff or the deliverable, tokens used and cost (reference), and **the exact path it will be saved to**.
   - Save location: the deliverable location in `## Scope summary` (or `scope.md`). If none, `deliverable/` in the task folder.
   - File names are lowercase English with hyphens. If the same name exists, do not overwrite; add `-2`. If the task changes an existing file, show the diff.
   - If the path is outside `~/dev`, state in the popup question that picking `Accept` counts as approval of that write.
5. **G3 popup:**
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="Final acceptance: <task-id> → <save path>" rec="Accept" --data-dir "<data folder>"`
   - Popup: `Accept (Recommended)` / `Rework` / `Abort`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<chosen choice>" --data-dir "<data folder>"`
6. **Accept:**
   - Do SKILL.md "Check before anything leaves" on the final version.
   - Copy the final version from the task folder to the save location. Workers do not write outside the task folder, so L1 makes this copy. If the judgments are not fresh, the hook (`verdict-fresh-check.py`) blocks it. If blocked, redo from Verify.
   - Add `Delivered: <path>` to `intake.md` and run `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=<path> --data-dir "<data folder>"`.
   - Change `intake.md` to `Status: done`.
   - Retrospective: do "Retrospective" below. After the retrospective ends, last of all delete `.active` and this task's line in `<data folder>/active-index.json` (the retrospective needs `.active`).
   - The dev profile follows "G3 in the dev profile" below instead of this item 6.
7. **Rework:** If the criteria stay the same, do "Back to Execute" and go to ③ Build with the shortfalls as failed criteria. If the request changes the criteria, take SKILL.md "In-flight revision".
8. **Abort:** the "Abort" procedure in SKILL.md.

## G3 in the dev profile (commit approval)

The deliverable is a commit, so do this instead of items 4–6.

1. **Paste into the chat:** `git status --porcelain`, `git diff --stat` and the main diffs, the list of new files, the judgment summary (`verify.md` `Run:`, SHOULD-FIX·NIT in `review.md`), the proposed commit message (first line says what changed; the body lists completion criterion numbers `criteria: 1, 2, 3`), tokens used and cost (reference).
2. Commit only the files this task changed (changes since the `base` line, excluding `docs/agent/`; if `docs/agent/.gitignore` is `# my-agent: commit`, include the task folder too).
3. Record before and after the popup.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="Commit approval: <task-id>" rec="Commit" --data-dir "<data folder>"`
   - Popup: `Commit (Recommended)` / `Rework` / `Abort`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<chosen choice>" --data-dir "<data folder>"`
4. **Commit:**
   - Do SKILL.md "Check before anything leaves" on the files to commit.
   - `git add <files>`, then `git commit -m "<message>"`. The G2 permission dialog showing once more is a deliberate second check. If the judgments are not fresh, the hook (`verdict-fresh-check.py`) blocks it. If blocked, redo from Verify. Never use `--no-verify`.
   - Add `Delivered: commit:<short sha>` to `intake.md` and run `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=commit:<short sha> --data-dir "<data folder>"`.
   - Change `intake.md` to `Status: done`. Do "Retrospective" below, and last of all delete `.active` and this task's line in `<data folder>/active-index.json`.
5. **Rework** and **Abort** are the same as items 7 and 8 above. On abort, do not revert the changed files; only report their list.

## E escalation

- Conditions: Verify FAIL 3 times in a row, the same work unit stopped twice (`stop:` with the same `unit=` is `end=partial` or `end=error`), a workflow ended with an error, a merge conflict exposes a plan error.
- Show in the chat where it is stuck and what was tried, then record and ask in a popup.
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=E q="<where it is stuck>" rec="<recommended choice>" --data-dir "<data folder>"`
  - Popup: `Give direction` / `Change scope` / `Abort` (put the one that fits first, with `(Recommended)`)
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=E choice="<chosen choice>" --data-dir "<data folder>"`

## Retrospective

After Accept (or Commit) and before deleting `.active`, do these in this order. `Status: done` is written first, so if the session drops during the retrospective, `continue` does not redo G3.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/gate-report.py" tally --data-dir "<data folder>"`. It writes the decision table, metrics, and cost and tokens per stretch to `gate-tally.md`. On exit 1 (no running task), skip the report, say so in one line, and go to item 5. On exit 3 (could not write `gate-tally.md`), state the printed cause in one line and skip the report. Do not undo the Accept or Commit; go to item 5.
2. Hand it to `my-agent:gate-analyst`. Pass: `gate-tally.md`, the result path `gate-report.md`, and the profile written in the prompt (the `Profile:` value from `intake.md`; gate-analyst cannot read `intake.md`). The first line of the result is `DONE` or `PARTIAL <reason>`.
3. If PARTIAL or an error, do not undo the Accept or Commit; state the cause in one line, skip the copy, and go to item 5.
4. Do SKILL.md "Check before anything leaves" on `gate-report.md` and run `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/gate-report.py" copy --data-dir "<data folder>"` (the copy goes to `<data folder>/gate-report/`; if the copy folder already has the same name, `-2` is added). In the chat, show only the two paths (`gate-report.md` in the task folder, and the copy) and the 3 lines of `## Summary` in `gate-report.md`. If copy ends with exit 1 (no report) or exit 3 (could not write the copy), do not undo the Accept or Commit; state the cause in one line and go to item 5.
5. If there is no report (item 1 exit 1·3) or it was PARTIAL·an error (item 3), skip filing the `clear` suggestions. Otherwise, file the items in `gate-report.md` `## Suggested improvements` marked `clear` with `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" add L1 <task-id> "<improvement>" --data-dir "<data folder>"` (not shown in the chat). File other improvements from this task with `add L<1-4>` too.
6. `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" count --data-dir "<data folder>"`. If a `REVIEW: L<n> …` line appears (4 or more open improvements at one level), tell the person in one line.
7. Missing-call check: compare the list of this session's subagent transcripts (`~/.claude/projects/<project>/<session>/subagents/`) with the `id` of `start:` lines in the run-log. If a call is missing, file it as an L4 improvement.
8. If any `stop:` line in the run-log has a `mode=` other than auto, note it in the retrospective.
9. Last, run `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/usage-snapshot.py" --data-dir "<data folder>"`. It saves the main session's tokens per step to `main-usage.json` in the task folder, because Claude Code deletes transcripts after a while (architecture 4.8.2 "Task records over time"). On exit 3, state the printed cause in one line; do not undo the Accept or Commit.

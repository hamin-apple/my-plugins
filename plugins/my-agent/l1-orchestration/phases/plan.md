# ② Plan: 3 Plan · 4 Plan Review → G1b

## 3. Plan

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=3 name=Plan --model <main session model ID> --data-dir "<data folder>" --task-dir "<task_dir>"`
2. Hand it to `my-agent:architect`. Pass: the paths of `intake.md`, `explore.md` (and `scope.md`), the scope summary in the general profile, the preset name from `intake.md` `Models:` with the lines of `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/agent-models.py" show --profile <p> --preset <name> --data-dir "<data folder>"` (none when there is no `Models:` line), and the result path `<task_dir>/<task-id>/plan.md`.
3. Sections `plan.md` must have (if one is missing, have architect rewrite only that section):
   - a lead paragraph right after the `# Plan: <task-id>` title: one or two sentences on what the plan builds (not a `Profile:` line or a pointer to the criteria); the G1b Report view shows it as the plan summary
   - `## Scope summary` (general profile): purpose, non-goals, deliverable location
   - `## Completion criteria`: numbered list `1.`, `2.`, each criterion line ending with its check tag (general profile; other profiles have it in `scope.md`)
   - `## Work units`: per unit, a `### u<n> <name>` heading, the agent in charge, the list of files to change, the parallel group, `- Status: pending` (when rewriting, `done` for units whose results `## Existing work` keeps as they are)
   - `## Reference files`: files outside the task folder that agents may read (scope-guard allows every worker's reads by this list)
   - `## Mock-up` (**required**): first line `Kind: <kind>`, then a sample of the deliverable. Both the normal case and the exception cases in the scope, each tagged with its completion criterion number
   - `## Models` (with a `Models:` line in `intake.md`): the preset name and a table of the agents the plan uses (model, effort, note), plus a `Recommendation:` line when architect proposes a change; without a preset, `Preset: standard (definition values)`
   - `## Prototype`: needed / not needed, and why
   - `## Estimate`: number of subagents, workflow steps and agent count
   - `## Existing work`: only when rewriting for a revision (rev). For each deliverable already made: keep / revise / discard
   - `## Approval`: left empty
   - `## Revisions`: if the previous `plan.md` had it, carried over as is at the very end
4. If work units in the same parallel group change the same files, have them reordered to run in sequence.

## 4. Plan Review

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=4 name=Plan-Review --model <main session model ID> --data-dir "<data folder>" --task-dir "<task_dir>"`
2. Whether to skip follows the profile file. If skipped, write `SKIPPED <reason>` in `plan-review.md`.
3. Hand it to `my-agent:plan-reviewer`. Pass: the paths of `plan.md`, `intake.md`, `explore.md`, the same `agent-models.py show` lines as for architect, and the result path `plan-review.md`. Do not pass architect's explanation.
4. Handle the judgment the same way in every profile. "Small" is the SKILL.md level-table size (2 task files or fewer, about 10 lines); a finding that turns out larger goes to architect.
   - **L1 edit of `plan.md`** (small): archive per SKILL.md "In-flight revision" → "Rewrite before approval", edit `plan.md` with Edit (SKILL.md "Tool choice"), then record `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" fix what="Plan Review <severity> <path>:<line>" files=plan.md before=G1b archive=<archive folder> --data-dir "<data folder>" --task-dir "<task_dir>"`. **Architect rewrite** (larger): archive and write the `revision … before=G1b` line as in that section, then pass the `plan-review.md` path to architect.
   - `REVISE` (any BLOCKER): small → L1 edit, otherwise architect rewrite; then judge again. If the third `REVISE` comes, show that judgment in the G1b popup and leave it to the person, even while delegated approval is on (SKILL.md "Delegated approval"; the popup is unchanged).
   - `READY FOR APPROVAL`: never another Plan Review round. Apply what is chosen below, then go to G1b.
     - NITPICK only: apply them without a popup (L1 edit if small, else architect) and go to G1b.
     - Any SHOULD-FIX: show the list and ask one popup over the whole list (NITPICKs included), recorded with `ask gate=Q … rec="Apply all"` and `answer gate=Q`: `Apply all (Recommended)` / `Approve without applying` / `Pick myself`. Apply the chosen items (L1 edit if small, else architect), then go to G1b.
   - L1 writes the `## Decisions` lines in `plan-review.md`; architect does not write that file. Each applied or declined item is one line in `## Decisions`: `- <severity> <path>:<line> <summary> → applied by L1 | applied by architect | declined`.

## G1b plan approval

1. **Chat report** (shown after the Report tab is opened, item 3; SKILL.md "Gate reports"): `### Overview`, `### Takeaway` (the plan summary: work units, order and estimate; in the general profile also the scope summary), the overview table with its `Models` row (the preset and the recommended change, if any) and a `Prototype` row when a prototype exists, and the pointer line. No Details section and no full mock-up in the chat. Put the findings applied after Plan Review in the Takeaway ("Applied after Plan Review: 2 NITPICK (plan.md:41, plan.md:77)"). If a work unit has a `- Plugin reload: needed (<what>)` line, put a `Plugin reload` note in the risks row: `/reload-plugins` (or a new session) is needed after that unit. The popup question repeats the first two rows.
2. If `## Prototype` is "needed", popup: `Make a prototype (Recommended)` / `Mock-up is enough` / `Plan change`.
   - `Plan change` is the same as item 5, Request changes.
   - To make one, add a `Prototype: requested` line inside the `plan.md` `## Prototype` section with Edit and hand `my-agent:writer` the output path `<task_dir>/<task-id>/prototype/index.html`, the plan's `## Mock-up` and the paths `${CLAUDE_PLUGIN_ROOT}/skills/mock-up/SKILL.md`, `${CLAUDE_PLUGIN_ROOT}/skills/mock-up/templates/canvas.html` and the matching `${CLAUDE_PLUGIN_ROOT}/skills/mock-up/references/*.md`. The writer reads them, builds the file from the template and references and keeps the capture boot script (SKILL.md "Tool choice" for the checks).
   - L1 then runs `sh "${CLAUDE_PLUGIN_ROOT}/skills/mock-up/scripts/capture.sh" "<absolute path of prototype/index.html>"`, reads `prototype/index.png` and hands the file back to the writer for a fix, at most 3 times. On a non-zero capture exit (for example no Chromium browser) it states the line and goes on without a PNG.
   - If a G1a prototype exists (`scope.md`), remake it only if the mock-up changed.
   - L1 reads that file to check it, then runs `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/open-html.py" "<absolute path of prototype/index.html>" --data-dir "<data folder>"`, and shows the local path with the script's line (SKILL.md "Gate reports"); on a `failed:` line it carries on and the person opens the path. Nothing is published, so no secret scan here.
3. Record before and after the approval popup. Order: the Korean copy (SKILL.md "Gate reports"; Korean requests only), the `ask` line, the Report tab, the chat report of item 1 with the pointer line, the popup, the `answer` line.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G1b q="Plan approval: <task-id>" rec="Approve" --data-dir "<data folder>" --task-dir "<task_dir>"`
   - Then open the Report tab: `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/open-html.py" --report "<absolute task folder>" --data-dir "<data folder>"`, then `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/open-html.py" --report "<absolute task folder>" --url --data-dir "<data folder>"` only when the first line is `window`, `tab` or `failed: no browser opened` (any other `failed:` line: no `--url` call, the third pointer form with that reason; SKILL.md "Gate reports"), then show the chat report (item 1) with the pointer line.
   - Popup: `Approve (Recommended)` / `Request changes` / `Abort`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G1b choice="<chosen choice>" --data-dir "<data folder>" --task-dir "<task_dir>"`
4. **Approve:** Write `- Approved <YYYY-MM-DD HH:MM> G1b` under `## Approval`. Get the time first with `date '+%Y-%m-%d %H:%M'`, then write the value with the Edit tool, without command substitution (SKILL.md "Tool choice"; the G1b hook asks for a Bash write containing `$(…)` as a command whose write target it cannot tell). The `## Models` rows now apply; a recommended change is part of the approval, and `Request changes` refuses it. Change `phase:` in `.active` to `3` and read `build.md`.
5. **Request changes:** a small change (SKILL.md level-table size) is an L1 edit of `plan.md`; otherwise architect rewrites. Both follow "Rewrite before approval" in SKILL.md "In-flight revision" (archive, then a `fix … before=G1b` line for an L1 edit or a `revision … before=G1b` line for architect). Go back to item 1; Plan Review runs again only after a BLOCKER fix. In the general profile and the dev small task G1b is the first gate: if the person wants a different profile, follow SKILL.md "Profile change at the first gate". If the request changes the confirmed scope, take Revise this task in that section. Remake the prototype only if the mock-up changed.
6. **Abort:** the "Abort" procedure in SKILL.md.

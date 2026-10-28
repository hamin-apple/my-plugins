# ② Plan: 3 Plan · 4 Plan Review → G1b

## 3. Plan

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=3 name=Plan --model <main session model ID> --data-dir "<data folder>"`
2. Hand it to `my-agent:architect`. Pass: the paths of `intake.md`, `explore.md` (and `scope.md`), the scope summary in the general profile, and the result path `docs/agent/<task-id>/plan.md`.
3. Sections `plan.md` must have (if one is missing, have architect rewrite only that section):
   - `## Scope summary` (general profile): purpose, non-goals, deliverable location
   - `## Completion criteria`: numbered list `1.`, `2.` (general profile; other profiles have it in `scope.md`)
   - `## Work units`: per unit, a `### u<n> <name>` heading, the agent in charge, the list of files to change, the parallel group, `- Status: pending` (when rewriting, `done` for units whose results `## Existing work` keeps as they are)
   - `## Reference files`: files outside the task folder that writer may read (scope-guard allows writer's reads by this list)
   - `## Mock-up` (**required**): first line `Kind: <kind>`, then a sample of the deliverable. Both the normal case and the exception cases in the scope, each tagged with its completion criterion number
   - `## Prototype`: needed / not needed, and why
   - `## Estimate`: number of subagents, workflow steps and agent count, expected tokens (`<N>k tokens`)
   - `## Existing work`: only when rewriting for a revision (rev). For each deliverable already made: keep / revise / discard
   - `## Approval`: left empty
   - `## Revisions`: if the previous `plan.md` had it, carried over as is at the very end
4. If work units in the same parallel group change the same files, have them reordered to run in sequence.

## 4. Plan Review

1. Record: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=4 name=Plan-Review --model <main session model ID> --data-dir "<data folder>"`
2. Whether to skip follows the profile file. If skipped, write `SKIPPED <reason>` in `plan-review.md`.
3. Hand it to `my-agent:plan-reviewer`. Pass: the paths of `plan.md`, `intake.md`, `explore.md` and the result path `plan-review.md`. Do not pass architect's explanation.
4. If the first line of the result is `READY FOR APPROVAL`, go to G1b. If `REVISE`, do the rewrite before approval in SKILL.md "In-flight revision" (archive, `revision … before=G1b` line), then pass the `plan-review.md` path to architect to rewrite, and judge again. If the third result is also `REVISE`, show that judgment in the G1b popup and leave it to the person.

## G1b plan approval

1. **Paste into the chat:** the full `## Mock-up` (no summary), the flow diagram if any, a summary of the work units, `## Estimate`, the task ID. In the general profile, also `## Scope summary` and `## Completion criteria`. Mark parts that change because of the judgment.
2. If `## Prototype` is "needed", popup: `Make a prototype (Recommended)` / `Mock-up is enough` / `Plan change`.
   - `Plan change` is the same as item 5, Request changes.
   - To make one, add a `Prototype: requested` line inside the `plan.md` `## Prototype` section with Edit and hand `docs/agent/<task-id>/prototype/index.html` to `my-agent:writer` (per `artifact-design`).
   - L1 reads that file to check it, does SKILL.md "Check before anything leaves", then publishes it as a private artifact and shows the link and the local path.
3. Record before and after the approval popup.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G1b q="Plan approval: <task-id>" rec="Approve" --data-dir "<data folder>"`
   - Popup: `Approve (Recommended)` / `Request changes` / `Abort`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G1b choice="<chosen choice>" --data-dir "<data folder>"`
4. **Approve:** Write `- Approved <YYYY-MM-DD HH:MM> G1b` under `## Approval`. Get the time first with `date '+%Y-%m-%d %H:%M'`, then write the value with the Edit tool, without command substitution (the G1b hook blocks a Bash write containing `$(…)` as a command whose write target it cannot tell). Change `phase:` in `.active` to `3` and read `build.md`.
5. **Request changes:** Do the rewrite before approval in SKILL.md "In-flight revision" (archive, `revision … before=G1b` line), then pass the request to architect to rewrite, and go back to item 1. If the request changes the confirmed scope, take Revise this task in that section. Remake the prototype only if the mock-up changed.
6. **Abort:** the "Abort" procedure in SKILL.md.

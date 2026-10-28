# Dev profile (dev)

Tasks that change code in a git repository (feature, bug fix, refactoring). The deliverable is one commit approved at G3. On the normal path the person is asked 3 times: G1a, G1b, G3; for a small task, 2 times: G1b, G3 (not counting questions asked only the first time, such as the task location and `.gitignore`, or the G2 permission dialog).

## Rules per phase

| Step | Dev profile |
|---|---|
| 2 Explore → Scope | Always hand it to explorer: related files and their callers, current behavior, check commands (test·lint·build), uncommitted changes. The Scope interview settles seven things in `scope.md`: **purpose and users**, **completion criteria** (numbered `1.`, `2.`), **hard constraints** (what must not change, compatibility, performance), **exception cases** (empty input, errors, boundary values), **data** (input/output formats, storage), **non-goals**, **UX preferences** (messages, screens, CLI output). `scope.md` holds only WHAT/WHY. Do not write file or function names. Confirm with G1a. |
| Small task exception | If `explore.md` shows fewer than 3 files to change, and the request already answers purpose and users, completion criteria and non-goals: skip the Scope interview and G1a. L1 passes a 5-line summary (purpose, numbered completion criteria, non-goals, constraints, exception cases) to architect, which puts it at the top of `plan.md` as `## Scope summary` and `## Completion criteria`. Skip Plan Review and write `SKIPPED small task` in `plan-review.md`. State the decision and its reason in one line, on the line after the Intake report. |
| 3 Plan | A work unit (`### u<n>`) is one piece of code (`my-agent:coder`). Per unit: files to change, tests to add, completion criterion numbers, check commands. Only units that change different files go in the same parallel group. Worktrees are used only for the first parallel group. The mock-up is a sample of the behavior after the change (command output, response, screen). |
| 4 Plan Review | Not skipped (except for a small task). Findings are handled as in `plan.md` step 4; the decisions go in `## Decisions` of `plan-review.md`. |
| G1b | Plan approval. Show `scope.md` (for a small task, the 5-line summary) with it. |
| 5 Execute | At the start, record the base point (`base commit=<HEAD> dirty=<summary>`). If the main tree has uncommitted changes, popup: `User cleans up first (Recommended)` / `Proceed as is` / `Abort`. For `Proceed as is`, use no worktree and run every work unit in sequence in the main tree. Otherwise, call only the coders of the first parallel group with the call argument `isolation: "worktree"`, and call later groups in sequence in the main tree. |
| 6 Merge | (An Execute rerun through "Back to Execute" uses no worktree, so there is nothing to move.) Move worktree results into the main tree in the plan's work unit order. coder does not commit, so a worktree's changes are an uncommitted diff and new files: move the diff with `git -C <worktree> diff --binary HEAD \| git apply`, copy the new files from `git -C <worktree> ls-files --others --exclude-standard`, then `git worktree remove <worktree>`. For conflicts, see `build.md` item 6. After moving everything, run the check commands (tests, lint) from `explore.md`. If they fail, hand the unit back to its coder in the main tree along with the failing tests. |
| 7 Verify | verifier judges each criterion from `git diff`, `git status --porcelain`, new files and check command results. The second line of `verify.md`, `Run:`, is the round. On 3 FAILs in a row, E. |
| 8 Review → G3 | reviewer looks at the code review and the definition of done (`review.md`). G3 is commit approval (`accept.md` "G3 in the dev profile"): show the diff and the proposed message, then popup `Commit (Recommended)` / `Rework` / `Abort`. The commit message lists the completion criterion numbers. |

## Agents used

Names are the names used to call them.

| Agent | Steps | Result |
|---|---|---|
| `my-agent:explorer` | 2 | report → L1 saves it to `explore.md` |
| `my-agent:architect` | 3, G1b revisions | `plan.md` |
| `my-agent:plan-reviewer` | 4 | `plan-review.md` |
| `my-agent:coder` | 5, 6 (failed tests, large conflicts) | code and tests (not committed) |
| `my-agent:writer` | prototype | `prototype/index.html` |
| `my-agent:verifier` | 7 | `verify.md` |
| `my-agent:reviewer` | 8 | `review.md` |

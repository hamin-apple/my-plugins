# General profile (general)

Multi-step tasks that fit neither the research nor the dev profile. On the normal path the person is asked twice: G1b and G3 (not counting questions asked only the first time, such as the task location and `.gitignore`).

## Rules per phase

| Step | General profile |
|---|---|
| 2 Explore → Scope | Ask: purpose, completion criteria, non-goals, deliverable location. If the request covers all of them, skip the interview. Do not ask G1a separately. Write the deliverable location in the scope summary as one line ``- Deliverable location: `<path>` ``. After approval, the hook asks about writes outside the task location that fall outside this path. |
| 3 Plan | Put the scope summary and `## Completion criteria` at the top of `plan.md`. The mock-up is a sample of the deliverable (e.g. the first few rows of a table, a document's outline and a sample paragraph). |
| 4 Plan Review | May be skipped if the work units change fewer than 3 files in total. If skipped, record the reason in `plan-review.md`. Findings are handled as in `plan.md` step 4. |
| G1b | Approve the scope summary and the plan at once. It is the first gate, so show the task ID with it. |
| 5 Execute | Use subagents. Do not use a workflow. |
| 6 Merge | If the deliverable is a document and there are two or more work units, L1 hands the plan's last work unit (`my-agent:writer`) out in 6 Merge, and that writer combines the earlier units' results into one `work/final.md` (or one file under `work/` that fits the deliverable format). L1 does not combine; it only checks. Basic checks: each work unit has a result file, and each completion criterion has a matching part. |
| 7 Verify | PASS/FAIL per criterion. Not skipped. |
| 8 Review → Deliver | Result summary and quality judgment. Not skipped. Save location: the deliverable location in the scope summary, or `deliverable/` if none. Do not save to the Obsidian vault. |

## Agents used

Names are the names used to call them. The definition files are in the plugin's `l2-design-judge/agents/` and `l3-workers/agents/`.

| Agent | Steps | Result |
|---|---|---|
| `my-agent:explorer` | 2 | `explore.md` |
| `my-agent:architect` | 3, G1b revisions | `plan.md` |
| `my-agent:plan-reviewer` | 4 | `plan-review.md` |
| `my-agent:researcher` | 5 (units that need research, only after G1b) | `work/` notes: claim · source URL · quote |
| `my-agent:writer` | 5, 6 (the last combining unit), prototype | `work/` drafts, `work/final.md`, `prototype/index.html` |
| `my-agent:coder` | 5 (units that need code) | code |
| `my-agent:verifier` | 7 | `verify.md` |
| `my-agent:reviewer` | 8 | `review.md` |

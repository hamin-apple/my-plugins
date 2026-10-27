# Probe results (build step 0, 2026-10-25)

- Practice project: `~/dev/labs/my-agent-sandbox/` (git repository, `docs/agent/.active` → `261025-probe-task`)
- Run: `probe/run-probes.sh r1 … r7` — `claude -p --plugin-dir ~/dev/my-agent --model haiku --permission-mode default`, stream-json output in `.probe/run-<r>.json`
- Records: `probe-log.py` writes hook input to `.probe/<label>.jsonl`. The real hooks (`hooks/hooks.json`) are on too, so run-log lines are checked as well
- Agent: `probe/agents/probe-worker.md` (haiku, effort low, Bash·Read, maxTurns 3)

## Section 4.13 items

| # | Question | Run | Evidence (file · field) | Answer |
|---|---|---|---|---|
| 1 | Do plugin `SubagentStart`/`SubagentStop` hooks run for `my-agent:*`? | r1 | `agent_type: my-agent:probe-worker` in `SubagentStart.jsonl`·`SubagentStop.jsonl`, run-log `start:`/`stop:` lines | **Yes.** Matched by matcher `^my-agent:` |
| 2 | The `cwd` in the hook input when a worktree coder ends | r2 | `cwd` in `SubagentStart.jsonl`·`SubagentStop.jsonl` = `<repo>/.claude/worktrees/agent-<id>`; that folder's `.git` is a `gitdir:` file | **The worktree path.** No `.active` there, so records were missing at first → fixed `ma_active.find_active` to follow `gitdir:` and read the main tree's `.active`. Rerun r2 shows `start:`/`stop:` lines |
| 3 | Do agents inside a workflow fire these events? | r10 | `start:`/`stop:` for 2 workflow `agent()` calls in the run-log (`configured=sonnet`, `actual=claude-sonnet-5-5`). No `call:` line | **Yes** (when `agentType` is given). F29 |
| 4 | Do skill frontmatter hooks also run inside subagents? | r3 | `skill-pretool.jsonl`: only 1 `Agent` call from the main session, no `agent_id`. No record for the subagent's `Bash` calls | **No.** Rules that must also block subagents go in plugin hooks (F9 decision kept) |
| 5 | Does the call argument `isolation: "worktree"` apply to custom agents? | r2 | `tool_input.isolation: worktree` in `PreToolUse.jsonl`; the subagent's `pwd` output and `cwd` are `.claude/worktrees/agent-<id>` | **Yes** |
| 6 | Do background subagents end when the session ends? | r4, interactive 2026-10-25 | Interactive `/exit` shows running background tasks (shells, agents) and asks `Exit and stop tasks` / `Move to background and exit` / `Stay`. Picking the default (stop) stops them: the `sleep 60; echo late` shell disappeared and `late` never printed | **Answered (F31).** By default they stop together. To keep them, pick `Move to background` |
| 7 | Do G1·G3 popups (`AskUserQuestion`) trigger `claude-sessions` notifications? | 2026-10-25 interactive (tmux) | Put a temporary `Notification` hook (matcher `""`, appends stdin to a file) in the sandbox `.claude/settings.json`, showed a popup and waited 100 seconds | **Yes.** When the popup appeared, one event: `notification_type: permission_prompt`, `message: "Claude needs your permission"`. It is in the `claude-sessions` matcher, so a Mac notification goes out. The user was away and did not get it on another device ("it didn't come") — expected, since it is a Mac notification. Temporary hook removed (F34) |
| 8 | Is `${CLAUDE_PLUGIN_ROOT}` replaced in skill frontmatter hook commands? | r3 | `env.CLAUDE_PLUGIN_ROOT = /Users/jahoonjin/dev/my-agent` in `skill-pretool.jsonl`. Single-quoted `'${CLAUDE_PLUGIN_ROOT}'` passed as an argument stays as is | **It comes in as an environment variable** (not text substitution). Written in double quotes `"${CLAUDE_PLUGIN_ROOT}"`, the shell expands it → can replace `$HOME/dev/my-agent` in section 4.7.1 |
| 9 | Does the status line `cost.total_cost_usd` include subagent cost? | scenario runs 2026-10-25 | General: shown $2.12, main transcript list price $1.63 + subagents $0.40 = $2.03. Research: shown $5.14, main $1.99 + subagents $2.01 = $4.00 | **Answered (F32).** It does. The shown value is clearly larger than the main-only value (the remaining gap is taken to be calls outside the transcript, such as WebFetch summaries) |
| 10 | Can a workflow `agent()` name a plugin agent, and what is `agent_type` then? | r10 (2026-10-25, user approval) | `agent(…, {agentType: 'my-agent:explorer'})` → SubagentStart matcher `^my-agent:` runs, scope-guard blocks that agent's `Read /etc/hosts` ("scope-guard: Outside the read scope of explorer") | **Yes.** `agent_type` is `my-agent:explorer`. Meets the protection condition in section 4.6 → `build.md` workflow rules. F29 |
| 11 | With both `"skills": ["./"]` and `skills/monitor/`, do both show? | r5 | init event in `run-r5.json`, `skills`: `my-agent:my-agent`, `my-agent:monitor`, `my-agent:probe-skill`; `agents`: `my-agent:probe-worker` | **Yes** |

## Other facts confirmed

| Fact | Run | Evidence | Applied |
|---|---|---|---|
| `PermissionRequest` runs in `-p` too, and its input has `agent_id`, `agent_type`, `permission_mode`, `effort`, `permission_suggestions` | r6 | `PermissionRequest.jsonl` | Resolves the G2 [unverified] in section 4.7.2. `permission-log.py` uses the input's `agent_id` first |
| After a G2 denial there is no `PostToolUse`, so no `answer:` line is made | r6 | 2 `ask:` lines in the run-log, no `answer:` | As designed |
| `SubagentStart` input has no `permission_mode`. `SubagentStop` has `permission_mode`, `effort: {"level": …}`, `background_tasks`, `session_crons`, `stop_hook_active` | r1 | `SubagentStart.jsonl`, `SubagentStop.jsonl` | Removed `mode=` from `start:` and added `mode=`, `effort=` to `stop:` |
| An agent that ended by maxTurns gets no `SubagentStop`. The meta file `~/.claude/projects/<proj>/<session>/subagents/agent-<id>.meta.json` has `"finished": true`, and the last assistant entry's `stop_reason` is `tool_use` (a normal end is `end_turn`) | r4, r7 | No such id in `SubagentStop.jsonl`, meta and transcript files | `lib/ma_subagent.sweep` writes `stop: … end=partial` during `run-log.py` and subagent-log start/stop. `run-log.py` prints one `PARTIAL:` line |
| The transcript assistant entry keeps `effort` | r1 | Subagent transcript `effort: low` | Resolves [unverified] 4 in section 4.7.2 |
| In `-p`, an `Agent` call is async even without `run_in_background` (`status: async_launched`, meta `requestShape: background`). Then `PostToolUse(Agent)` has no result. A sync call's `tool_response` has status, totalTokens, usage, content | r1, r7 | `PostToolUse.jsonl`, meta files | Leave records to the Subagent events and sweep; do not use `PostToolUse(Agent)` |
| `result=` (first line of the last message) may not be a verdict word (r1: "The command \`pwd\` returned:") | r1 | run-log `stop:` line | Step 4 agent definitions get a "verdict word on the first line" rule. The monitor checks `startswith('FAIL')` |
| In `-p`, a `Skill` the model invokes needs permission. If denied ("Skill tool permission denied"), neither the skill content nor its frontmatter hooks are registered | live-t5, live-t5b (2026-10-25) | `claude --debug hooks` log: only scope-guard ran on `PreToolUse:Write` | F28. `-p` tests pass `--allowedTools Skill`. Interactively, the user allows it |
| The skill hook `plan-approved-check.py` blocks the main session's `Write`, and the plugin hook `scope-guard.py` blocks `Read /etc/hosts` inside `my-agent:explorer`. All 8 agents show at init, with `start: configured=sonnet` and `stop: actual=claude-sonnet-5-5` | live-t5c (2026-10-25, `-p` haiku, `--allowedTools Skill Agent Write Read Glob`) | stream `tool_result`: "…(G1b). Write outside the task folder", "scope-guard: Outside the read scope of explorer" | Real behavior of steps 2·3·4 confirmed |

## Manual procedures

### 7. G1·G3 popup notifications

1. Start an interactive session in `~/dev/labs/my-agent-sandbox/` with `claude --plugin-dir ~/dev/my-agent` (with the `claude-sessions` app running)
2. Ask "Show me any one question with AskUserQuestion"
3. With the popup open, wait 10 seconds and 70 seconds, and see whether a `claude-sessions` notification comes and which `notification_type` the `Notification` hook runs with (`.probe/Notification.jsonl`, after adding a `Notification` line to probe-hooks.json)
4. Write the result in row 7 of this table and in section 4.9. Even with no notification, the decision does not change (section 4.9)

### 9. Whether the status line cost includes subagents

1. In the same session, temporarily set the status line command to save the JSON it receives to a file (wrap `statusLine.command` with `tee`, in the practice project's `.claude/settings.json`)
2. Note `cost.total_cost_usd` before the subagent call
3. Call `my-agent:probe-worker` once, and note the value after it ends
4. Compare the difference with the run-log `stop:` line's `in`/`out`/`cw`/`cr` × the list prices in `monitor/prices.json`. If close, included; if near 0, not included
5. Write the result in section 4.8 and in row 9 of this table

### 6. Session end and background agents

1. In an interactive session, call `my-agent:probe-worker` with `run_in_background: true` and have it run `sleep 60; echo late`
2. End the session right away with `/exit`
3. After 1~2 minutes, check `finished` in the meta file, the time of the last transcript entry, and the run-log `stop:` line. If `late` is in the transcript, it kept running

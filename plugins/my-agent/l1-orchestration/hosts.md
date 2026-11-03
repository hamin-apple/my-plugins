# Host mapping

The phase, profile and agent files use Claude Code names. In a Codex session, read each name below as the Codex name beside it. A row that says `not available in Codex` has no Codex counterpart: if its note names another way (such as reading through `Bash`), use that way; otherwise skip the step that needs it and say so in one chat line. Codex agent names allow only `[a-z0-9_]`.

| Claude Code | Codex | Note |
|---|---|---|
| `AskUserQuestion` popup | `request_user_input` or `request_user_input_async`, with the choices | Both Codex tools take the question and its choices (`request_user_input`: header, id, question and options of label and description; `request_user_input_async`: title and string options), and the Codex TUI shows the choices. Write the `ask` and `answer` lines as usual. |
| `Agent` (start a subagent) | `collaborationspawn_agent` | Input fields: `agent_type`, `message`, `task_name`, `fork_turns`. |
| `subagent_type` `my-agent:<role>` | not available in Codex | Codex loads no agent definition from the plugin (identity findings; e2e run) and refuses `my_agent_<role>` as an unknown agent_type. Subagents started otherwise run without my-agent roles, so the subagent records (start and stop) and the role-based checks do not apply (gap report). |
| `isolation` | not available in Codex | The start tool has no such field. |
| `run_in_background` | not available in Codex | The start tool has no such field. Subagents started together overlap. |
| `model`, `effort` call arguments | not available in Codex | The start tool has no per-call model or effort field (D4). |
| `Workflow` | not available in Codex | |
| `SendMessage` | `send_message` | `followup_task` and `wait_agent` also exist in the main session. |
| Subagent hand-back (its final message) | the subagent's final message, read by the main session with `wait_agent` | |
| `Bash` | `Bash` | One `command` string. |
| `Edit`, `Write` | `apply_patch` | One `command` string holding the patch text. |
| `Read`, `Grep`, `Glob` | not available in Codex | No dedicated tool in the findings; read through `Bash`. |
| `WebFetch`, `WebSearch` | not available in Codex | |
| `${CLAUDE_PLUGIN_ROOT}` in skill text | not available in Codex | Codex passes the text literally, not expanded. The plugin folder is the folder of the `SKILL.md` file Codex read for the skill. Hooks get `CLAUDE_PLUGIN_ROOT` expanded. |
| `${CLAUDE_SKILL_DIR}` in skill text | not available in Codex | Codex passes the text literally, not expanded. The skill folder is the folder of the `SKILL.md` file Codex read for the skill. |
| `$CLAUDE_CODE_SESSION_ID` | `$CODEX_THREAD_ID` | The thread id is the session id of the Codex record. The findings list no other shell variable. |
| `${user_config.data_dir}`, `${user_config.task_dir}` | not available in Codex | Codex passes the text literally, not expanded. `data-dir.py` treats an unsubstituted `${...}` as empty, so the data folder is `$MA_TASKS_DIR` or the default, and the task folder is `$MA_TASK_DIR` or `.my-agent`. |
| G2 permission dialog | not available in Codex | The findings show no Codex permission dialog for G2. |
| `/my-agent` | not available in Codex | Codex lists no plugin-root `SKILL.md` (skills findings); `my-agent:monitor` is listed. |
| `/my-agent:monitor` | the skill `my-agent:monitor` | Codex lists it among its skills. |
| `.claude/worktrees` | not available in Codex | There is no `isolation`, so no coder worktree. |
| Agent identity on tool calls | `agent_type` and `agent_id` on the call | The identity findings show both fields on every subagent call and neither on the main session's calls. |

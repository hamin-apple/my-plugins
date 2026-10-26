# 탐침 결과 (구현 0단계, 2026-10-25)

- 연습 프로젝트: `~/dev/labs/my-agent-sandbox/` (git 저장소, `docs/agent/.active` → `261025-probe-task`)
- 실행: `probe/run-probes.sh r1 … r7` — `claude -p --plugin-dir ~/dev/my-agent --model haiku --permission-mode default`, stream-json 출력은 `.probe/run-<r>.json`
- 기록: `probe-log.py`가 hook 입력을 `.probe/<label>.jsonl`에 남김. 진짜 hook(`hooks/hooks.json`)도 같이 켜 두어 run-log 줄로 함께 확인함
- 에이전트: `probe/agents/probe-worker.md` (haiku, effort low, Bash·Read, maxTurns 3)

## 4.13절 항목

| # | 질문 | 실행 | 근거 (파일 · 필드) | 답 |
|---|---|---|---|---|
| 1 | 플러그인 `SubagentStart`/`SubagentStop`이 `my-agent:*`에서 실행되는가 | r1 | `SubagentStart.jsonl`·`SubagentStop.jsonl`의 `agent_type: my-agent:probe-worker`, run-log `start:`/`stop:` 줄 | **예.** matcher `^my-agent:`로 걸림 |
| 2 | worktree coder가 끝날 때 hook 입력의 `cwd` | r2 | `SubagentStart.jsonl`·`SubagentStop.jsonl`의 `cwd` = `<repo>/.claude/worktrees/agent-<id>`, 그 폴더의 `.git`은 `gitdir:` 파일 | **worktree 경로.** `.active`가 없어 처음엔 기록이 빠짐 → `ma_active.find_active`가 `gitdir:`를 따라 메인 트리의 `.active`를 읽게 고침. 재실행 r2에서 `start:`/`stop:` 줄 확인 |
| 3 | workflow 안의 에이전트가 이 이벤트를 일으키는가 | r10 | run-log에 workflow `agent()` 2개의 `start:`/`stop:` (`configured=sonnet`, `actual=claude-sonnet-5-5`). `call:` 줄은 없음 | **예** (`agentType`을 준 경우). F29 |
| 4 | 스킬 frontmatter hook이 서브에이전트 안에서도 실행되는가 | r3 | `skill-pretool.jsonl`: 메인 세션의 `Agent` 호출 1건만, `agent_id` 없음. 서브에이전트의 `Bash` 호출에는 기록 없음 | **아니오.** 서브에이전트까지 막을 규칙은 플러그인 hook에 둠(F9 결정 유지) |
| 5 | 호출 인자 `isolation: "worktree"`가 커스텀 에이전트에 적용되는가 | r2 | `PreToolUse.jsonl`의 `tool_input.isolation: worktree`, 서브에이전트 `pwd` 결과와 `cwd`가 `.claude/worktrees/agent-<id>` | **예** |
| 6 | 세션이 끝날 때 백그라운드 서브에이전트도 끝나는가 | r4, 대화형 2026-10-25 | 대화형 `/exit`는 돌고 있는 백그라운드 작업(셸, 에이전트)을 보여 주고 `Exit and stop tasks` / `Move to background and exit` / `Stay`를 묻는다. 기본값(stop)을 고르면 멈춤: `sleep 60; echo late` 셸이 사라졌고 `late`는 나오지 않았다 | **답함 (F31).** 기본은 함께 멈춤. 남기려면 `Move to background`를 골라야 한다 |
| 7 | G1·G3 팝업(`AskUserQuestion`)이 `claude-sessions` 알림을 일으키는가 | 2026-10-25 대화형(tmux) | 샌드박스 `.claude/settings.json`에 임시 `Notification` hook(matcher `""`, stdin을 파일에 덧붙임)을 넣고 팝업을 띄워 100초 기다림 | **예.** 팝업이 뜨자 `notification_type: permission_prompt`, `message: "Claude needs your permission"` 한 건. `claude-sessions` matcher에 있으므로 Mac 알림이 감. 사용자는 자리에 없어 다른 기기에서는 받지 못함("안 왔다") — Mac 알림이라 예상대로. 임시 hook은 지움 (F34) |
| 8 | 스킬 frontmatter hook 명령에서 `${CLAUDE_PLUGIN_ROOT}`가 바뀌는가 | r3 | `skill-pretool.jsonl`의 `env.CLAUDE_PLUGIN_ROOT = /Users/jahoonjin/dev/my-agent`. 인자로 준 작은따옴표 `'${CLAUDE_PLUGIN_ROOT}'`는 그대로 | **환경 변수로 들어옴** (글자 치환이 아님). 큰따옴표 `"${CLAUDE_PLUGIN_ROOT}"`로 쓰면 셸이 펼침 → 4.7.1절의 `$HOME/dev/my-agent`를 바꿀 수 있음 |
| 9 | status line `cost.total_cost_usd`에 서브에이전트 비용이 들어가는가 | 시나리오 실행 2026-10-25 | 일반: 표시 $2.12, 메인 transcript 정가 $1.63 + 서브에이전트 $0.40 = $2.03. 조사: 표시 $5.14, 메인 $1.99 + 서브에이전트 $2.01 = $4.00 | **답함 (F32).** 포함한다. 표시값이 메인만의 값보다 확실히 크다(남는 차이는 WebFetch 요약 같은 transcript 밖 호출로 봄) |
| 10 | workflow `agent()`에 플러그인 에이전트를 지정할 수 있는가, 그때 `agent_type` | r10 (2026-10-25, 사용자 승인) | `agent(…, {agentType: 'my-agent:explorer'})` → SubagentStart matcher `^my-agent:`가 실행됨, scope-guard가 그 에이전트의 `Read /etc/hosts`를 막음("scope-guard: explorer의 읽기 범위 밖입니다") | **예.** `agent_type`은 `my-agent:explorer`. 4.6절 보호 조건 충족 → `build.md` workflow 규칙. F29 |
| 11 | `"skills": ["./"]`와 `skills/monitor/`를 함께 둘 때 둘 다 뜨는가 | r5 | `run-r5.json`의 init 이벤트 `skills`: `my-agent:my-agent`, `my-agent:monitor`, `my-agent:probe-skill`, `agents`: `my-agent:probe-worker` | **예** |

## 그 밖에 확인한 사실

| 사실 | 실행 | 근거 | 반영 |
|---|---|---|---|
| `PermissionRequest`는 `-p`에서도 실행되고 입력에 `agent_id`, `agent_type`, `permission_mode`, `effort`, `permission_suggestions`가 들어옴 | r6 | `PermissionRequest.jsonl` | 4.7.2절 G2 [미확인] 해결. `permission-log.py`는 입력의 `agent_id`를 먼저 씀 |
| G2 거부 뒤에는 `PostToolUse`가 없어 `answer:` 줄이 생기지 않음 | r6 | run-log에 `ask:` 2줄, `answer:` 없음 | 설계대로 |
| `SubagentStart` 입력에는 `permission_mode`가 없음. `SubagentStop`에는 `permission_mode`, `effort: {"level": …}`, `background_tasks`, `session_crons`, `stop_hook_active`가 있음 | r1 | `SubagentStart.jsonl`, `SubagentStop.jsonl` | `start:`에서 `mode=`를 빼고 `stop:`에 `mode=`, `effort=`를 넣음 |
| maxTurns로 끝난 에이전트에는 `SubagentStop`이 오지 않음. meta 파일 `~/.claude/projects/<proj>/<session>/subagents/agent-<id>.meta.json`이 `"finished": true`, 마지막 assistant 항목의 `stop_reason`이 `tool_use` (정상 종료는 `end_turn`) | r4, r7 | `SubagentStop.jsonl`에 해당 id 없음, meta·transcript 파일 | `lib/ma_subagent.sweep`이 `run-log.py`와 subagent-log start/stop 때 `stop: … end=partial`을 씀. `run-log.py`가 `PARTIAL:` 한 줄을 출력 |
| transcript assistant 항목에 `effort`가 남음 | r1 | 서브에이전트 transcript `effort: low` | 4.7.2절 [미확인] 4 해결 |
| `-p`에서는 `Agent` 호출이 `run_in_background` 없이도 비동기가 됨 (`status: async_launched`, meta `requestShape: background`). 그때 `PostToolUse(Agent)`에는 결과가 없음. 동기 호출의 `tool_response`에는 status, totalTokens, usage, content가 있음 | r1, r7 | `PostToolUse.jsonl`, meta 파일 | 기록은 Subagent 이벤트와 sweep에 맡기고 `PostToolUse(Agent)`는 쓰지 않음 |
| `result=`(마지막 메시지 첫 줄)가 판정어가 아닐 수 있음 (r1: "The command \`pwd\` returned:") | r1 | run-log `stop:` 줄 | 4단계 에이전트 정의에 "첫 줄에 판정어" 규칙을 둠. 모니터는 `startswith('FAIL')`로 봄 |
| `-p`에서 모델이 부른 `Skill`은 권한이 필요함. 거부되면("Skill tool permission denied") 스킬 내용도 frontmatter hook도 등록되지 않음 | live-t5, live-t5b (2026-10-25) | `claude --debug hooks` 로그: `PreToolUse:Write`에 scope-guard만 실행 | F28. `-p` 시험에는 `--allowedTools Skill`을 줌. 대화형에서는 사용자가 허용 |
| 스킬 hook `plan-approved-check.py`가 메인 세션의 `Write`를 막고, 플러그인 hook `scope-guard.py`가 `my-agent:explorer` 안의 `Read /etc/hosts`를 막음. 8개 에이전트가 init에 모두 뜨고 `start: configured=sonnet`, `stop: actual=claude-sonnet-5-5` | live-t5c (2026-10-25, `-p` haiku, `--allowedTools Skill Agent Write Read Glob`) | stream `tool_result`: "…(G1b). 작업 폴더 밖 쓰기", "scope-guard: explorer의 읽기 범위 밖입니다" | 2·3·4단계 실제 동작 확인 |

## 수동 절차

### 7. G1·G3 팝업 알림

1. `~/dev/labs/my-agent-sandbox/`에서 `claude --plugin-dir ~/dev/my-agent`로 대화형 세션을 시작함 (`claude-sessions` 앱이 떠 있는 상태)
2. "AskUserQuestion으로 아무 질문 하나를 보여 줘"라고 요청함
3. 팝업이 뜬 채 10초, 70초를 기다리며 `claude-sessions` 알림이 오는지, `Notification` hook이 어떤 `notification_type`으로 실행되는지 봄 (`.probe/Notification.jsonl`, probe-hooks.json에 `Notification` 줄을 더해서)
4. 결과를 이 표의 7번 줄과 4.9절에 적음. 알림이 없어도 결정은 바꾸지 않음(4.9절)

### 9. status line 비용에 서브에이전트 포함 여부

1. 같은 세션에서 status line 명령이 받는 JSON을 파일로 남기도록 임시 설정함 (`statusLine.command`를 `tee`로 감쌈, 연습 프로젝트의 `.claude/settings.json`)
2. 서브에이전트 호출 전의 `cost.total_cost_usd`를 적음
3. `my-agent:probe-worker`를 한 번 부르고, 끝난 뒤의 값을 적음
4. 차이를 run-log `stop:` 줄의 `in`/`out`/`cw`/`cr` × `monitor/prices.json` 정가와 비교함. 비슷하면 포함, 0에 가까우면 미포함
5. 결과를 4.8절과 이 표의 9번 줄에 적음

### 6. 세션 종료와 백그라운드 에이전트

1. 대화형 세션에서 `my-agent:probe-worker`를 `run_in_background: true`로 부르고 `sleep 60; echo late`를 시킴
2. 곧바로 `/exit`로 세션을 끝냄
3. 1~2분 뒤 meta 파일의 `finished`와 transcript 마지막 항목 시각, run-log `stop:` 줄을 봄. `late`가 transcript에 있으면 계속 돈 것

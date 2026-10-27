# my-agent 유지보수 노트

레벨마다 "현재 상태 · 외부 동작 의존 · 주의할 점"을 적습니다(설계 문서 4.11절). 고친 내용은 해당 레벨 절에 날짜와 함께 더합니다.

## L1 오케스트레이션 (`SKILL.md`, `l1-orchestration/`)

**현재 상태 (2026-10-25)**

- `SKILL.md`: 핵심 규칙(질문 규칙, 게이트, 레벨, `.active`, 데이터와 지시, phase 파일), 인자, Intake, status, continue, 중단, Recorder 규칙, 실패 처리, 작업 중 수정.
- `phases/define.md` · `plan.md` · `build.md`(workflow 규칙 포함) · `accept.md`(개발 프로파일의 G3 포함), `profiles/general.md` · `research.md` · `dev.md`. Router가 요청을 보고 프로파일을 정한다(묻지 않음).
- frontmatter hook 2개: `plan-approved-check.py`(G1b), `verdict-fresh-check.py`(커밋·결과물 복사 전 판정 최신성). `/my-agent`가 실제로 실행된 뒤에만 걸린다(F28).
- 바깥으로 나가기 전 점검(`secret-scan.py`)과 회고를 SKILL.md와 phase 파일이 부른다. 회고(`accept.md`)는 집계(`gate-report.py tally` → `gate-tally.md`), `my-agent:gate-analyst`의 해석(→ `gate-report.md`), 복사(`gate-report.py copy`), 개선점 올리기(`feedback.py`) 순서다(2026-10-26).

**외부 동작 의존**

- 압축 뒤에는 스킬 앞부분 5,000토큰만 다시 붙는다. 핵심 규칙은 SKILL.md 앞 6,000자 안에 둔다(`test_skill_md`가 확인).
- 스킬 본문의 `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SKILL_DIR}`는 바뀌지만, Read로 읽는 phase 파일 안의 변수는 바뀌지 않는다. SKILL.md가 바꿔 쓰라고 지시한다.
- `$CLAUDE_CODE_SESSION_ID`가 메인 세션 Bash에 들어온다(F27). `.active`의 `session:`과 `step:` 줄이 이 값을 쓴다.

**주의할 점**

- run-log 명령은 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" <kind> key=value…` 전체 형태로 쓴다. `test_skill_md`가 모든 명령을 실제로 돌려 본다.
- 대화형 검증에서 고친 L1 규칙(2026-10-25): phase·프로파일 파일의 팝업은 선택지를 그대로 쓴다(Sonnet L1이 dev NIT 팝업 순서를 바꿨음). `git`이 든 명령에 `$(`·백틱을 넣지 않는다(verdict hook이 커밋인지 판단 못 함). L1은 세션 모델로 돈다(F13). `step:`의 `model=`은 `run-log.py`가 transcript에서 읽는다.
- 파일 표시는 모니터 파서와 맞춘다: `## Approval`의 `- Approved <YYYY-MM-DD HH:MM> G1b`, `## Confirmation`의 `Confirmed <…>`, `## 완료 기준` 번호 목록, `intake.md`의 `Status:`/`Location:`/`Profile:`/`Request:`.

## L2 설계 · 판정 (`l2-design-judge/agents/`)

**현재 상태 (2026-10-25):** `architect`, `plan-reviewer`, `verifier`, `reviewer`, `gate-analyst`(2026-10-26 추가, 회고에서 결정 집계를 해석. 2026-10-27 effort를 medium에서 high로 올림). 모델·effort·도구는 4.5절 표 그대로(`test_agents`가 확인). 프로파일별 점검 목록(general / research / dev)을 본문에 직접 씀.

**정해 둔 것**

- 모니터 `web/index.html`의 L2 에이전트 목록에 gate-analyst가 없음(2026-10-26 결정으로 그대로 둠).
- 판정자 점검: `tests/judge-fixtures/run-judge-check.sh`(유료, 노트마다 verifier 1회). verifier나 reviewer를 고치면 돌린다. 2026-10-25 4/4 일치.
- 결과 첫 줄: plan-reviewer `READY FOR APPROVAL` | `REVISE`, verifier `Verdict: ALL PASS` | `Verdict: FAIL`(아래에 `- <번호>. PASS|FAIL <근거>`), reviewer `BLOCKER <개수>`.
- 마지막 메시지 첫 줄이 run-log `result=`가 되고 모니터가 `startswith('FAIL')`로 본다. 첫 줄에 판정어가 없으면 판정이 화면에 안 나온다(F26).

## L3 작업 (`l3-workers/agents/`)

**현재 상태 (2026-10-25):** `explorer`(maxTurns 30, 파일을 쓰지 않음 → L1이 보고를 `explore.md`에 저장), `researcher`(40), `writer`(40), `coder`(60, 커밋하지 않음).

**정해 둔 것**

- 모든 작업자에 `maxTurns`를 둔다. 걸리면 SubagentStop이 오지 않고 sweep이 `end=partial`로 남긴다(F22).
- researcher 노트 항목은 `- <주장> · <출처 URL> · "<인용>"` 또는 `- 찾지 못함: …`만. verifier·writer가 같은 형식을 쓴다.
- workflow 안에서도 `agentType: 'my-agent:<name>'`이면 정의 파일과 hook이 그대로 적용된다(F29).

## L4 도구 · 가드 (`l4-tools-guards/`)

**현재 상태 (2026-10-25)**

- 플러그인 hook(`hooks/hooks.json`): `scope-guard.py`(모든 도구, `my-agent:` 에이전트의 읽기·쓰기 범위, `onFailure: block`. gate-analyst는 읽기 `gate-tally.md`·`gate-report.md`, 쓰기 `gate-report.md`만, 2026-10-26), `subagent-log.py`(call/start/stop), `permission-log.py`(G2 ask/answer), `session-notice.py`(SessionStart). 기록 hook은 항상 exit 0, `onFailure` 없음.
- 스킬 hook: `plan-approved-check.py`, `verdict-fresh-check.py`. `plan-approved-check`은 승인 뒤에도 작업 위치·agent-tasks·선언된 결과물 위치 밖 쓰기에 `ask`를 돌린다(auto 모드가 묻지 않으므로, 2026-10-25). 회고 복사 폴더(`ma_gate_report.report_dir()`, `$MA_GATE_REPORT_DIR`)도 묻지 않고 통과한다(2026-10-26). 막는 hook 셋은 오류가 나면 exit 2로 막는다.
- `lib/ma_bash`: Bash 명령의 쓰기 대상·읽는 경로·복사 원본·git 변경 판정. 못 잡는 쓰기(`python -c` 등)는 남는 위험(4.4절). 셸 예약어, `bash -c`/`eval`, `cd`는 따라가고, 따라가지 못하는 형태(명령 치환, 열린 heredoc, 변수 경로, 변수 `cd`, symlink+쓰기)는 None(막음). git은 읽기 하위 명령 허용 목록.
- `ma_bash.http_sends`: curl·wget이 데이터를 보내는지(짧은 옵션 묶음 `-sd`, `-XPOST`, `--data=…` 포함). scope-guard는 verifier에게만 적용한다(사용자 결정 2026-10-25). curl 옵션이 늘면 `CURL_SEND_*`를 고친다.
- `lib/ma_path`: 경로 비교(`under`, `same`)는 대소문자를 접어서 한다. hook의 경로 비교는 모두 이것을 쓴다(macOS 볼륨에서 `Docs/agent`로 우회하던 빈틈, 최종 리뷰 C3).
- `lib/ma_plan`: plan.md의 승인 줄·`Prototype: requested` 읽기. scope-guard는 architect가 이 두 줄을 새로 넣는 쓰기를 막는다(C2).
- `permissions/permissions.json`: G2 ask/deny. 2026-10-25 설치 때 사용자 설정(`~/.claude/settings.json`)에 병합했다(백업 `settings.json.backup-20261025-141535`). 샌드박스 `.claude/settings.json`에도 같은 사본이 있다. 규칙을 바꾸면 두 곳과 `test_permissions`를 함께 고친다. "작업 디렉터리 밖에 쓰기"는 규칙 문자열이 없어 Claude Code의 기본 확인에 맡긴다. git 옵션이 하위 명령 앞에 오는 꼴(`git -C … commit`)은 `Bash(git * commit*)`처럼 가운데 `*` 규칙으로 잡는다. 접두어 규칙만으로는 지나갔음(2026-10-25, 대화형으로 ask·deny 둘 다 확인).
- `scripts/run-log.py`: L1 기록. 쓰기 전에 sweep을 돌려 maxTurns로 끝난 작업자를 닫고 `PARTIAL:`/`MISMATCH:`를 출력한다. `step:` 줄의 메인 모델은 `<projects>/*/<session>.jsonl`의 마지막 메인 assistant 항목에서 읽고(`ma_subagent.main_model`, 끝 4MB만), 없을 때만 `--model`을 쓴다.
- `lib/`: `ma_active`(`.active` 찾기, worktree면 메인 트리로. 색인은 저장소 안에서 그 루트 줄만 본다, C1), `ma_logline`(줄 형식), `ma_subagent`(transcript 합계, `stop:` 줄, sweep). `SendMessage`로 이어 부른 에이전트는 같은 id로 다시 시작하므로 `stop:`은 `start:` 수만큼 쓰고, 이어 부른 실행은 마지막 `start:` 시각 −2초부터 센다(`run_since`, F33). sweep은 첫 실행만 닫는다(meta가 첫 실행의 finished를 그대로 두므로). 실행 중에도 user 항목이 들어오므로 user 항목으로 실행을 나누지 않는다. `ma_gate_report`(run-log 결정 집계와 `cost:` 구간별 비용·토큰, 복사 폴더 `report_dir()`, 2026-10-26).
- `scripts/`: `run-log.py`, `feedback.py`, `secret-scan.py`, `check-run.py`(시나리오 통과 조건), `gate-report.py`(회고 집계 `tally`·복사 `copy`, 종료 코드 0/1/2/3, 2026-10-26). 종료 코드 3(`gate-tally.md`나 복사본을 쓰지 못함)은 261026 계획 사양(0/1/2)에 없던 보완이고, ARCH 4.11과 `accept.md`에는 적혀 있다.
- 테스트: `python3 -m unittest discover -s l4-tools-guards/tests` (174개). 시나리오는 `tests/scenarios/`.

**외부 동작 의존 (탐침 결과, `probe/results.md`)**

- maxTurns로 끝난 서브에이전트에는 SubagentStop이 없다. sweep은 `~/.claude/projects/<프로젝트>/<세션>/subagents/agent-<id>.meta.json`의 `"finished": true`와 transcript 마지막 assistant 항목의 `stop_reason`(≠ `end_turn`)을 본다. 이 파일 형식이 바뀌면 `end=partial`이 사라진다. `MA_CLAUDE_PROJECTS`로 경로를 바꿀 수 있다.
- **sweep의 한계:** `end_turn`이 아닌 모든 종료를 partial로 센다. maxTurns가 아닌 다른 이유로 끊긴 경우도 E의 "작업 단위 두 번 중단"에 들어간다.
- worktree 에이전트의 `cwd`는 `.claude/worktrees/agent-<id>`이고 `.git`은 `gitdir:` 파일이다. `ma_active.main_worktree`가 이것을 따라간다.
- `SubagentStart`에는 `permission_mode`가 없다. 권한 모드는 `stop:`의 `mode=`에 남는다.
- `PermissionRequest` 입력에 `agent_id`가 들어온다. 거부는 이벤트가 없어 기록되지 않는다.

**아직 열린 탐침 항목**

- 6: 세션이 끝날 때 백그라운드 에이전트가 같이 끝나는지 — 대화형 절차(`probe/results.md`).
- 7: G1·G3 팝업의 `claude-sessions` 알림 — 대화형 절차.
- 9: status line 금액에 서브에이전트 비용이 들어가는지 — 대화형 절차.

**남는 위험 (Q8)**

- G1b 하드 게이트는 스킬 hook이라 `/my-agent`를 부르기 전의 새 세션에는 없다. `SessionStart` 알림은 지시문일 뿐이다. 승인 없이 진행된 일이 회고에 나오면 플러그인 hook으로 옮기는 것을 다시 검토한다.
- `-p`나 권한 창에서 `Skill` 호출이 거부되면 스킬 hook도 등록되지 않는다(F28). 그 세션에서는 G1b가 `SessionStart` 알림으로만 지켜진다.

**진단 위치**

- 불러오기 오류는 `/hooks`가 아니라 `/plugin`의 **Errors** 탭에 나온다.
- manifest, 에이전트 frontmatter, `hooks.json`을 고칠 때마다 `claude plugin validate --strict .`(플러그인 폴더)과 `claude plugin validate --strict ~/dev/my-plugins`(마켓플레이스)를 돌린다.
- 기록이 빠졌으면 run-log의 `log-error` 줄, hook 출력, `claude --debug` 로그를 본다.

**설치와 되돌리기 (Task 12, 사용자 승인 뒤)**

- 설치 전에 `~/.claude/settings.json`을 `~/.claude/settings.json.bak-<YYMMDD-hhmmss>`로 복사한다.
- 설치: `claude plugin marketplace add ~/dev/my-plugins`, `claude plugin install my-agent@my-plugins`. 설치한 뒤에는 `--plugin-dir`를 같이 쓰지 않는다(같은 이름이 두 번 불림).
- 되돌리기: `claude plugin disable my-agent@my-plugins`(hook이 모두 빠짐) → 필요하면 `claude plugin uninstall my-agent@my-plugins`와 `claude plugin marketplace remove my-plugins` → 백업한 `settings.json`을 되돌린다.
- 자기 수정으로 hook이 깨졌을 때: 일반 터미널에서 `claude plugin disable my-agent@my-plugins` → `git checkout -- <파일>` → `claude plugin enable my-agent@my-plugins`.

## 모니터 (`monitor/`, 레벨 밖)

- `monitor-up.py`가 8765–8775 중 첫 빈 포트에 띄운다. 상태는 `~/dev/agent-tasks/monitor.json`, 출력은 `monitor.log`. 끄기는 `/my-agent:monitor stop`.
- 여는 방식은 `~/dev/agent-tasks/monitor-config.json`(`window`/`tab`). 메뉴바 앱은 `monitor/menubar/`이고, 로그인 항목 해제는 `login-item.sh uninstall`.
- 가격표는 `~/dev/agent-tasks/prices.json`이 있으면 그것을 쓴다.
- 미니 창 (2026-10-27): 메뉴바 아이콘 왼쪽 클릭은 List/Detail 미니 창, 오른쪽·Ctrl 클릭은 기존 메뉴. 화면 설정(`mode`, `pinned`, `frame.list`, `frame.detail`)만 UserDefaults suite `my-agent.monitor-menubar`에 저장한다(지우기: `defaults delete my-agent.monitor-menubar`). `/api/tasks` 요약에 읽기 전용 `elapsed` 필드가 늘었다.
- 미니 창의 Detail은 `web/index.html`의 전역 `selectTask`와 처음 load 때의 `#task=` hash 읽기에 기댄다. 둘 중 하나의 이름이나 형식을 바꾸면 Detail 선택이 깨진다. `tests/test_web_contract.py`가 이를 잡는다.
- List 깜빡임(진행 중·답 대기 줄의 기호와 막대 현재 칸)은 웹 `.dot.run`의 `pulse`(1.4초, 불투명도 .3)에 맞춘 값이다. 웹 쪽 값을 바꾸면 `menubar/Sources/Views.swift`도 함께 맞춘다. Reduce Motion이면 멈춘다.
- List 높이·상태 색 (2026-10-27): 상태 색은 `web/index.html`의 `--st-*`와 `menubar/Sources/ListModel.swift`의 `statusPalette` 두 곳에 있다. `tests/test_menubar.py`의 `test_palette_matches_web`이 둘이 같은지 본다. 한쪽을 바꾸면 다른 쪽도 바꾼다.
- `--ok`/`--run`/`--gate`/`--l1-soft`는 상태 밖(게이트 결과, L1 표시 등)에서도 쓰므로 상태 색을 바꿀 때 건드리지 않는다.
- 웹에는 상태 없는 작업의 tone이 없다. 서버가 상태를 항상 셋 중 하나로 보내기 때문이다(`monitor/taskview.py:173`).
- List 높이는 `ListMetrics` 상수로 계산하고, 뷰가 같은 상수로 높이를 고정한다. 줄 모양을 바꾸면 상수도 맞춘다.
- List 높이 애니메이션은 제약 풀기 → 애니메이션 → completion에서 높이 고정·저장 순서다. 순서를 바꾸면 애니메이션이 사라지거나 중간 frame이 저장된다.
- 미니 창 List 줄은 단계 이름을 그리지 않는다. `stepLabel`은 `--print-list`(`renderList`)가 쓰므로 남아 있다.
- 첫 클릭 (2026-10-28): 다른 앱이 앞에 있을 때 미니 창의 첫 클릭이 필터·List/Detail·핀·줄에 바로 적용된다. `FirstClickHostingView`가 first mouse를 받고, List 줄은 SwiftUI 스크롤 컨테이너가 받지 않으므로 `FirstClickWindow`가 제자리에서 놓인 클릭만 창이 key가 된 뒤 다시 보낸다(4pt 넘게 움직인 끌기는 다시 보내지 않음). GUI 테스트는 없다.
- 알려진 표시 문제: `call:`만 있고 `start:`가 없는 호출(거부되었거나 시작하지 못한 에이전트)은 계속 "running"으로 보인다. 내용 없는 partial의 `result=-`가 결과 칸에 `-`로 보인다.

## 설치 (2026-10-25)

- (처음 설치 기록) `claude plugin marketplace add ~/dev/my-agent` (이름 `my-agent-dev`, 사용자 설정의 `extraKnownMarketplaces`에 directory 소스로 들어감), `claude plugin install my-agent@my-agent-dev` (사용자 범위, 0.1.0).
- `claude plugin list`가 `Read from: /Users/jahoonjin/dev/my-agent`를 보였음(옮긴 뒤 경로는 아래 절). 디렉터리 소스라 고친 내용은 새 세션(또는 `/reload-plugins`)에서 바로 반영된다(F17). `--plugin-dir`는 더 쓰지 않는다.
- 새 세션에서 `my-agent:` 에이전트 8개와 `my-agent:my-agent` 스킬이 보임. (2026-10-26 gate-analyst 추가로 9개.) `/my-agent:monitor`는 `disable-model-invocation`이라 모델 목록에는 없고 사람이 부를 때만 뜬다.
- 전역 설정 `"model": "sonnet"`이라 L1은 세션 모델(Sonnet)로 돈다(F13). 설계대로 opus로 하려면 세션을 opus로 연다.

## my-plugins로 옮김 (2026-10-25)

- 플러그인 폴더를 `~/dev/my-agent`에서 `~/dev/my-plugins/plugins/my-agent`로 옮겼다. `~/dev/my-plugins`가 마켓플레이스(`my-plugins`)이고 git 저장소다. 다른 플러그인은 `plugins/<이름>`에 두고 `.claude-plugin/marketplace.json`에 항목을 더한다.
- 마켓플레이스 상대 경로는 그 폴더 안만 가리킨다(`..` 불가, 바깥 심볼릭 링크는 읽지 않음). 바깥 폴더를 가리키려면 `command` 소스뿐이라 옮기는 쪽을 골랐다.
- 다시 설치: `marketplace remove my-agent-dev` → `marketplace add ~/dev/my-plugins` → `install my-agent@my-plugins`. `claude plugin list`는 `Read from: /Users/jahoonjin/dev/my-plugins/plugins/my-agent`.
- 플러그인 버전(`intake.md`의 `my-agent:`)은 플러그인 폴더만 본다: `git -C "${CLAUDE_PLUGIN_ROOT}" log -1 --format=%h -- .`(`test_plugin_version_scoped_to_plugin_folder`). 다른 플러그인의 커밋은 `continue`의 규칙 변경 팝업을 띄우지 않는다.
- 옛 경로가 남은 곳: 날짜가 적힌 계획서·탐침 결과·검증 기록(그때의 기록이라 고치지 않음), `~/dev/my-agent-monitor/`(손대지 않는 폴더).

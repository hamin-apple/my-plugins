# my-agent monitor 설계

- 상태: 설계 v0.3 (2026-10-28, 아키텍처 v0.27에 맞춤: 코드 위치 정정, 5.2 줄 형식에 `unit=`·`revision` 상태·`Scope change`·되돌리기 `back=`/`archive=`, 모니터가 L4 `lib/ma_schema.py`로 읽음). v0.2 (2026-10-25). v0.1 승인 뒤 구현함(`~/dev/my-agent-monitor/`). v0.2는 플러그인에 넣는 결정(6.1절, 아키텍처 v0.20 Q14)을 더함. 같은 날 탐침 결과(아키텍처 v0.21)로 `start:`에 `session=`, `stop:`에 `mode=`·`effort=`가 붙음. 모니터는 이 필드를 읽지 않아도 됨.
- 코드 위치: 플러그인 안 `monitor/`(`~/dev/my-plugins/plugins/my-agent/monitor/`, 6.1절). 처음 구현은 `~/dev/my-agent-monitor/`에 있었습니다.
- 화면 기준: 목업 v22 `~/dev/my-agent/.superpowers/brainstorm/29416-1792798606/content/webapp-v22.html`
- 관련 문서: `my-agent-architecture.md` v0.19. 7절의 "my-agent 쪽 변경"은 v0.19에 반영했습니다.

## 1. 무엇이고 왜 필요한가

my-agent는 phase 4개, 단계 8개, 게이트 5개(G1a, G1b, G2, G3, E)를 거치며 서브에이전트 여러 개를 병렬로 부립니다. 진행 상황은 작업 폴더(`<프로젝트>/docs/agent/<task-id>/`)의 파일과 `run-log.md`에 흩어져 있어서, 터미널만으로는 다음을 한눈에 보기 어렵습니다.

1. 지금 어느 단계이고, 누가 일하고 있고, 사람의 답을 기다리는지
2. my-agent 아키텍처(L1~L4)의 어느 구성 요소가 쓰였는지
3. 결과물과 중간 결과물(mock-up), 작업 파일
4. 단계별 기록을 task-id마다 다시 보기

모니터는 이 네 가지를 Mac의 로컬 웹 페이지로 보여 줍니다. **읽기만 합니다.** my-agent의 진행에 끼어들거나 파일을 바꾸지 않습니다.

## 2. 목표 · 비목표 · 실패 조건

**목표**

- 진행 중인 작업을 2초 안에 반영해 보여 줍니다.
- 끝난 작업과 중단된 작업도 같은 화면으로 다시 봅니다(기록 재생).
- 단계별·모델별 토큰, 시간, 비용(추정)을 보여 줍니다.

**비목표**

- 게이트에 답하기, 작업 시작·중단 같은 조작. 사람의 답은 터미널 팝업에서만 합니다.
- 다른 기기나 다른 사람에게 공유, 원격 접속
- 정확한 청구 금액. 비용은 정가 기준 추정과 statusline 값(참고)뿐입니다.
- 다른 OS 지원

**실패 조건 (동작해도 실패로 봄)**

- 모니터가 작업 폴더, run-log, transcript에 무엇이든 쓰거나 잠금을 걸어 my-agent 진행에 영향을 줌
- 기록 파일의 형식이 조금 달라 한 작업을 못 읽을 때 화면 전체가 멈춤. 그 작업만 "읽기 오류"로 표시하고 나머지는 보여 줘야 합니다.
- 화면에 보이는 값이 기록과 다름. 기록에 없는 값은 지어내지 않고 `–`로 둡니다.

## 3. 제약

- macOS, 브라우저는 Chrome 기준
- 서버는 `127.0.0.1`에만 열고, Python 3 표준 라이브러리만 씁니다. 설치할 의존성이 없어야 합니다.
- 프런트엔드는 HTML 파일 하나(+ 필요하면 JS/CSS 파일)로, 빌드 단계가 없습니다. 웹 폰트(IBM Plex)는 Google Fonts에서 읽고, 오프라인이면 시스템 글꼴로 대체합니다.
- `~/dev/tools/claude-sessions`는 읽기 전용입니다. 모니터는 그 코드를 가져다 쓰지 않습니다(가격표는 자체 파일).
- 서버는 파일을 쓰지 않습니다. 실행 스크립트 `monitor-up.py`만 `~/dev/agent-tasks/monitor.json`과 `monitor.log`를 씁니다(6.1절).

## 4. 화면 (목업 v22로 확정)

목업 v22가 화면의 기준입니다. 구현은 목업의 HTML/CSS/렌더 코드를 출발점으로 삼고, 가짜 데이터(`TASKS`, `MOCKS`, 가짜 실시간 갱신 `QUEUE`)만 서버 API로 바꿉니다.

**공통**

- 위쪽 막대: `my-agent monitor`, 실시간 표시, 작업 선택(좁은 화면), EN/한국어 전환
- 왼쪽 사이드바: 작업 목록(전체/진행 중/완료/중단 필터, 단계 8칸 미니 막대)
  - 경계를 끌어 너비 조절(200~480px), 더블클릭하면 기본값으로
  - 접기/펴기. 접으면 작업마다 상태 아이콘만(● 진행 중, ? 답 기다림, ✓ 완료, ■ 중단)
- 작업 머리: task-id, 상태, 작업 제목, 프로파일·경로·시작·경과
- 탭 4개: Dashboard / Architecture / Deliverables / Log

**언어**

- 제목(탭, 섹션, 타일 이름, 표 머리글, phase·단계·게이트 이름, 레벨 이름, 구성 요소 설명줄)은 항상 영문입니다.
- 나머지 UI 문구는 EN/한국어로 바꿀 수 있습니다. 기본은 EN, 선택은 브라우저에 저장합니다.
- 기록에서 읽은 글(작업 제목, run-log 내용, 결과물 이름, mock-up, 파일 내용)은 바꾸지 않습니다.

**1 Dashboard**

- 왼쪽: 단계 목록. phase 4개 아래 단계 8개를 한 줄 카드로(시간 · 토큰 · 비용), 게이트 줄(passed / awaiting / pending), rev 칩(`rev0 · archived`, `rev1 · current`)과 단계 표시(`↺ rev1`, `from rev0`)
  - 단계를 누르면 Log 탭 재생에서 그 단계의 첫 기록으로 갑니다.
- 오른쪽: 타일 6개를 2열로. 순서는 Now, Elapsed / Criteria, Tokens / Escalation, Cost
  - Now: 지금 단계와 실행 중인 서브에이전트(모델, effort), 답을 기다리면 그 게이트
  - Criteria: 통과 수 / 전체, 기준마다 한 칸
  - Tokens: 사용 / 예상, 진행 막대 (예상은 참고, E 조건 아님)
  - Escalation (E): Verify 연속 FAIL n/3, slice 중단 n/2. 두 값으로만 Normal / Caution / E raised
  - Cost: 모델별 추정 합계와 statusline 값(작게, "statusline"이라고 표시)
- 아래: Models 표(모델별 호출, 토큰, 시간, 비용. 메인 세션 행 포함), MISMATCH 경고

**2 Architecture**

- L1~L4 레벨마다 구성 요소 4개. 이 작업에서 쓰인 것은 밝게, 기록 수 표시, 지금 실행 중이면 점
- 이름은 소문자: L1 router · orchestrator · gatekeeper · recorder, L4 tools · hooks · permissions · scripts
- L2·L3 칸은 두 줄(역할 / 모델 · effort)
- 누르면 오른쪽에 설명, 모델·effort, 이 작업에서의 기록

**3 Deliverables**

- 왼쪽: 최종 결과물, 중간 결과물(G1b에서 승인한 mock-up, rev가 여럿이면 `⇄ compare` 줄 단위 비교), 작업 파일 트리
- 오른쪽: 누른 파일의 미리보기(고정)

**4 Log**

- 머리줄: `4 · Log` 옆에 Replay / Parallel timeline 전환, 오른쪽 끝에 `run-log.md · task-id`와 `↗ Components`
- Replay: 처음/이전/다음/자동 재생, 속도 0.5×~4×, 슬라이더, 키보드(← → Space Home End)
  - 왼쪽 단계 목록, 가운데 콘솔(레벨 색 태그)과 이벤트 카드(모델, effort, MISMATCH, G1b 시점이면 mock-up), 오른쪽 그 시점의 작업 파일(새로 쓴 파일은 타이핑 효과)
- `↗ Components`: "이 순간의 구성 요소"를 별도 창으로 엽니다. 재생 위치를 따라 바뀌고, 창 크기와 위치를 기억합니다.
- Parallel timeline: 서브에이전트 호출을 막대로(모델 색, `×N`은 N줄, MISMATCH 빨간 테두리), 단계 띠와 게이트 표시, 최대 동시 실행 수. 막대를 누르면 재생의 그 시점으로

**효과**

- 숫자 올라가기, 진행 막대, 실행 중 점 깜빡임, 화면 전환 애니메이션, task-id 글자 섞기 등 목업에 있는 것
- 실시간 갱신 때는 이미 그린 것을 다시 애니메이션하지 않습니다(목업 v13에서 고친 문제).
- `prefers-reduced-motion`이면 효과를 끕니다.

## 5. 데이터 출처

| 화면 값 | 읽는 곳 |
|---|---|
| 볼 프로젝트 | 프로젝트 목록 파일 (5.1) |
| 작업 목록, 상태, 제목, 프로파일, 위치, 시작 | `intake.md` (`Status:`, `Profile:`, `Location:`, 요청 줄), 폴더 이름(task-id) |
| 진행 중인 작업 | `docs/agent/.active` (task, phase, session, started) |
| 단계 진입, 단계별 시간 | run-log `step:` 줄 (5.2, my-agent 쪽 변경) |
| 서브에이전트 호출·모델·effort·토큰·시간·결과·MISMATCH | run-log `call:` / `start:` / `stop:` 줄 (아키텍처 4.7.2절) |
| 메인 세션 토큰 | 메인 transcript (5.3) |
| 게이트, 팝업 질문과 선택 | run-log 팝업 줄, `scope.md ## Confirmation`, `plan.md ## Approval` |
| rev | run-log `revision:` 줄, `plan.md`/`scope.md ## Revisions`, `archive/` |
| Criteria | `scope.md` 완료 기준(일반 프로파일은 `plan.md` 맨 위 범위 요약), `verify.md` 판정 |
| Escalation | run-log의 verifier `stop:` 결과(연속 FAIL), 작업자 중단 기록 |
| 예상 토큰 | `plan.md ## Estimate` |
| 비용 추정 | 토큰 × `prices.json` (5.4) |
| 비용 statusline | run-log `cost:` 줄 |
| 파일 트리, 쓴 시각, 미리보기 | 작업 폴더 파일과 수정 시각 |
| mock-up과 버전 비교 | `plan.md ## Mock-up`, `archive/*/plan.md ## Mock-up` |
| 최종 결과물 | `intake.md`의 `Delivered:`, run-log `deliver` 줄 |

### 5.1 프로젝트 목록

- 파일: `~/dev/agent-tasks/projects.txt`. 한 줄에 프로젝트 경로(작업 위치) 하나
- my-agent가 Intake에서 작업 위치를 정한 뒤, 목록에 없으면 한 줄 추가합니다. 지우지는 않습니다.
- 모니터는 줄마다 `<경로>/docs/agent/*/intake.md`를 찾습니다. 경로가 없어졌으면 건너뜁니다.

### 5.2 run-log 줄 (모니터가 읽는 계약)

모니터의 파서는 아래 줄만 해석하고, 모르는 줄은 무시합니다. 줄 읽기는 L4 `lib/ma_schema.py`의 `split_line`을 그대로 씁니다(아키텍처 4.7절 "형식의 단일 소스"). 이 형식은 아키텍처 문서 4.7.2절에도 같은 내용으로 넣고(7절), `run-log.py`, `subagent-log.py`, 모니터가 같은 예시 파일(fixture)로 시험합니다.

**줄 형식:** 한 줄에 기록 하나. `<YYYY-MM-DD HH:MM:SS> <종류>: <key=value ...>`. 값에 공백이 있으면 큰따옴표로 감쌉니다. 값 안의 `"`는 `\"`, `\`는 `\\`로 쓰고 줄바꿈은 공백으로 바꿉니다(아키텍처 4.7.2절). rev가 없는 줄은 가장 최근 `revision:` 줄의 rev를 따릅니다(없으면 rev0).

```text
2026-10-24 15:56:02 step: n=5 name=Execute rev=0 session=4f2a…
2026-10-24 15:56:10 call: agent=my-agent:coder model=- effort=- isolation=worktree background=true unit=u1
2026-10-24 15:56:11 start: agent=my-agent:coder id=a81c… configured=sonnet effort=medium session=4f2a…
2026-10-24 16:04:40 stop: id=a81c… unit=u1 actual=claude-sonnet-5-5 tokens=84213 in=61020 out=9870 cw=8113 cr=5210 secs=509 result=DONE end=ok mode=auto effort=medium
2026-10-24 16:01:15 ask: gate=G2 agent=my-agent:coder id=a81c… tool=Bash q="npm i fast-json-stable-stringify"
2026-10-24 16:01:31 answer: gate=G2 id=a81c… result=allowed
```

| 줄 | 쓰는 쪽 | 모니터가 쓰는 필드 |
|---|---|---|
| `step:` **(새로)** | run-log.py, 단계에 들어갈 때마다 | 시각, 단계 번호(1~8), rev, session ID. Execute로 되돌린 줄에는 `back=`(이유)·`archive=`(보관한 판정) |
| phase 진입 | run-log.py | 시각, phase |
| `ask:` / `answer:` **(나눔)** | run-log.py | 게이트(G1a/G1b/G3/E), 질문, 선택. `ask:` 뒤에 `answer:`가 아직 없으면 "답 기다림" |
| `ask: gate=G2` / `answer: gate=G2` **(새로)** | 플러그인 hook `PermissionRequest` / `PostToolUse` | 요청한 에이전트, 도구, 입력 요약, `result=allowed`. 그 에이전트가 끝날 때까지 `answer:`가 없으면 "not run (denied?)"로 표시 |
| `call:` / `start:` / `stop:` | subagent-log.py | agent_type, agent_id, 작업 단위(`unit=`), 모델(기대·실제), effort, isolation, 토큰, 시간, 결과 첫 줄, MISMATCH, 끝난 방식(`end=ok|partial|error`). 연속 FAIL은 verifier `result=`가 `Verdict: FAIL`로 시작하는 줄로 세고 rev가 바뀌면 처음부터, 작업자 중단은 (rev, `unit=`)마다 셈 |
| `revision:` | run-log.py | rev 번호, 바뀐 내용, 보관 폴더. `before=G1b`면 승인 전 계획 다시 쓰기(rev는 그대로). `state=pending` 줄과 같은 rev의 `state=done` 줄을 한 수정으로 합침 |
| `fix:` | run-log.py | 고친 것. `what="Scope change: …"`이면 승인 범위 안 조정으로 표시 |
| `cost:` | run-log.py | `session=`, `usd=` (cost_usd) |
| `stale:`, `abort`, `deliver`, `resume`, `base:`, `log-error` | 아키텍처 문서 | 표시용 |

### 5.3 메인 세션 토큰

- `step:` 줄의 session ID로 `~/.claude/projects/*/<session>.jsonl`을 찾습니다.
- 그 단계 구간(이 `step:` 줄 시각 ~ 다음 `step:` 줄 시각)의 assistant 응답 사용량(입력, 출력, 캐시 쓰기, 캐시 읽기)을 모델별로 더합니다. 같은 응답이 여러 줄로 나뉘어 있으면 응답 ID로 한 번만 셉니다.
- 같은 세션에서 my-agent와 상관없는 일을 했다면 그 몫도 들어갑니다. 화면의 Models 표에는 메인 세션 행을 "opus · main"으로 표시합니다.
- transcript를 찾지 못하면 메인 세션 행을 `–`로 둡니다.

### 5.4 가격표

- 파일: 모니터 폴더의 `prices.json`(기본값). `~/dev/agent-tasks/prices.json`이 있으면 그것을 씁니다(6.1절). 모델 ID 앞부분(예: `claude-opus-5`)마다 입력, 출력, 캐시 쓰기, 캐시 읽기 단가(USD / 1M 토큰)와 확인한 날짜
- 사람이 직접 갱신합니다. 표에 없는 모델은 비용을 `?`로 두고 Models 표 아래에 "가격표에 없는 모델" 한 줄을 띄웁니다.

## 6. 구조

```text
~/dev/my-plugins/plugins/my-agent/monitor/
├── server.py          # http.server, 127.0.0.1, 읽기 전용 JSON API + 정적 파일
├── monitor-up.py      # 이미 떠 있는지 보고 띄우기 · 창 열기 (6.1절)
├── monitor/           # 프로젝트 목록, intake, run-log, transcript, 파일 트리를 읽어 작업 모델로 (runlog · events · mdfiles · taskview 등. L4 lib/ma_schema를 import)
├── web/index.html     # 목업 v22에서 출발한 화면
├── prices.json
├── menubar/           # 메뉴바 앱 (선택)
├── tools/             # 화면 생성기 (다시 돌리면 web/index.html의 직접 수정이 사라짐)
├── tests/fixtures/    # 실제 산출물 형식대로 만든 가짜 작업 (build_fixtures.py)
└── README.md          # 실행 방법
```

- **API:** 작업 목록(요약)과 작업 하나(전체 모델) 두 가지면 충분합니다. 화면은 2초마다 다시 가져옵니다.
- **읽기 비용:** 파일 수정 시각이 바뀐 작업만 다시 읽습니다. transcript는 마지막으로 읽은 위치부터 이어 읽습니다.
- **실행:** `python3 server.py` 후 브라우저에서 엽니다. 포트는 8765를 쓰고, 쓰고 있으면 8775까지 다음 번호를 씁니다.

### 6.1 플러그인에 넣기와 자동 실행 (v0.2)

자세한 동작은 아키텍처 문서 4.7.4절에 있습니다. 모니터 쪽에서 바뀌는 것만 적습니다.

- **위치:** 코드를 플러그인 안 `monitor/`로 옮겼습니다(지금 `~/dev/my-plugins/plugins/my-agent/monitor/`). 읽는 코드는 `reader/`에서 `monitor/` 패키지로 이름이 바뀌었습니다.
- **`GET /api/health`:** `{"app": "my-agent-monitor", "root": <monitor 폴더 절대 경로>}`를 돌려줍니다. 실행 스크립트가 이미 떠 있는 서버를 알아보는 데 씁니다.
- **`monitor-up.py`:** 이미 떠 있으면 URL만 출력하고, 없으면 빈 포트에 서버를 띄웁니다. `--open`, `--no-open`, `--window`, `--tab`, `--task <key>`, `status`, `stop`을 받습니다. 여는 방식(`window`/`tab`)은 옵션, `~/dev/agent-tasks/monitor-config.json`, 기본값 `window` 순서로 정합니다. 브라우저(`default`/`safari`/`chrome`)는 `--browser` 옵션, 설정 파일의 `browser`, 기본값 `default`(기본 브라우저를 알아냄) 순서로 정하고, `monitor-up.py set-browser <값>`이 설정 파일의 `browser`만 바꿔 씁니다. 고른 브라우저가 열리지 않으면 기본 브라우저 탭으로 대체합니다. 어떤 경우에도 exit 0입니다.
- **작업 링크:** `/#task=<key>`(key는 `<sha1 8자>/<task-id>`, URL 인코딩)로 열면 그 작업이 골라집니다. 키가 틀리거나 끝난 작업이면 기존 선택 규칙을 따릅니다.
- **메뉴바 앱:** `monitor/menubar/`의 작은 앱이 진행 중 작업 수와 작업별 줄을 보이고 `monitor-up.py`를 실행합니다(`monitor/menubar/README.md`).
- **가격표 덮어쓰기:** `~/dev/agent-tasks/prices.json`이 있으면 모니터 폴더의 `prices.json` 대신 씁니다.
- **누가 띄우나:** my-agent Router가 Intake에서 작업 위치를 정한 직후, 그리고 `/my-agent:monitor`를 직접 부를 때입니다.
- **수명:** 세션이 끝나도 서버는 남습니다. `/my-agent:monitor stop`으로 끕니다.

## 7. my-agent 쪽 변경 (아키텍처 문서 v0.19에 반영)

1. **프로젝트 목록 등록:** Intake에서 작업 위치를 정한 뒤 `~/dev/agent-tasks/projects.txt`에 없으면 추가 (4.8.2절 "작업 위치")
2. **`step:` 줄:** run-log.py가 단계(1~8)에 들어갈 때마다 시각, 단계, rev, session ID를 남김 (4.7.2절 표의 L1 Recorder 행)
3. **팝업 기록을 둘로 나눔:** 팝업을 띄우기 직전에 `ask:`, 답을 받은 뒤 `answer:`. 지금은 질문과 선택을 한 줄로 남기므로, 답을 기다리는 동안은 기록이 없습니다 (4.7.2절 표의 L1 Recorder 행)
4. **줄 형식:** 5.2의 형식을 4.7.2절에 넣음
5. **G2 기록 hook:** 플러그인 hook에 `PermissionRequest`(→ `ask: gate=G2`)와 `PostToolUse`(앞의 G2 `ask:`와 같은 도구·입력일 때만 → `answer: gate=G2 result=allowed`)를 더함. matcher와 `.active` 찾기는 subagent-log와 같고, 실패해도 막지 않음(exit 0). 거부는 직접 알 수 없어 기록하지 않음 (4.4절 G2, 4.7.2절)
6. **작업자 중단 기록:** E의 "같은 작업 단위 두 번 중단"을 셀 수 있도록(v0.3부터 `unit=`으로 단위를 구분), `stop:` 줄에 `end=ok|partial|error`를 적음 (maxTurns에 걸리면 partial. 이때는 SubagentStop이 없어 sweep이 meta 파일로 씀, 아키텍처 F22) (4.7.2절, 4.8절)
7. **판정 파일 형식:** `verify.md`에 기준 번호마다 `PASS`/`FAIL` 한 줄, `scope.md` 완료 기준은 번호 목록 (4.3절 또는 4.4절)

## 8. 사용자가 정한 것

- 화면: 목업 v22 (4절 전체)
- Mac 로컬 웹 페이지, Python 서버
- E 조건에서 토큰을 뺌 (아키텍처 v0.17), 에이전트별 effort 고정 (v0.18)
- 프로젝트 찾기: my-agent가 목록에 등록
- 8단계: Recorder가 `step:` 줄을 남김
- 메인 세션 토큰: 모니터가 transcript를 읽음
- 가격표: 모니터 자체 `prices.json`
- G2: hook(`PermissionRequest` + `PostToolUse`)으로 기록. 거부는 추정으로 표시
- 코드는 `~/dev/my-agent-monitor/`, 이 문서는 `~/dev/my-agent/`
- (v0.2) 플러그인 안 `monitor/`로 옮기고, my-agent를 실행하면 같이 뜸(Router가 작업을 시작할 때). 수동 실행용 `/my-agent:monitor` 스킬도 둠

## 9. 제가 정한 것 (확인 부탁)

- 프로젝트 목록 파일 위치를 `~/dev/agent-tasks/projects.txt`로 함. 이미 `active-index.json`을 두는 폴더라서
- 기록 형식이 깨진 작업은 그 작업만 "읽기 오류"로 표시하고 나머지는 계속 보여 줌
- 서버는 표준 라이브러리만, 프런트엔드는 빌드 없이
- 2초 폴링 (파일 감시 대신). 단순하고 Mac 기본 Python으로 충분해서
- run-log 줄 형식(5.2)과, 팝업 기록을 `ask:`/`answer:` 둘로 나누는 것. "답 기다림"을 보여 주려면 질문 시점의 기록이 필요해서
- (v0.2) 이미 떠 있는 서버를 `/api/health`의 `root`로 알아보고, 다른 프로그램이 쓰는 포트는 건너뜀
- (v0.2) 브라우저는 새로 띄웠을 때만 엶. 작업을 시작할 때마다 새 탭이 열리지 않게 하려고
- (v0.2) 서버를 세션이 끝나도 남겨 둠. 여러 세션이 서버 하나를 같이 쓰고, 화면을 닫으면 하는 일이 거의 없어서
- (v0.2) 상태 파일과 로그, 가격표 덮어쓰기를 `~/dev/agent-tasks/`에 둠. `projects.txt`가 있는 곳이고, 플러그인 파일을 고치지 않아도 되어서

## 10. 만드는 사람에게 맡기는 것

- API 경로와 JSON 모양, 포트 번호
- run-log 파서 구조. 단 5.2의 계약과 fixture 테스트를 지킬 것
- transcript 이어 읽기와 캐시 방식
- 목업 코드를 파일 몇 개로 나눌지

## 11. 시험

- `tests/fixtures/`에 목업의 가짜 작업 5개(진행 중 dev, rev1 수정이 있는 research, MISMATCH가 있는 완료 작업, 일반 프로파일 완료, E로 중단)를 실제 폴더 모양으로 만들고, 화면 값이 목업과 같은지 확인합니다.
- 진행 중 작업 fixture에 run-log 줄을 몇 초 간격으로 덧붙이는 스크립트로 실시간 갱신을 확인합니다(애니메이션이 다시 돌지 않는지 포함).
- 일부러 깨진 run-log 한 줄과 없는 transcript로, 그 작업만 오류 표시되는지 확인합니다.
- my-agent 구현 뒤에는 실제 작업 하나로 끝까지 따라가 봅니다.

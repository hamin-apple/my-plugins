# ④ 수용 (Accept): 7 Verify · 8 Review → G3

Verify와 Review는 어떤 프로파일에서도 생략하지 않습니다.

## 7. Verify

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=7 name=Verify --model <메인 세션 모델 ID>`
2. `my-agent:verifier`에게 맡깁니다. 넘기는 것: 완료 기준이 있는 파일(일반 프로파일은 `plan.md`, 아니면 `scope.md`)과 `## Approval` 아래 `Scope change:` 줄, 결과물 경로, 결과 경로 `verify.md`. 작업자의 설명은 넘기지 않습니다.
3. `verify.md` 형식: 첫 줄 `Verdict: ALL PASS` 또는 `Verdict: FAIL`, 그 아래 기준마다 `- <번호>. PASS|FAIL <근거>`.
4. FAIL이면 실패한 기준 목록을 들고 ③ 구축의 Execute로 되돌립니다. 3번 연속 FAIL이면 E로 갑니다(SKILL.md "실패 처리").

## 8. Review → Deliver

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=8 name=Review-Deliver --model <메인 세션 모델 ID>`
2. `my-agent:reviewer`에게 맡깁니다. 넘기는 것: 결과물 경로, `plan.md` 경로, 결과 경로 `review.md`. 결과 첫 줄은 `BLOCKER <개수>`입니다.
3. BLOCKER가 1개 이상이면: 작은 수정이면 L1이 고치고(`fix` 줄) 다시 판정을 받습니다. 아니면 Execute로 되돌립니다.
4. **G3 보고 (채팅):** 결과 요약, 실패·미처리 목록, diff 또는 결과물, 사용 토큰과 금액(참고), **저장할 정확한 경로**.
   - 저장 위치: `## 범위 요약`(또는 `scope.md`)의 결과물 위치. 없으면 작업 폴더의 `deliverable/`.
   - 파일 이름은 영어 소문자와 하이픈. 같은 이름이 있으면 덮어쓰지 않고 `-2`를 붙입니다. 기존 파일을 고치는 작업이면 diff를 보여 줍니다.
   - 경로가 `~/dev` 밖이면 `수용` 선택을 그 쓰기의 승인으로 삼는다고 팝업 질문에 적습니다.
5. **G3 팝업:**
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="최종 수용: <task-id> → <저장 경로>"`
   - 팝업: `수용 (Recommended)` / `재작업` / `중단`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<고른 선택지>"`
6. **수용:**
   - 최종본에 SKILL.md "바깥으로 나가기 전 점검"을 합니다.
   - 작업 폴더의 최종본을 저장 위치로 복사합니다. 작업자는 작업 폴더 밖에 쓰지 않으므로 이 복사는 L1이 합니다. 판정이 최신이 아니면 hook(`verdict-fresh-check.py`)이 막습니다. 막히면 Verify부터 다시 합니다.
   - `intake.md`에 `Delivered: <경로>`를 더하고 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=<경로>`.
   - `intake.md`를 `Status: done`으로 바꾸고, `.active`와 `active-index.json`의 이 작업 줄을 지웁니다.
   - 회고: 아래 "회고"를 합니다.
   - 개발 프로파일은 이 6번 대신 아래 "개발 프로파일의 G3"를 따릅니다.
7. **재작업:** 기준이 그대로면 부족한 점을 실패한 기준처럼 들고 ③ 구축으로 되돌립니다. 기준이 바뀌는 요청이면 SKILL.md "작업 중 수정"을 탑니다.
8. **중단:** SKILL.md "중단" 절차.

## 개발 프로파일의 G3 (커밋 승인)

결과물이 커밋이므로 4~6번 대신 이렇게 합니다.

1. **채팅에 붙입니다:** `git status --porcelain`, `git diff --stat`과 주요 diff, 새 파일 목록, 판정 요약(`verify.md` `Run:`, `review.md`의 SHOULD-FIX·NIT), 제안 커밋 메시지(첫 줄은 무엇을 바꿨는지, 본문에 완료 기준 번호 `criteria: 1, 2, 3`), 사용 토큰과 금액(참고).
2. 커밋할 파일은 이번 작업이 바꾼 파일만입니다(`base` 줄 이후의 변경, `docs/agent/` 제외. `docs/agent/.gitignore`가 `# my-agent: commit`이면 작업 폴더도 포함).
3. 팝업 전후로 기록합니다.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="커밋 승인: <task-id>"`
   - 팝업: `커밋 (Recommended)` / `재작업` / `중단`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<고른 선택지>"`
4. **커밋:**
   - 커밋할 파일에 SKILL.md "바깥으로 나가기 전 점검"을 합니다.
   - `git add <파일들>` 뒤 `git commit -m "<메시지>"`. G2 권한 창이 한 번 더 뜨는 것은 일부러 두 번 확인하는 것입니다. 판정이 최신이 아니면 hook(`verdict-fresh-check.py`)이 막습니다. 막히면 Verify부터 다시 합니다. `--no-verify`는 쓰지 않습니다.
   - `intake.md`에 `Delivered: commit <짧은 sha>`를 더하고 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=commit:<짧은 sha>`.
   - `intake.md`를 `Status: done`으로 바꾸고, `.active`와 `active-index.json`의 이 작업 줄을 지웁니다. 회고를 합니다.
5. **재작업**과 **중단**은 위 7, 8번과 같습니다. 중단하면 바뀐 파일은 되돌리지 않고 목록만 보고합니다.

## E 에스컬레이션

- 조건: Verify 3번 연속 FAIL, 같은 작업 단위가 두 번 중단(`end=partial` 또는 `end=error`), workflow가 오류로 끝남, 병합 충돌이 계획 오류를 드러냄.
- 막힌 지점과 시도한 내용을 채팅에 보여 준 뒤 기록하고 팝업으로 묻습니다.
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=E q="<막힌 지점>"`
  - 팝업: `방향 제시` / `범위 수정` / `중단` (상황에 맞는 것을 맨 앞에 `(Recommended)`)
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=E choice="<고른 선택지>"`

## 회고

- 이번 작업에서 나온 개선점마다: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" add L<1-4> <task-id> "<개선점>"`.
- 그다음 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" count`. `REVIEW: L<n> …` 줄이 나오면(한 레벨에 열린 개선점 4개 이상) 사람에게 한 줄로 알립니다.
- 누락 점검: 이 세션의 서브에이전트 transcript 목록(`~/.claude/projects/<프로젝트>/<세션>/subagents/`)과 run-log의 `start:` 줄 `id`를 대조합니다. 빠진 호출이 있으면 L4 개선점으로 올립니다.
- run-log의 `stop:` 줄에 `mode=`가 auto가 아닌 것이 있으면 회고에 적습니다.

# ④ 수용 (Accept): 7 Verify · 8 Review → G3

Verify와 Review는 어떤 프로파일에서도 생략하지 않습니다.

## 7. Verify

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=7 name=Verify --model <메인 세션 모델 ID>`
2. `my-agent:verifier`에게 맡깁니다. 넘기는 것: 완료 기준이 있는 파일(`scope.md`가 있으면 `scope.md`, 없으면 `plan.md`. 일반 프로파일과 개발 프로파일의 작은 작업은 `plan.md`)과 `## Approval` 아래 `Scope change:` 줄, 결과물 경로, 결과 경로 `verify.md`. 작업자의 설명은 넘기지 않습니다.
3. `verify.md` 형식: 첫 줄 `Verdict: ALL PASS` 또는 `Verdict: FAIL`, 그 아래 기준마다 `- <번호>. PASS|FAIL <근거>`.
4. FAIL이면 아래 "Execute로 되돌리기"를 하고 실패한 기준 목록을 들고 ③ 구축의 Execute로 갑니다. 3번 연속 FAIL이면 E로 갑니다(SKILL.md "실패 처리"). 연속 횟수는 마지막 `Verdict: ALL PASS`(또는 같은 작업 수정) 뒤로 이어진 `Verdict: FAIL` 수입니다. run-log의 verifier `stop:` 줄 `result=`를 끝에서부터 셉니다(모니터도 같게 셈). `Run:`은 판정 회차일 뿐이라 PASS 뒤에도 오릅니다.

## Execute로 되돌리기

Verify FAIL, Review BLOCKER(작은 수정이 아닐 때), G3 `재작업`으로 ③ 구축에 돌아갈 때마다 합니다. 다음 판정이 `verify.md`·`review.md`를 덮어쓰므로 지금 판정을 먼저 남깁니다.

1. `verify.md`와 (있으면) `review.md`를 `archive/<date +%y%m%d-%H%M%S 값>-run<verify.md의 Run: 값>/`에 `cp -p`로 복사하고(절대 경로) `cmp`로 대조합니다. 다르면 멈추고 알립니다.
2. `plan.md`에서 실패한 기준(또는 G3에서 부족하다고 한 점)에 걸린 작업 단위의 `Status:`를 `pending`으로 바꿉니다. 문서 결과물을 합치는 마지막 writer 단위가 있으면 앞 단위가 하나라도 `pending`이 될 때 그 단위도 `pending`으로 바꿉니다. 나머지는 `done`으로 둡니다.
3. `.active`의 `phase:`를 `3`으로 바꾸고 `build.md`를 읽습니다. Execute 단계 줄에 이유와 보관 폴더를 붙입니다: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=5 name=Execute back="<Verify FAIL 기준 번호 / Review BLOCKER / G3 재작업>" archive=<보관 폴더> --model <메인 세션 모델 ID>` (`build.md` 5단계 1번 대신). 이렇게 돌아간 Execute에서는 `build.md` 5단계 2번(기준점, 커밋하지 않은 변경 팝업)을 하지 않고, coder는 worktree 없이 메인 트리에서 순서대로 돌립니다(이미 병합한 변경이 커밋되지 않아 worktree가 보지 못함).

## 8. Review → Deliver

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=8 name=Review-Deliver --model <메인 세션 모델 ID>`
2. `my-agent:reviewer`에게 맡깁니다. 넘기는 것: 결과물 경로, `plan.md` 경로, 결과 경로 `review.md`. 결과 첫 줄은 `BLOCKER <개수>`입니다.
3. BLOCKER가 1개 이상이면: 작은 수정(SKILL.md 레벨 표의 L1 예외)이면 L1이 고치고(`fix` 줄) 다시 판정을 받습니다. Verify 없이 Review만 다시 받았으면, 새 `review.md` 끝에 `## Applied after review` 절을 Edit로 더하고 고친 것을 `- <고친 것> (<파일>)`로 한 줄씩 적습니다(이 절이 없으면 hook이 `verify.md`가 변경보다 오래됐다고 G3 저장·커밋을 막습니다). 작은 수정이 아니면 "Execute로 되돌리기"를 합니다.
4. **G3 보고 (채팅):** 결과 요약, 실패·미처리 목록, diff 또는 결과물, 사용 토큰과 금액(참고), **저장할 정확한 경로**.
   - 저장 위치: `## 범위 요약`(또는 `scope.md`)의 결과물 위치. 없으면 작업 폴더의 `deliverable/`.
   - 파일 이름은 영어 소문자와 하이픈. 같은 이름이 있으면 덮어쓰지 않고 `-2`를 붙입니다. 기존 파일을 고치는 작업이면 diff를 보여 줍니다.
   - 경로가 `~/dev` 밖이면 `수용` 선택을 그 쓰기의 승인으로 삼는다고 팝업 질문에 적습니다.
5. **G3 팝업:**
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="최종 수용: <task-id> → <저장 경로>" rec="수용"`
   - 팝업: `수용 (Recommended)` / `재작업` / `중단`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<고른 선택지>"`
6. **수용:**
   - 최종본에 SKILL.md "바깥으로 나가기 전 점검"을 합니다.
   - 작업 폴더의 최종본을 저장 위치로 복사합니다. 작업자는 작업 폴더 밖에 쓰지 않으므로 이 복사는 L1이 합니다. 판정이 최신이 아니면 hook(`verdict-fresh-check.py`)이 막습니다. 막히면 Verify부터 다시 합니다.
   - `intake.md`에 `Delivered: <경로>`를 더하고 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=<경로>`.
   - `intake.md`를 `Status: done`으로 바꿉니다.
   - 회고: 아래 "회고"를 합니다. 회고가 끝난 뒤 마지막에 `.active`와 `active-index.json`의 이 작업 줄을 지웁니다(회고에 `.active`가 필요합니다).
   - 개발 프로파일은 이 6번 대신 아래 "개발 프로파일의 G3"를 따릅니다.
7. **재작업:** 기준이 그대로면 "Execute로 되돌리기"를 하고 부족한 점을 실패한 기준처럼 들고 ③ 구축으로 갑니다. 기준이 바뀌는 요청이면 SKILL.md "작업 중 수정"을 탑니다.
8. **중단:** SKILL.md "중단" 절차.

## 개발 프로파일의 G3 (커밋 승인)

결과물이 커밋이므로 4~6번 대신 이렇게 합니다.

1. **채팅에 붙입니다:** `git status --porcelain`, `git diff --stat`과 주요 diff, 새 파일 목록, 판정 요약(`verify.md` `Run:`, `review.md`의 SHOULD-FIX·NIT), 제안 커밋 메시지(첫 줄은 무엇을 바꿨는지, 본문에 완료 기준 번호 `criteria: 1, 2, 3`), 사용 토큰과 금액(참고).
2. 커밋할 파일은 이번 작업이 바꾼 파일만입니다(`base` 줄 이후의 변경, `docs/agent/` 제외. `docs/agent/.gitignore`가 `# my-agent: commit`이면 작업 폴더도 포함).
3. 팝업 전후로 기록합니다.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G3 q="커밋 승인: <task-id>" rec="커밋"`
   - 팝업: `커밋 (Recommended)` / `재작업` / `중단`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G3 choice="<고른 선택지>"`
4. **커밋:**
   - 커밋할 파일에 SKILL.md "바깥으로 나가기 전 점검"을 합니다.
   - `git add <파일들>` 뒤 `git commit -m "<메시지>"`. G2 권한 창이 한 번 더 뜨는 것은 일부러 두 번 확인하는 것입니다. 판정이 최신이 아니면 hook(`verdict-fresh-check.py`)이 막습니다. 막히면 Verify부터 다시 합니다. `--no-verify`는 쓰지 않습니다.
   - `intake.md`에 `Delivered: commit:<짧은 sha>`를 더하고 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" deliver path=commit:<짧은 sha>`.
   - `intake.md`를 `Status: done`으로 바꿉니다. 아래 "회고"를 하고, 마지막에 `.active`와 `active-index.json`의 이 작업 줄을 지웁니다.
5. **재작업**과 **중단**은 위 7, 8번과 같습니다. 중단하면 바뀐 파일은 되돌리지 않고 목록만 보고합니다.

## E 에스컬레이션

- 조건: Verify 3번 연속 FAIL, 같은 작업 단위가 두 번 중단(같은 `unit=`의 `stop:`이 `end=partial` 또는 `end=error`), workflow가 오류로 끝남, 병합 충돌이 계획 오류를 드러냄.
- 막힌 지점과 시도한 내용을 채팅에 보여 준 뒤 기록하고 팝업으로 묻습니다.
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=E q="<막힌 지점>" rec="<권장 선택지>"`
  - 팝업: `방향 제시` / `범위 수정` / `중단` (상황에 맞는 것을 맨 앞에 `(Recommended)`)
  - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=E choice="<고른 선택지>"`

## 회고

수용(또는 커밋) 뒤, `.active`를 지우기 전에 이 순서로 합니다. `Status: done`을 먼저 써 두므로 회고 중에 세션이 끊겨도 `continue`가 G3를 다시 하지 않습니다.

1. `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/gate-report.py" tally`를 실행합니다. 결정 표, 지표, 단계별 비용·토큰이 `gate-tally.md`에 써집니다. exit 1(진행 중인 작업 없음)이면 리포트를 건너뛰고 한 줄로 알린 뒤 5번으로 갑니다. exit 3(`gate-tally.md`를 쓰지 못함)이면 출력된 원인을 한 줄로 알리고 리포트를 건너뜁니다. 수용·커밋은 되돌리지 않고 5번으로 갑니다.
2. `my-agent:gate-analyst`에게 맡깁니다. 넘기는 것: `gate-tally.md`, 결과 경로 `gate-report.md`, 프롬프트에 적은 프로파일(`intake.md`의 `Profile:` 값. gate-analyst는 `intake.md`를 읽을 수 없습니다). 결과 첫 줄은 `DONE` 또는 `PARTIAL <이유>`입니다.
3. PARTIAL이거나 오류면 수용·커밋을 되돌리지 않고, 원인을 한 줄로 알리고, 복사를 건너뛰고 5번으로 갑니다.
4. SKILL.md "바깥으로 나가기 전 점검"을 `gate-report.md`에 하고 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/gate-report.py" copy`를 실행합니다(복사 폴더에 같은 이름이 있으면 `-2`가 붙습니다). 채팅에는 경로 두 개(작업 폴더의 `gate-report.md`, 복사본)와 `gate-report.md` `## 요약`의 3줄만 보여 줍니다. copy가 exit 1(리포트 없음) 또는 exit 3(복사본을 쓰지 못함)으로 끝나면 수용·커밋을 되돌리지 않고, 원인을 한 줄로 알린 뒤 5번으로 갑니다.
5. 리포트가 없거나(1번 exit 1·3) PARTIAL·오류였으면(3번) 뚜렷함 올리기는 건너뜁니다. 아니면 `gate-report.md` `## 개선 제안` 중 `뚜렷함` 표시가 있는 것을 `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" add L1 <task-id> "<개선점>"`로 올립니다(채팅에는 보이지 않습니다). 이번 작업에서 나온 다른 개선점도 `add L<1-4>`로 올립니다.
6. `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/feedback.py" count`. `REVIEW: L<n> …` 줄이 나오면(한 레벨에 열린 개선점 4개 이상) 사람에게 한 줄로 알립니다.
7. 누락 점검: 이 세션의 서브에이전트 transcript 목록(`~/.claude/projects/<프로젝트>/<세션>/subagents/`)과 run-log의 `start:` 줄 `id`를 대조합니다. 빠진 호출이 있으면 L4 개선점으로 올립니다.
8. run-log의 `stop:` 줄에 `mode=`가 auto가 아닌 것이 있으면 회고에 적습니다.

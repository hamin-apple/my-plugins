# ② 계획 (Plan): 3 Plan · 4 Plan Review → G1b

## 3. Plan

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=3 name=Plan --model <메인 세션 모델 ID>`
2. `my-agent:architect`에게 맡깁니다. 넘기는 것: `intake.md`, `explore.md`(, `scope.md`) 경로, 일반 프로파일이면 범위 요약, 결과 경로 `docs/agent/<task-id>/plan.md`.
3. `plan.md`에 있어야 하는 절 (없으면 architect에게 그 절만 다시 쓰게 합니다):
   - `## 범위 요약` (일반 프로파일): 목적, 비목표, 결과물 위치
   - `## 완료 기준`: `1.`, `2.` 번호 목록 (일반 프로파일. 다른 프로파일은 `scope.md`에 있음)
   - `## 작업 단위`: 단위마다 맡을 에이전트, 고칠 파일 목록, 병렬 그룹, `Status: pending`
   - `## 참고 파일`: writer가 읽어도 되는 작업 폴더 밖 파일 (scope-guard가 이 목록으로 writer의 읽기를 허용합니다)
   - `## Mock-up` (**필수**): 결과물 예시. 정상 경우와 범위에 적힌 예외 경우를 모두, 각 경우에 완료 기준 번호를 붙여서
   - `## Prototype`: 필요 / 불필요와 이유
   - `## Estimate`: 서브에이전트 수, workflow 단계와 에이전트 수, 예상 토큰(`<N>k tokens`)
   - `## Approval`: 비워 둠
4. 병렬 그룹 안의 작업 단위끼리 고칠 파일이 겹치면 순서대로 돌리게 고치게 합니다.

## 4. Plan Review

1. 기록: `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" step n=4 name=Plan-Review --model <메인 세션 모델 ID>`
2. 생략 여부는 프로파일 파일을 따릅니다. 생략하면 `plan-review.md`에 `Verdict: SKIPPED <이유>`를 씁니다.
3. `my-agent:plan-reviewer`에게 맡깁니다. 넘기는 것: `plan.md`, `intake.md`, `explore.md` 경로와 결과 경로 `plan-review.md`. architect의 설명은 넘기지 않습니다.
4. 결과 첫 줄이 `READY FOR APPROVAL`이면 G1b로 갑니다. `REVISE`이면 architect에게 `plan-review.md` 경로를 넘겨 다시 쓰게 하고 다시 판정합니다. 세 번째도 `REVISE`이면 그 판정을 G1b 팝업에 함께 보여 사람에게 맡깁니다.

## G1b 계획 승인

1. **채팅에 붙입니다:** `## Mock-up` 전문(요약 금지), 흐름도가 있으면 흐름도, 작업 단위 요약, `## Estimate`, 작업 ID. 일반 프로파일이면 `## 범위 요약`과 `## 완료 기준`도. 판정 때문에 바뀔 부분은 표시합니다.
2. `## Prototype`이 "필요"이면 팝업: `prototype 만들기 (Recommended)` / `mock-up으로 충분` / `계획 수정`.
   - 만들면 `plan.md`에 `Prototype: requested` 줄을 쓰고 `my-agent:writer`에게 `docs/agent/<task-id>/prototype/index.html`을 맡깁니다(`artifact-design` 기준).
   - L1이 그 파일을 읽어 확인하고 SKILL.md "바깥으로 나가기 전 점검"을 한 뒤 비공개 artifact로 게시하고, 링크와 로컬 경로를 보여 줍니다.
3. 승인 팝업 전후로 기록합니다.
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" ask gate=G1b q="계획 승인: <task-id>"`
   - 팝업: `승인 (Recommended)` / `수정 요청` / `중단`
   - `python3 "${CLAUDE_PLUGIN_ROOT}/l4-tools-guards/scripts/run-log.py" answer gate=G1b choice="<고른 선택지>"`
4. **승인:** `## Approval` 아래에 `- Approved <YYYY-MM-DD HH:MM> G1b`를 씁니다. 시각은 `date '+%Y-%m-%d %H:%M'`로 먼저 얻고, 그 값을 Edit 도구로 명령 치환 없이 적습니다(`$(…)`가 든 Bash 쓰기는 G1b hook이 어디에 쓰는지 알 수 없는 명령으로 막습니다). `.active`의 `phase:`를 `3`으로 바꾸고 `build.md`를 읽습니다.
5. **수정 요청:** 요청 내용을 architect에게 넘겨 다시 쓰게 하고 1번으로 돌아갑니다. 확정된 범위를 바꾸는 요청이면 SKILL.md "작업 중 수정"을 탑니다. prototype은 mock-up이 바뀐 경우에만 다시 만듭니다.
6. **중단:** SKILL.md "중단" 절차.

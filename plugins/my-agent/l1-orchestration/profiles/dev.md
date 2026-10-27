# 개발 프로파일 (dev)

git 저장소의 코드를 바꾸는 작업입니다(기능, 버그 수정, 리팩터링). 결과물은 G3에서 승인한 커밋 하나입니다. 사람에게 묻는 횟수는 정상 경로에서 G1a, G1b, G3, 3번이고, 작은 작업은 G1b, G3, 2번입니다(작업 위치, `.gitignore`처럼 처음 한 번만 묻는 질문과 G2 권한 창은 빼고 셉니다).

## phase별 규칙

| 단계 | 개발 프로파일 |
|---|---|
| 2 Explore → Scope | explorer에게 항상 맡깁니다: 관련 파일과 호출처, 지금 동작, 확인 명령(테스트·lint·빌드), 커밋하지 않은 변경. Scope 인터뷰로 `scope.md`에 일곱 가지를 정합니다: **목적·사용자**, **완료 기준**(`1.`, `2.` 번호), **강한 제약**(바꾸면 안 되는 것, 호환성, 성능), **예외 경우**(빈 입력, 오류, 경계값), **데이터**(입출력 형식, 저장), **비목표**, **UX 선호**(메시지, 화면, CLI 출력). `scope.md`에는 WHAT/WHY만 씁니다. 파일·함수 이름은 쓰지 않습니다. G1a로 확정합니다. |
| 작은 작업 예외 | `explore.md`로 보아 고칠 파일이 3개 미만이고, 요청이 목적·사용자, 완료 기준, 비목표에 이미 답하면: Scope 인터뷰와 G1a를 하지 않습니다. L1이 5줄 요약(목적, 완료 기준 번호 목록, 비목표, 제약, 예외 경우)을 architect에게 넘겨 `plan.md` 맨 위 `## 범위 요약`과 `## 완료 기준`으로 두게 합니다. Plan Review는 하지 않고 `plan-review.md`에 `SKIPPED 작은 작업`을 씁니다. 판단과 이유를 Intake 보고 다음 줄에 한 줄로 알립니다. |
| 3 Plan | 작업 단위(`### u<번호>`)는 코드 한 조각입니다(`my-agent:coder`). 단위마다 고칠 파일, 더할 테스트, 완료 기준 번호, 확인 명령. 서로 다른 파일을 고치는 단위만 같은 병렬 그룹에 둡니다. worktree는 첫 병렬 그룹에만 씁니다. mock-up은 바뀐 뒤의 동작 예시(명령 출력, 응답, 화면)입니다. |
| 4 Plan Review | 생략하지 않습니다(작은 작업 예외만). 판정이 `REVISE`(BLOCKER 있음)이면 묻지 않고 architect에게 되돌립니다(SKILL.md "작업 중 수정"의 승인 전 다시 쓰기를 거침). `READY FOR APPROVAL`인데 SHOULD-FIX나 NIT가 있으면 목록을 보여 주고 한 번 팝업: `모두 반영 (Recommended)` / `반영하지 않고 승인으로` / `직접 고르기`. 반영할 것은 승인 전 다시 쓰기를 거쳐 architect에게 넘기고, 결정은 L1이 `plan-review.md`의 `## Decisions`에 한 줄씩 남깁니다. |
| G1b | 계획 승인. `scope.md`(작은 작업이면 5줄 요약)도 함께 보여 줍니다. |
| 5 Execute | 시작할 때 기준점을 남깁니다(`base commit=<HEAD> dirty=<요약>`). 메인 트리에 커밋하지 않은 변경이 있으면 팝업: `사용자가 먼저 정리 (Recommended)` / `그대로 두고 진행` / `중단`. `그대로 두고 진행`이면 worktree를 쓰지 않고 모든 작업 단위를 메인 트리에서 순서대로 돌립니다. 아니면 첫 병렬 그룹의 coder만 호출 인자 `isolation: "worktree"`로 부르고, 그 뒤 그룹은 메인 트리에서 순서대로 부릅니다. |
| 6 Merge | ("Execute로 되돌리기"로 다시 돈 Execute는 worktree를 쓰지 않으므로 옮길 것이 없습니다.) worktree 결과를 계획의 작업 단위 순서대로 메인 트리에 옮깁니다. coder는 커밋하지 않으므로 worktree의 변경은 커밋하지 않은 diff와 새 파일입니다: `git -C <worktree> diff --binary HEAD \| git apply`로 diff를, `git -C <worktree> ls-files --others --exclude-standard`의 새 파일은 복사로 옮긴 뒤 `git worktree remove <worktree>`. 충돌 처리는 `build.md` 6번. 다 옮긴 뒤 `explore.md`의 확인 명령(테스트, lint)을 돌립니다. 실패하면 실패한 테스트와 함께 해당 단위의 coder에게 메인 트리에서 다시 맡깁니다. |
| 7 Verify | verifier가 `git diff`, `git status --porcelain`, 새 파일, 확인 명령 결과로 기준마다 판정합니다. `verify.md` 둘째 줄 `Run:`이 회차입니다. 3번 연속 FAIL이면 E. |
| 8 Review → G3 | reviewer가 코드 리뷰와 완료 정의를 봅니다(`review.md`). G3는 커밋 승인입니다(`accept.md` "개발 프로파일의 G3"): diff와 제안 메시지를 보여 주고 팝업 `커밋 (Recommended)` / `재작업` / `중단`. 커밋 메시지는 완료 기준 번호를 적습니다. |

## 맡기는 에이전트

이름은 호출할 때 쓰는 이름입니다.

| 에이전트 | 쓰는 단계 | 결과 |
|---|---|---|
| `my-agent:explorer` | 2 | 보고 → L1이 `explore.md`에 저장 |
| `my-agent:architect` | 3, G1b 수정 | `plan.md` |
| `my-agent:plan-reviewer` | 4 | `plan-review.md` |
| `my-agent:coder` | 5, 6 (테스트 실패, 큰 충돌) | 코드와 테스트 (커밋하지 않음) |
| `my-agent:writer` | prototype | `prototype/index.html` |
| `my-agent:verifier` | 7 | `verify.md` |
| `my-agent:reviewer` | 8 | `review.md` |

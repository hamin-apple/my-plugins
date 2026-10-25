# 일반 프로파일 (general)

조사·문서나 개발 프로파일에 해당하지 않는 여러 단계 작업입니다. 사람에게 묻는 횟수는 정상 경로에서 G1b와 G3, 2번입니다(작업 위치, `.gitignore`처럼 처음 한 번만 묻는 질문은 빼고 셉니다).

## phase별 규칙

| 단계 | 일반 프로파일 |
|---|---|
| 2 Explore → Scope | 묻는 것: 목적, 완료 기준, 비목표, 결과물 위치. 요청에 다 있으면 인터뷰를 생략합니다. G1a는 따로 묻지 않습니다. 결과물 위치는 범위 요약에 ``- 결과물 위치: `<경로>` `` 한 줄로 적습니다. 승인 뒤 hook이 이 경로 밖의 작업 위치 밖 쓰기를 묻습니다. |
| 3 Plan | 범위 요약과 `## 완료 기준`을 `plan.md` 맨 위에 둡니다. mock-up은 결과물 예시입니다(예: 표의 첫 몇 줄, 문서의 목차와 샘플 단락). |
| 4 Plan Review | 작업 단위의 고칠 파일이 모두 합쳐 3개 미만이면 생략할 수 있습니다. 생략하면 이유를 `plan-review.md`에 남깁니다. |
| G1b | 범위 요약과 계획을 한 번에 승인받습니다. 첫 게이트이므로 작업 ID를 함께 보여 줍니다. |
| 5 Execute | 서브에이전트로 합니다. workflow는 쓰지 않습니다. |
| 6 Merge | 결과를 모아 결과물 하나로 합칩니다. 기본 점검: 작업 단위마다 결과 파일이 있는지, 완료 기준마다 대응하는 부분이 있는지. |
| 7 Verify | 기준별 PASS/FAIL. 생략하지 않습니다. |
| 8 Review → Deliver | 결과 요약과 품질 판정. 생략하지 않습니다. 저장 위치는 범위 요약의 결과물 위치, 없으면 `deliverable/`. Obsidian vault에는 저장하지 않습니다. |

## 맡기는 에이전트

이름은 호출할 때 쓰는 이름입니다. 정의 파일은 플러그인의 `l2-design-judge/agents/`, `l3-workers/agents/`에 있습니다.

| 에이전트 | 쓰는 단계 | 결과 |
|---|---|---|
| `my-agent:explorer` | 2 | `explore.md` |
| `my-agent:architect` | 3, G1b 수정 | `plan.md` |
| `my-agent:plan-reviewer` | 4 | `plan-review.md` |
| `my-agent:researcher` | 5 (조사가 필요한 단위, G1b 뒤에만) | `work/` 노트: 주장 · 출처 URL · 인용 |
| `my-agent:writer` | 5, prototype | `work/` 초안, `prototype/index.html` |
| `my-agent:coder` | 5 (코드가 필요한 단위) | 코드 |
| `my-agent:verifier` | 7 | `verify.md` |
| `my-agent:reviewer` | 8 | `review.md` |

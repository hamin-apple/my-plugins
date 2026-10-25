# 조사·문서 프로파일 (research)

주제를 웹에서 조사해 출처를 붙인 노트나 보고서를 만드는 작업입니다. 사람에게 묻는 횟수는 정상 경로에서 G1a, G1b, G3, 3번입니다(작업 위치, `.gitignore`처럼 처음 한 번만 묻는 질문은 빼고 셉니다).

## phase별 규칙

| 단계 | 조사·문서 프로파일 |
|---|---|
| 2 Explore → Scope | Explore는 기존 노트나 파일을 고치거나 이어 쓰는 작업일 때만 맡깁니다. Scope 인터뷰로 `scope.md`에 네 가지를 정합니다: **질문**(알고 싶은 것과 이유), **범위**(다룰 것, 비목표, 기간·지역), **출처 기준**(공식 문서·1차 자료 우선, 날짜 범위, 쓰지 않을 출처), **결과물 형식**(노트 / 보고서, 목차 수준, 길이, 저장 경로. 경로는 ``- 저장 경로: `<경로>` `` 한 줄로 적습니다. 승인 뒤 hook이 이 경로 밖의 작업 위치 밖 쓰기를 묻습니다). 그 아래 `## 완료 기준` 번호 목록과 `## Confirmation`. 요청에 이미 답이 있는 항목은 묻지 않습니다. G1a로 확정합니다. |
| 3 Plan | architect가 하위 질문 → 조사 단위(하위 질문 하나에 `my-agent:researcher` 하나, 결과 `work/<slug>.md`) → 종합 구조 순서로 씁니다. 마지막 단위는 `my-agent:writer`가 노트를 종합 구조에 배치하는 단위(결과 `work/final.md`)입니다. mock-up은 최종 노트의 목차와 샘플 단락 1개입니다. |
| 4 Plan Review | 생략하지 않습니다. 공통 점검에 더해 범위 누락(하위 질문이 질문을 모두 덮는지)과 출처 편향을 봅니다. |
| G1b | 계획 승인. `scope.md` 요약은 G1a에서 확정했으므로 다시 묻지 않고 함께 보여 줍니다. |
| 5 Execute | 웹 조사는 G1b 승인 뒤에만 시작합니다. 조사 단위가 4개 이하면 researcher를 한 메시지에서 함께 부릅니다. 5개 이상이면 `build.md`의 workflow 규칙대로 `agentType: 'my-agent:researcher'`로 workflow를 씁니다(계획의 `## Estimate`에 있을 때만). |
| 6 Merge | writer가 노트를 종합 구조에 배치합니다. 기본 점검(L1): 하위 질문마다 노트가 있는지, 노트의 모든 항목이 `- <주장> · <출처 URL> · "<인용>"` 또는 `- 찾지 못함: …` 형식인지. 형식이 깨진 노트는 그 researcher에게 다시 맡깁니다. |
| 7 Verify | 기준별 PASS/FAIL과 주장 · 출처 URL · 인용 대조(verifier가 출처를 열어 인용을 확인). 형식에 맞지 않는 문장, 지시문 같은 내용이 섞이면 FAIL입니다. |
| 8 Review → Deliver | 문서 품질 판정. 저장 위치는 `scope.md` 결과물 형식의 경로, 정하지 않았으면 작업 폴더의 `deliverable/`. 파일 이름은 영어 소문자와 하이픈, 같은 이름이 있으면 `-2`를 붙입니다. Obsidian vault에는 저장하지 않습니다. |

## 맡기는 에이전트

이름은 호출할 때 쓰는 이름입니다.

| 에이전트 | 쓰는 단계 | 결과 |
|---|---|---|
| `my-agent:explorer` | 2 (기존 노트를 고칠 때만) | 보고 → L1이 `explore.md`에 저장 |
| `my-agent:architect` | 3, G1b 수정 | `plan.md` |
| `my-agent:plan-reviewer` | 4 | `plan-review.md` |
| `my-agent:researcher` | 5 (G1b 뒤에만) | `work/<slug>.md` 노트: 주장 · 출처 URL · 인용 |
| `my-agent:writer` | 6, prototype | `work/final.md`, `prototype/index.html` |
| `my-agent:verifier` | 7 | `verify.md` |
| `my-agent:reviewer` | 8 | `review.md` |

# 개발 프로파일 검증 (설계 §6 "개발 프로파일 검증")

- 날짜: 2026-10-25
- 위치: `~/dev/my-agent-sandbox` (main)
- 실행: tmux 대화형 세션 `PYTHONDONTWRITEBYTECODE=1 claude --plugin-dir ~/dev/my-agent --permission-mode auto`
- 세션 모델: Sonnet 5.5. 스킬 `model: opus`는 호출한 턴에만 적용됨(F13)
- 팝업 답: 시나리오 파일대로 Claude가 대신 했습니다. 커밋 3건은 사용자가 팝업으로 승인했습니다.

## 결과

| # | 작업 (task ID) | 종류 | 물은 횟수 (팝업 / G2 권한 창) | Plan Review | Verify | Review | 걸린 시간 | 비용(세션, 참고) | 커밋 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `261025-wc-lines-option` (`wc.py --lines`) | 작은 작업 (파일 2개, G1a 없음) | 2 / 2 | `SKIPPED 작은 작업` | ALL PASS, Run 1 | BLOCKER 0, NIT 3 | 5분 34초 | $2.20 | `a491e13` |
| 2 | `261025-upper-rev-tools` (`upper.py`, `rev.py`) | 병렬 slice (group 1에 coder 2개, worktree) | 5 / 0 | READY FOR APPROVAL, NIT 2 (반영) | ALL PASS, Run 1 | BLOCKER 0, SHOULD-FIX 1, NIT 1 | 30분 13초 (G3 대기 17분 포함) | $3.80 | `bd3e467` |
| 3 | `261025-textstats-module` (wc 함수를 `textstats.py`로, 테스트, README) | 여러 파일, 차례로 (slice 2개) | 4 / 1 | READY FOR APPROVAL, NIT 3 (반영 안 함) | ALL PASS, Run 1 | BLOCKER 0, SHOULD-FIX 1, NIT 3 | 9분 33초 | $3.23 | `9794c7c` |

- `check-run.py` 결과: 3건 모두 exit 0.
- 작업 1의 G2 2번 중 1번은 `AskUserQuestion`을 G2로 잘못 기록한 것입니다. 나중에 고쳤습니다(`permission-log`). 실제 권한 창은 1번이었습니다.
- 작업 2의 G2 0번은 문제 4 때문입니다.
- `stop:` 줄: 모두 `end=ok`.
- 작업 2의 G3 대기 17분: Claude가 추가 커밋 승인을 사용자에게 물은 시간입니다.
- 팝업 수 기준: dev 정상 경로는 2~3번입니다.
  - 작업 2는 G1b 수정 요청 1번, NIT 질문 1번 때문에 더 많습니다.
  - 작업 3은 NIT 질문 1번 때문에 더 많습니다.
- 작업 2의 병렬 실행: coder 둘이 15초 안팎으로 함께 끝났습니다. 그다음 Merge, Verify 순서로 진행했고, worktree와 임시 브랜치는 정리됐습니다.

## 발견된 문제와 처리

| # | 문제 | 처리 |
|---|---|---|
| 1 | 판정 최신성 hook이 Execute 중에 막았습니다. 명령은 `echo "HEAD=$(git rev-parse HEAD)"`였고, 메시지는 "verify.md 첫 줄이…"였습니다. 해석할 수 없는 git 명령을 커밋일 수 있다고 보고 막은 것은 맞습니다. 그러나 이유가 틀리게 나왔습니다. | 이유와 "치환 없이 나눠 실행"을 알리도록 메시지를 고쳤습니다. SKILL.md에 규칙을 더했습니다(테스트 먼저). |
| 2 | `SendMessage`로 이어 부른 architect의 두 번째·세 번째 실행에 `stop:` 줄이 없었습니다(같은 id라서 중복으로 버림). | `start:` 수만큼 `stop:`을 씁니다. 이어 부른 실행은 마지막 `start:` 시각부터 세고, sweep은 첫 실행만 닫습니다. 실행마다 Start/Stop이 다시 오는 것은 임시 기록 hook으로 확인했습니다(F33, 테스트 먼저). |
| 3 | 메인 모델 MISMATCH가 한 번도 뜨지 않았습니다. L1이 Sonnet 세션에서 `--model claude-opus-5-5`로 자기 모델을 잘못 적었습니다. | `run-log.py`가 transcript에서 모델을 읽습니다. 작업 3에서 실제로 MISMATCH가 떴습니다. 모든 줄에 붙던 것은 `step:` 줄로 줄였습니다. |
| 4 | 작업 2의 커밋은 `git -C <repo> commit`이었습니다. 이 형태는 `Bash(git commit:*)`에 걸리지 않아 G2 권한 창 없이 지나갔습니다. | ask에 `Bash(git * commit*)`, `Bash(git * push*)`를 더했습니다. deny에는 `git * push … --force/-f`를 더했습니다. 대화형으로 둘 다 확인했습니다. |
| 5 | L1(Sonnet)이 dev 프로파일에 정해진 NIT 팝업의 순서를 바꾸고 `(Recommended)`를 뺐습니다. | SKILL.md 질문 규칙에 "정해진 선택지는 그대로"를 더했습니다(테스트 먼저). |
| 6 | 작업 2: architect가 추적 중인 pyc 변경을 이유로 처음에 병렬을 차례 실행으로 바꿨습니다. | 샌드박스 환경 문제입니다. pyc를 정리했다고 G1b에서 알리자 계획이 병렬 worktree로 바뀌었습니다. 플러그인은 고치지 않았습니다. |

## 판단

3건 모두 Verify와 Review(BLOCKER 0)를 통과했습니다. 발견한 문제 1~5는 고쳤고 테스트를 더했습니다(전체 174개 통과). 차단 수준의 문제는 남지 않았습니다. 그래서 개발 프로파일을 검증된 것으로 봅니다(설계 §6).

**단서: L1은 세 번 모두 Sonnet(세션 모델)으로 돌았습니다.** 스킬의 `model: opus`는 호출한 첫 턴에만 적용됐습니다(F13). 그래서 이번 검증은 "L1 = opus" 설계를 실행해 본 것이 아닙니다. L1을 opus로 두려면 세션을 opus로 열어야 합니다. 그렇지 않으면 이제 `step:`마다 MISMATCH가 뜹니다. 설치(9단계)는 사용자 승인 뒤에 합니다.

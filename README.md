# my-plugins

jahoonjin의 Claude Code 플러그인 마켓플레이스입니다.

| 플러그인 | 버전 | 설명 |
|---|---|---|
| `my-agent` | 0.1.3 | 사람의 승인(HITL)을 끼운 멀티 에이전트 작업 스킬: 계획 → 실행 → 검증 → 리뷰 |

## 설치

```bash
claude plugin marketplace add hamin-apple/my-plugins
claude plugin install my-agent@my-plugins
```

비공개 저장소이므로 저장소에 초대된 GitHub 계정으로 로그인되어 있어야 합니다.

## my-agent

메인 세션(L1)이 요청을 받아 계획 → 실행 → 검증 → 리뷰를 차례로 돌리고, 정해진 지점마다 팝업으로 사람에게 묻습니다.

| 레벨 | 구성 |
|---|---|
| L1 | 메인 세션 (`/my-agent` 스킬): 단계 진행, 위임, 질문, 기록 |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: 계획, 판정, 결정 해석 |
| L3 | `explorer` · `researcher` · `writer` · `coder`: 맡은 작업 하나 |
| L4 | hook · 권한 규칙 · 스크립트: 기록과 차단 |

| 명령 | 하는 일 |
|---|---|
| `/my-agent <요청>` | 새 작업을 시작합니다. |
| `/my-agent continue` | 진행 중인 작업을 이어 갑니다. |
| `/my-agent status` | 진행 중인 작업과 최근 작업을 보여 줍니다. |
| `/my-agent:monitor` | 작업 기록을 보는 로컬 웹 페이지(읽기 전용)를 띄웁니다. `status`, `stop` |

작업 기록은 작업 위치의 `docs/agent/<작업 ID>/`에 남습니다.

## 업데이트와 제거

```bash
claude plugin marketplace update my-plugins
claude plugin update my-agent@my-plugins
claude plugin uninstall my-agent@my-plugins
```

## 저장소 구조

- `CLAUDE.md`: 개발용 안내(폴더 역할, 테스트 명령, 버전 규칙)
- `.claude-plugin/marketplace.json`: 플러그인 목록
- `plugins/<이름>/`: 플러그인. 설치하면 이 폴더만 복사됩니다.
- `docs/agent/`: 이 저장소에서 돌린 my-agent 작업 기록. git에서 제외됩니다.

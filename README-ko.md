# my-plugins

[English](README.md) | **한국어**

jahoonjin의 Claude Code 플러그인 마켓플레이스입니다.

| 플러그인 | 버전 | 설명 |
|---|---|---|
| `my-agent` | 0.3.1 | 사람의 승인(HITL)을 끼운 멀티 에이전트 작업 스킬: 계획 → 실행 → 검증 → 리뷰 |

## 요구 사항

- 플러그인을 지원하는 Claude Code. Claude Code 2.1.311로 테스트했고, 최소 버전은 확인하지 않았습니다.
- Python 3.9 이상, `PATH`에서 `python3`로 실행 가능(표준 라이브러리만 씀). Python 3.13.7로 테스트했습니다. hook, 스크립트, 모니터 서버가 이것으로 돕니다.
- git: `dev` 프로파일(기준 커밋, worktree, 커밋)에 필요. git 2.50.1로 테스트했습니다.
- macOS: 모니터의 브라우저 창 열기와 메뉴바 앱에 필요. macOS 27.0.1에서 테스트했습니다. Linux와 Windows는 시험하지 않았습니다: hook이 `python3`를 부르고, 모니터는 macOS 명령(`open`, `osascript`)으로 창을 엽니다.
- 선택, 메뉴바 앱에만: macOS 12 이상의 Command Line Tools(`swiftc`). Xcode는 필요 없습니다. Swift 6.3.3으로 테스트했고, 더 낮은 Swift 버전은 시험하지 않았습니다.

그 밖에 설치하는 것은 없습니다.

## 설치

```bash
claude plugin marketplace add hamin-apple/my-plugins
claude plugin install my-agent@my-plugins
```

비공개 저장소이므로 저장소에 초대된 GitHub 계정으로 로그인되어 있어야 합니다.

플러그인은 권한 규칙을 실을 수 없습니다. 위험한 행동 확인(G2: `git commit`, `git push`, `rm -rf`, 패키지 설치)과 막는 명령(비밀값 파일, `--no-verify`, `git push --force`)을 쓰려면 `plugins/my-agent/l4-tools-guards/permissions/permissions.json`의 `ask`·`deny` 목록을 `~/.claude/settings.json`의 `permissions`에 직접 병합합니다. 병합하지 않으면 이 행동들을 묻거나 막지 않습니다.

## my-agent

메인 세션(L1)이 요청을 받아 계획 → 실행 → 검증 → 리뷰를 차례로 돌리고, 정해진 지점마다 팝업으로 사람에게 묻습니다.

| 레벨 | 구성 |
|---|---|
| L1 | 메인 세션 (`/my-agent` 스킬): 단계 진행, 위임, 질문, 기록 |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: 계획, 판정, 결정 해석 |
| L3 | `explorer` · `researcher` · `writer` · `coder`: 맡은 작업 하나 |
| L4 | 도구·MCP · hook · 권한 규칙 · 스크립트: 실행, 기록과 차단 |

| 명령 | 하는 일 |
|---|---|
| `/my-agent <요청>` | 새 작업을 시작합니다. |
| `/my-agent continue` | 진행 중인 작업을 이어 갑니다. |
| `/my-agent status` | 진행 중인 작업과 최근 작업을 보여 줍니다. |
| `/my-agent:monitor` | 작업 기록을 보는 로컬 웹 페이지(읽기 전용)를 띄웁니다. `status`, `stop` |

작업 기록은 작업 위치의 `docs/agent/<작업 ID>/`에 남습니다.
끝난 작업은 그곳과 모니터 목록에 계속 쌓입니다. 끝난 지 30일 이상 된 작업을 `docs/agent/.archived/`로 옮겨 목록에서 빼려면 다음을 실행합니다(되돌리려면 폴더를 다시 옮깁니다):

```bash
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py --dry-run   # 목록만
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py [--days N]
```

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
- `docs/handoff/`: 다른 환경에서 이어 할 작업의 handoff 문서
- `docs/agent/`: 이 저장소에서 돌린 my-agent 작업 기록. git에서 제외됩니다.

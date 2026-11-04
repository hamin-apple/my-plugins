# my-plugins

[English](README.md) | **한국어**

hamin-apple의 Claude Code 플러그인 마켓플레이스입니다.

| 플러그인 | 버전 | 설명 |
|---|---|---|
| `my-agent` | 0.11.0 | 사람의 승인(HITL)을 끼운 멀티 에이전트 작업 스킬: 계획 → 실행 → 검증 → 리뷰 |
| `my-agent-tray` | 0.1.3 | my-agent 모니터용 macOS 메뉴바 앱 (선택; my-agent 0.5.0 이상 필요) |

## 요구 사항

- 플러그인을 지원하는 Claude Code. Claude Code 2.1.311로 테스트했고, 최소 버전은 확인하지 않았습니다.
- Python 3.9 이상, `PATH`에서 `python3`로 실행 가능(표준 라이브러리만 씀). Python 3.13.7로 테스트했습니다. hook, 스크립트, 모니터 서버가 이것으로 돕니다.
- git: `dev` 프로파일(기준 커밋, worktree, 커밋)에 필요. git 2.50.1로 테스트했습니다.
- macOS: 모니터의 창 열기에 필요. macOS 27.0.1에서 테스트했습니다. 다른 플랫폼에서는 모니터가 표준 브라우저 열기 도구로 탭을 열지만 시험하지 않았습니다. Linux와 Windows는 시험하지 않았습니다: hook이 `python3`를 부릅니다.
- 선택, 메뉴바 앱(`my-agent-tray` 플러그인)에만: macOS 12 이상의 Command Line Tools(`swiftc`). Xcode는 필요 없습니다. Swift 6.3.3으로 테스트했고, 더 낮은 Swift 버전은 시험하지 않았습니다.
- 선택, Codex에서 my-agent를 쓰려면: 플러그인을 지원하는 Codex CLI. codex-cli 0.166.0으로 테스트했고, 다른 버전은 시험하지 않았습니다.

그 밖에 설치하는 것은 없습니다.

## 설치

```bash
claude plugin marketplace add hamin-apple/my-plugins
claude plugin install my-agent@my-plugins
claude plugin install my-agent-tray@my-plugins   # 선택: macOS 메뉴바 앱
```

비공개 저장소이므로 저장소에 초대된 GitHub 계정으로 로그인되어 있어야 합니다.

플러그인은 권한 규칙을 실을 수 없습니다. 위험한 행동 확인(G2: `git commit`, `git push`, `rm -rf`, 패키지 설치)과 막는 명령(비밀값 파일, `--no-verify`, `git push --force`)을 쓰려면 `plugins/my-agent/l4-tools-guards/permissions/permissions.json`의 `ask`·`deny` 목록을 `~/.claude/settings.json`의 `permissions`에 직접 병합합니다. 병합하지 않으면 이 행동들을 묻거나 막지 않습니다.

플러그인을 켤 때 Claude Code가 설정 두 가지를 묻습니다. 첫째는 데이터 폴더입니다(기본값 `~/dev/log/my-agent`, 나중에 `/config`에서 바꿀 수 있습니다). my-agent가 작업 폴더 밖에 두는 모든 것이 여기에 들어갑니다: 프로젝트 목록(`projects.txt`), 실행 색인(`active-index.json`), 모니터 상태·로그·설정, 가격 재정의, 개선 목록(`feedback.md`), 회고 보고서 사본(`gate-report/`). 앞의 `~`는 홈 폴더로 펼쳐집니다. 플러그인 자기 폴더에는 아무것도 쓰지 않습니다. 폴더를 바꾸면 이전 폴더는 그대로 두고 그때부터 새 폴더를 씁니다. 설정이 없으면(예: `--plugin-dir`로 불러온 경우) `~/dev/log/my-agent`를 씁니다. 환경변수 `MA_TASKS_DIR`(데이터 폴더), `MA_PROJECTS_FILE`, `MA_FEEDBACK_FILE`, `MA_GATE_REPORT_DIR`이 설정보다 먼저 적용됩니다. 이전 버전의 폴더(`~/my-agent`)는 옮겨 주지 않습니다. 새 위치로 직접 옮기거나, 데이터 폴더를 옛 경로로 지정하세요. 둘째 설정 `task_dir`은 작업 위치 안의 작업 폴더입니다(기본값 `.my-agent`, 나중에 `/config`에서 바꿀 수 있습니다). 이전 버전은 작업 기록을 `docs/agent`에 두었습니다. 이 기록은 옮기거나 읽어 주지 않으므로, `task_dir`을 `docs/agent`로 지정하거나 폴더를 직접 옮기세요(`mv docs/agent .my-agent`). `..`가 없는 상대 경로여야 하며, 아니면 기본값을 씁니다. 환경변수 `MA_TASK_DIR`이 설정보다 먼저 적용됩니다.

데이터 폴더에는 선택적으로 `agent-models.json`을 둘 수 있습니다. 프로필별로 이름 붙인 모델 프리셋(에이전트마다 모델과 effort)을 정의하는 파일이며, `plugins/my-agent/docs/agent-models.example.json`을 복사해서 시작하세요. 프로필에 프리셋이 둘 이상이면 작업을 시작할 때 어느 것을 쓸지 묻습니다. 프리셋은 역할을 `"model": "inline"`으로 표시할 수도 있습니다(함께 제공되는 `inline` 프리셋은 아홉 역할 모두를 그렇게 표시합니다). 그러면 에이전트를 시작하지 않고 메인 세션이 그 역할을 직접 실행하며, 두 호스트 모두에서 같습니다. 파일이 없으면 아무것도 바뀌지 않습니다. 모든 에이전트가 정의 파일의 모델과 effort로 실행됩니다.

## Codex에서 쓰기

my-agent는 Codex에서도 돕니다. 마켓플레이스 원본으로는 이 저장소의 로컬 클론만 시험했습니다:

```bash
git clone https://github.com/hamin-apple/my-plugins ~/dev/my-plugins
codex plugin marketplace add ~/dev/my-plugins
codex plugin add my-agent@my-plugins
```

- Codex는 플러그인의 hook을 신뢰하기 전에는 실행하지 않습니다. Codex를 한 번 열고 `Hooks need review` 화면에서 my-agent hook을 신뢰하세요(`t`는 모두 신뢰). 그 전에는 Intake가 실행되지 않은 hook의 이름을 알려 줍니다.
- Codex는 메인 스킬을 `my-agent:my-agent`로 `my-agent:monitor`와 함께 `skills/my-agent/SKILL.md`에서 목록에 올립니다. 세션을 시작할 때 my-agent hook이 Codex에 플러그인, 데이터, 작업 폴더를 알려 주는 한 줄을 줍니다.
- Codex는 에이전트 정의를 플러그인이 아니라 `~/.codex/agents/`에서 불러옵니다. Intake가 my-agent 역할 아홉 개를 `my-agent-<role>`로 그곳에 설치하므로 Codex가 서브에이전트를 my-agent 역할로 실행합니다. 설치되기 전에는 Codex가 그 이름을 거부하고, 서브에이전트 시작·종료 기록과 역할 기반 점검이 적용되지 않습니다.
- 작업을 시작할 때 Intake가 `~/.codex/agents/`의 my-agent 에이전트 아홉 개를 점검하고, 없거나 오래되었으면 설치하기 전에 물어봅니다(`build-codex.py --install-agents`). my-agent 버전 주석이 없는 파일은 덮어쓰지 않습니다. 새 에이전트는 새 Codex 세션에서 보입니다.
- `/my-agent:monitor`는 Codex에서 스킬 `my-agent:monitor`이며, Codex가 목록에 올립니다.
- Codex에서 다른 점: coder worktree 없음, 백그라운드 시작 없음, 플러그인 설정이 전달되지 않음. Codex에는 자체 G2 권한 대화상자가 없습니다. 위험한 작업은 호출을 멈추고, my-agent가 자기 팝업으로 묻고, `Allow once` 뒤에 그 호출 하나만 통과시킵니다. 모델 프리셋은 `agent-models.json`의 `codex` 섹션으로 Codex에서도 적용되고, 에이전트의 `tools`와 `maxTurns`는 쓸 수 없습니다. `plugins/my-agent/l1-orchestration/hosts.md`가 이름을 하나씩 대응시키고, `plugins/my-agent/docs/build-guide/my-agent-architecture.md`의 4.14절에 제한이 정리되어 있습니다.

## my-agent

메인 세션(L1)이 요청을 받아 계획 → 실행 → 검증 → 리뷰를 차례로 돌리고, 정해진 지점마다 팝업으로 사람에게 묻습니다.

| 레벨 | 구성 |
|---|---|
| L1 | 메인 세션 (`/my-agent` 스킬): 단계 진행, 위임, 질문, 기록 |
| L2 | `architect` · `plan-reviewer` · `verifier` · `reviewer` · `gate-analyst`: 계획, 판정, 결정 해석 |
| L3 | `explorer` · `researcher` · `writer` · `coder`: 맡은 작업 하나 |
| L4 | 도구·MCP · hook · 권한 규칙 · 스크립트: 실행, 기록과 차단 |

레벨별 구성 요소, 각 구성의 역할과 권한, 단계와 게이트, 작업 파일마다의 형식까지 전체 구조는 한 페이지 `docs/architecture.html`에 있고, <https://hamin-apple.github.io/my-plugins/architecture.html> 에서 볼 수 있습니다. 사이트 첫 화면 <https://hamin-apple.github.io/my-plugins/> 은 기능 소개 페이지입니다. `python3 tools/build-docs.py`가 플러그인 파일에서 아키텍처 페이지를 만들며, 플러그인 파일을 고친 뒤 다시 실행합니다.

| 명령 | 하는 일 |
|---|---|
| `/my-agent <요청>` | 새 작업을 시작합니다. |
| `/my-agent --auto <요청>` | 새 작업을 시작하고 일상적인 팝업은 메인 세션이 대신 답합니다. 최종 인수(G3)와 에스컬레이션은 계속 사람에게 옵니다. 프로필 플래그와 함께 쓸 수 있습니다. |
| `/my-agent --dev <요청>` | 지정한 프로필로 새 작업을 시작합니다: `--general`, `--research`, `--dev`. 플래그가 없으면 요청을 보고 프로필을 고릅니다. |
| `/my-agent continue` | 진행 중인 작업을 이어 갑니다. |
| `/my-agent status` | 진행 중인 작업과 최근 작업을 보여 줍니다. |
| `/my-agent:monitor` | 작업 기록을 보는 로컬 웹 페이지(읽기 전용)를 띄웁니다. 선택한 작업의 범위·계획·결과를 한 페이지로 요약하는 Report 탭이 있습니다. `status`, `stop` |

작업 기록은 작업 위치의 `<task location>/<task_dir>/<작업 ID>/`에 남습니다(기본값은 `.my-agent/<작업 ID>/`, `docs/agent`는 이전 구조).
끝난 작업은 그곳과 모니터 목록에 계속 쌓입니다. 끝난 지 30일 이상 된 작업을 `<task_dir>/.archived/`로 옮겨 목록에서 빼려면 다음을 실행합니다(되돌리려면 폴더를 다시 옮깁니다):

```bash
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py --dry-run [--data-dir <폴더>] [--task-dir <폴더>]   # 목록만
python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/archive-tasks.py [--days N] [--data-dir <폴더>] [--task-dir <폴더>]
```

셸에서 직접 실행하면 스크립트는 설정을 알지 못합니다. 데이터 폴더가 기본값 `~/dev/log/my-agent`가 아니면 `--data-dir <폴더>`로 알려 주어야 프로젝트 목록을 찾습니다. `task_dir`을 바꿨다면 `--task-dir <폴더>`도 같이 알려 주세요.

## 업데이트와 제거

```bash
claude plugin marketplace update my-plugins
claude plugin update my-agent@my-plugins
claude plugin uninstall my-agent@my-plugins
claude plugin update my-agent-tray@my-plugins      # 설치했다면
claude plugin uninstall my-agent-tray@my-plugins   # 설치했다면
```

## 저장소 구조

- `CLAUDE.md`: 개발용 안내(폴더 역할, 테스트 명령, 버전 규칙)
- `.claude-plugin/marketplace.json`: 플러그인 목록
- `.agents/plugins/marketplace.json`: Codex용 플러그인 목록
- `plugins/<이름>/`: 플러그인. 설치하면 이 폴더만 복사됩니다.
- `tools/build-docs.py`, `tools/docs-template.html`: my-agent 아키텍처 페이지를 만듭니다
- `docs/architecture.html`: 아키텍처 페이지(생성물, GitHub Pages 소스 `main` · `/docs`)
- `docs/index.html`: my-agent 기능 소개 영어판(사이트 첫 화면, 직접 관리)
- `docs/index-ko.html`: my-agent 기능 소개 한국어판(직접 관리)
- `tests/`: `tools/` 테스트
- `docs/handoff/`: 다른 환경에서 이어 할 작업의 handoff 문서
- `.my-agent/`: 이 저장소에서 돌린 my-agent 작업 기록. git에서 제외됩니다.
- `plugins/my-agent/docs/reference.md`: 참고 문서의 출처 목록. 로컬 사본(`plugins/my-agent/docs/ref/`)은 git에서 제외됩니다.

## 라이선스

[MIT](LICENSE)

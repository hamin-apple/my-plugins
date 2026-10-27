# Handoff: Windows에서 my-agent 모니터 List 창

작성 2026-10-27 (macOS 세션). Windows PC의 Claude Code 세션이 이 문서만 보고 시작할 수 있게 정리했다.

## 목표

macOS 메뉴바 앱의 미니 창(작업 한 줄 목록 → 줄 클릭 시 상세)과 같은 사용감을 Windows에서 얻는다. Swift 앱은 macOS 전용이므로 **웹 모니터에 List 화면을 더하고, Edge 앱 창으로 작게 띄우는 방식**을 권한다(macOS 세션에서 검토만 함, 아직 승인된 계획 아님).

- 웹: `index.html`에 `#view=list` 모드. 한 작업 한 줄(상태 기호 `?`/점/`✓`/`■`, 작업 ID, 단계 `5. Execute`, 경과, 8칸 진행 막대), 진행 중·답 대기 먼저, 필터 All/Running/Done/Stopped, 진행 중 줄 깜빡임(1.4 s, opacity .3, `prefers-reduced-motion`이면 멈춤). 줄 클릭 → 같은 창에서 `#task=<key>` 상세로.
- 실행: `monitor-up.py --open --view list` 같은 옵션 → Edge `msedge --app=<url>#view=list --window-size=320,700`.
- 한계: Edge 앱 창은 "항상 위(핀)"와 모드별 창 크기 기억이 없다. 필요하면 별도 작업으로 네이티브(WinUI/WPF 등)나 PowerToys "Always on Top"(Win+Ctrl+T)으로 해결.

## 시작 전 조건

1. macOS 쪽 작업 `261027-monitor-mini-window`(메뉴바 미니 창)가 커밋·push되어야 한다. 이 작업이 `/api/tasks` 요약에 `elapsed`(분)를 더했고, List가 그 값을 쓴다. 2026-10-27 현재 커밋 전(Verify 재실행 중).
2. Windows에서: `git clone https://github.com/hamin-apple/my-plugins.git` (또는 pull), Python 3, Edge.

## 지금 코드에서 Windows에 걸리는 곳 (확인한 사실)

| 위치 | 내용 | 영향 |
|---|---|---|
| `plugins/my-agent/monitor/monitor/opener.py` | 창 열기가 macOS 전용: `open`, `osascript`, LaunchServices plist로 기본 브라우저 판별 | Windows에서는 모든 명령이 실패해 `'failed'` 반환(예외는 안 남). Windows 분기 필요: `msedge --app=` 또는 `os.startfile(url)`/`webbrowser` |
| `plugins/my-agent/monitor/monitor-up.py` | 서버를 `subprocess.Popen(..., start_new_session=True)`로 띄움, `stop`은 `os.kill(pid, SIGTERM)` | `start_new_session`은 Windows에서 효과 없음 → 콘솔을 닫으면 서버가 같이 죽을 수 있음. `creationflags=DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP` 검토. `os.kill`은 Windows에서 강제 종료로 동작 |
| `plugins/my-agent/l4-tools-guards/hooks/hooks.json` | hook 명령이 `python3 "..."` | Windows에 `python3`가 없으면(`py`/`python`만 있으면) hook 전체가 실패. Windows에서 my-agent를 쓰려면 먼저 확인 |
| `plugins/my-agent/monitor/menubar/` | Swift, AppKit/SwiftUI/WebKit | Windows 대상 아님. 건드리지 않음 |
| 경로 | `~/dev/agent-tasks`, `~/.claude/projects` (`Path.home()` 기준) | Windows에서도 `%USERPROFILE%\dev\agent-tasks` 등으로 동작할 것으로 보임(미확인) |

## 재사용할 것

- `web/index.html`: `statusTxt`/`statusBadge`/`stepState`(약 537–539행), 사이드바 `renderList`(약 559–575행)의 mini-rail, `STEP_NAME`(약 471행), `#task=` 해석(973행), 전역 `selectTask(key)`(967행 부근). `POLL_MS = 2000`.
- macOS List 규칙(정렬·필터·단계 표시·경과 표기)은 `plugins/my-agent/monitor/menubar/Sources/ListModel.swift`와 `menubar/README.md` "Mini window"에 있다. 같은 규칙으로 맞추면 두 플랫폼이 같게 보인다.
- 주의(`CLAUDE.md`): `index.html`은 `monitor/tools/build-web.py`로 다시 만들면 직접 수정이 사라진다. 직접 고친다.

## 지켜야 할 제약

- 모니터 서버는 읽기 전용. 새 쓰기 경로·OS 동작 엔드포인트 금지.
- 기존 macOS 동작(Open Monitor, 메뉴바 앱, `monitor-up.py` 기본 동작)은 바뀌면 안 된다. Windows 분기는 `sys.platform == 'win32'`(또는 `os.name == 'nt'`)로 나눈다.
- 버전을 올리면 `plugins/my-agent/.claude-plugin/plugin.json`과 루트 `README.md` 표를 같은 커밋에서 함께 바꾼다.

## 테스트

```sh
cd plugins/my-agent/monitor && python3 -m unittest discover tests            # 모니터 (macOS 기준 116개, Swift 테스트는 swiftc 없으면 skip)
cd plugins/my-agent && python3 -m unittest discover -s l4-tools-guards/tests   # L1~L4 (214개)
```

Windows에서 처음 돌리면 macOS 가정(`open`, plist 경로, 경로 구분자) 때문에 실패하는 테스트가 있을 수 있다. 먼저 한 번 돌려 목록을 남기고 시작한다.

## 진행 방법 (권장)

Windows의 Claude Code에서 저장소 루트로 열고:

```text
/my-agent 웹 모니터에 #view=list 화면(작업 한 줄 목록, 필터, 진행 막대, 줄 클릭 시 상세)을 더하고, Windows에서 monitor-up.py로 Edge 앱 창(약 320x700)에 띄울 수 있게 해줘. macOS 동작은 그대로, 서버는 읽기 전용. 참고: docs/handoff/windows-list-window.md
```

- 프로파일: dev. Intake에서 `Follows: 261027-monitor-mini-window`.
- 첫 단계(Explore)에서 위 "걸리는 곳" 표를 Windows에서 실제로 확인한다(특히 hook의 `python3`, 테스트 실패 목록).
- 범위가 크면 둘로 나눈다: (1) 웹 `#view=list`(플랫폼 무관, macOS 브라우저에서도 확인 가능) (2) Windows 실행 경로(opener·monitor-up).

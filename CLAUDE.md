# my-plugins

Claude Code 플러그인 마켓플레이스. 지금은 `my-agent` 하나(HITL 멀티 에이전트 오케스트레이션: 계획 → 실행 → 검증 → 리뷰). 사용자용 설명은 `README.md`(영문)와 `README-ko.md`(한국어).

## 구조 (`plugins/my-agent/`)

- `.claude-plugin/plugin.json`: 스킬·에이전트·hook 등록. 저장소 루트 `.claude-plugin/marketplace.json`은 플러그인 목록.
- `SKILL.md`: L1(메인 세션) 진입점. 핵심 규칙은 앞 6,000자 안에 둔다(`test_skill_md`가 확인).
- `l1-orchestration/phases/`(define·plan·build·accept), `profiles/`(general·research·dev): 단계별 L1 절차.
- `l2-design-judge/agents/`(architect·plan-reviewer·verifier·reviewer·gate-analyst), `l3-workers/agents/`(explorer·researcher·writer·coder): 서브에이전트 정의.
- `l4-tools-guards/`: `hooks/`(hooks.json + 가드 스크립트), `scripts/`(run-log·feedback·gate-report·secret-scan·check-run), `lib/`(공용 `ma_*.py`), `permissions/`, `tests/`.
- `monitor/`: 읽기 전용 로컬 웹 모니터. `server.py`(JSON API), `monitor/`(mdfiles·taskview 등 데이터), `web/index.html`(화면 전부), `monitor-up.py`(실행·창 열기), `menubar/`(Swift 앱: 메뉴 + List/Detail 미니 창).
- `skills/monitor/`: `/my-agent:monitor` 스킬.
- `docs/build-guide/`: 설계 문서(`my-agent-architecture.md`가 기준), `docs/ref/`: Claude Code 참고 문서.
- `maintenance-notes.md`: 레벨별 현재 상태·외부 의존·주의점. 고치면 해당 절에 날짜와 함께 더한다.

## 테스트

```sh
cd plugins/my-agent && python3 -m unittest discover -s l4-tools-guards/tests   # L1~L4 규칙·hook (214개)
cd plugins/my-agent/monitor && python3 -m unittest discover tests            # 모니터 (116개)
```

빌드 단계는 없다(Python 표준 라이브러리 + 정적 HTML). 예외: `monitor/menubar/`의 Swift 앱은 `sh menubar/build.sh`로 빌드한다(선택).

## 주의

- 버전을 올릴 때는 `plugins/my-agent/.claude-plugin/plugin.json`의 `version`과 `README.md`·`README-ko.md` 플러그인 표의 버전을 같은 커밋에서 함께 바꾼다. 세 값은 항상 같아야 한다.
- `README.md`(영문)와 `README-ko.md`(한국어)는 같은 내용이다. 하나를 고치면 다른 하나도 함께 고친다(요구 사항의 도구 버전 포함).
- my-agent는 `docs/build-guide/my-agent-architecture.md` 설계대로만 동작해야 한다. 임시 예외·우회 문구를 런타임 규칙에 넣지 않는다.
- `monitor/web/index.html`은 `monitor/tools/build-web.py`가 생성했지만 이후 직접 수정되어 있다. 생성기를 다시 돌리면 직접 수정이 사라진다.
- `docs/agent/`(my-agent 작업 기록)와 `.superpowers/`는 git에서 제외된다.

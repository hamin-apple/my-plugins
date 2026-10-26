# 시나리오 (설계 4.13절)

프로파일마다 작은 작업 1건을 처음부터 끝까지 사람과 함께 돌립니다. L1·L2 파일(SKILL.md, phase·프로파일 파일, 에이전트 정의)을 고칠 때마다 다시 돌리고 결과를 `maintenance-notes.md`에 남깁니다.

- 어디서: `~/dev/labs/my-agent-sandbox`, `claude --plugin-dir ~/dev/my-plugins/plugins/my-agent` (설치 전). 권한 모드는 auto.
- 시작 전: 샌드박스에 남은 `docs/agent/.active`가 있으면 Intake 1번 팝업에서 `그 작업 중단 후 새로 시작`을 고릅니다.
- 통과 조건: 끝난 뒤 `python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/check-run.py ~/dev/labs/my-agent-sandbox/docs/agent/<task-id>`가 exit 0, 그리고 파일마다 적은 "확인할 것".
- 팝업 답은 파일에 적힌 대로 고릅니다. 적히지 않은 팝업이 뜨면 그 내용을 결과에 적고 권장안을 고릅니다.

| 파일 | 프로파일 | 정상 경로 팝업 |
|---|---|---|
| `general.md` | general | G1b, G3 |
| `research.md` | research | G1a, G1b, G3 |
| `dev.md` | dev (작은 작업) | G1b, G3 커밋 |

# 시나리오: 일반 프로파일

**요청 (그대로 입력):**

```text
/my-agent 회의록 템플릿을 만들어 줘. 안건, 결정 사항, 할 일(담당자·기한) 표가 있는 마크다운 한 장이고, 저장 위치는 templates/meeting-notes.md야. 다른 템플릿은 필요 없어.
```

**기대:** `Profile: general`. Explore는 생략(`explore.md`에 `생략:`). 인터뷰 없음(목적, 완료 기준, 비목표, 위치가 요청에 있음).

| 팝업 | 고를 답 |
|---|---|
| `.gitignore` (처음 한 번) | `커밋 안 함 (Recommended)` |
| G1b 계획 승인 | `승인 (Recommended)` — 그 전에 채팅에 `## Mock-up` 전문이 붙었는지 봄 |
| G3 최종 수용 | `수용 (Recommended)` — 팝업에 저장 경로 `…/templates/meeting-notes.md`가 보이는지 봄 |

**확인할 것**

1. `check-run.py` exit 0, `info popups: 2`.
2. G1b 전에 `Write`가 작업 폴더 밖으로 가지 않았다(run-log에 G1b 전 `fix`/`deliver` 없음).
3. `templates/meeting-notes.md`가 있고 `intake.md`에 `Delivered:`가 있다.
4. `.active`가 지워졌다.

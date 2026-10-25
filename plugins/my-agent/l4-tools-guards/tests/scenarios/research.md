# 시나리오: 조사·문서 프로파일

**요청 (그대로 입력):**

```text
/my-agent Python 표준 라이브러리 shlex의 split, quote, join이 각각 무엇을 하는지 공식 문서(docs.python.org)만 근거로 조사해서 노트 한 장으로 정리해 줘.
```

**기대:** `Profile: research`. Scope 인터뷰는 요청에 없는 항목(결과물 형식의 저장 경로 등)만 묻습니다.

| 팝업 | 고를 답 |
|---|---|
| Scope 인터뷰 (뜨면) | 권장안. 저장 경로를 물으면 `deliverable/` 기본값 |
| G1a 범위 확정 | `확정 (Recommended)` |
| G1b 계획 승인 | `승인 (Recommended)` — mock-up이 목차 + 샘플 단락 1개인지 봄 |
| G3 최종 수용 | `수용 (Recommended)` |

**확인할 것**

1. `check-run.py` exit 0, `info popups: 3`(인터뷰 팝업은 `Q`로 따로 셈).
2. `scope.md`에 질문 · 범위 · 출처 기준 · 결과물 형식과 `## Confirmation`의 `Confirmed` 줄.
3. researcher의 `start:`가 G1b `answer:` 뒤에만 있다.
4. `work/` 노트의 모든 항목이 `- <주장> · <출처 URL> · "<인용>"` 형식.
5. `verify.md`의 `## 확인한 명령`에 WebFetch로 대조한 URL이 있다.

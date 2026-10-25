# 시나리오: 개발 프로파일 (작은 작업)

**준비 (사람이 한 번):** 샌드박스에 작은 코드와 테스트를 만들고 커밋합니다. 커밋은 사용자 승인으로 합니다.

```bash
cd ~/dev/my-agent-sandbox && mkdir -p tools tests
cat > tools/wc.py <<'PY'
import sys


def count_words(text: str) -> int:
    return len(text.split())


if __name__ == '__main__':
    print(count_words(sys.stdin.read()))
PY
cat > tests/test_wc.py <<'PY'
import unittest

from tools.wc import count_words


class WcTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(count_words('a b  c\n'), 3)
PY
touch tools/__init__.py tests/__init__.py && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . && git add tools tests && git commit -m "sandbox: wc tool"
```

**요청 (그대로 입력):**

```text
/my-agent tools/wc.py에 --lines 옵션을 더해 줘. 주면 단어 대신 줄 수를 출력해. 빈 입력은 0. 다른 옵션은 필요 없어.
```

**기대:** `Profile: dev`, 작은 작업 예외(고칠 파일 2개, 목적·완료 기준·비목표가 요청에 있음) → G1a 없음, `plan-review.md`가 `Verdict: SKIPPED 작은 작업`.

| 팝업 | 고를 답 |
|---|---|
| G1b 계획 승인 | `승인 (Recommended)` |
| G3 커밋 승인 | `커밋 (Recommended)` — diff와 메시지(`criteria:` 번호)가 보이는지 봄 |
| G2 `git commit` 권한 창 | 이번 한 번 허용 |

**확인할 것**

1. `check-run.py` exit 0, `info popups: 2`.
2. run-log에 `base commit=` 줄, `git log -1`의 메시지에 완료 기준 번호.
3. `verify.md`에 `Run: 1`과 테스트 명령 결과.
4. coder가 커밋하지 않았다(커밋은 G3 뒤 하나뿐).

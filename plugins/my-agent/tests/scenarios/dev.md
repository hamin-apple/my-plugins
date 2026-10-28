# Scenario: dev profile (small task)

**Setup (the person, once):** create a small piece of code and a test in the sandbox and commit them. The commit is made with the user's approval.

```bash
cd ~/dev/labs/my-agent-sandbox && mkdir -p tools tests
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

**Request (type as is):**

```text
/my-agent Add a --lines option to tools/wc.py. When given, print the number of lines instead of words. Empty input gives 0. No other options needed.
```

**Expected:** `Profile: dev`, small task exception (2 files to change; purpose, completion criteria and non-goals are in the request) → no G1a, `plan-review.md` is `SKIPPED small task`.

| Popup | Answer to pick |
|---|---|
| G1b Plan approval | `Approve (Recommended)` |
| G3 commit approval | `Commit (Recommended)` — check that the diff and the message (`criteria:` numbers) are shown |
| G2 `git commit` permission prompt | Allow once |

**Check**

1. `check-run.py` exit 0, `info popups: 2`.
2. A `base commit=` line in the run-log, and completion criterion numbers in the `git log -1` message.
3. `Run: 1` and the test command result in `verify.md`.
4. The coder did not commit (the only commit is the one after G3).

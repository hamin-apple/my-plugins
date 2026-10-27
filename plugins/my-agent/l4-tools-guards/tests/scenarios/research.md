# Scenario: research profile

**Request (type as is):**

```text
/my-agent Research what split, quote and join in the Python standard library module shlex each do, using only the official docs (docs.python.org) as evidence, and summarize it in one note.
```

**Expected:** `Profile: research`. The Scope interview asks only about items missing from the request (such as the save path in the deliverable format).

| Popup | Answer to pick |
|---|---|
| Scope interview (if shown) | The recommended option. If it asks for the save path, the `deliverable/` default |
| G1a Scope confirmation | `Confirm (Recommended)` |
| G1b Plan approval | `Approve (Recommended)` — check that the mock-up is an outline + 1 sample paragraph |
| G3 Final acceptance | `Accept (Recommended)` |

**Check**

1. `check-run.py` exit 0, `info popups: 3` (interview popups are counted separately as `Q`).
2. `scope.md` has questions · scope · source criteria · deliverable format and the `Confirmed` line under `## Confirmation`.
3. The researcher's `start:` comes only after the G1b `answer:`.
4. Every item in the `work/` notes is in the format `- <claim> · <source URL> · "<quote>"`.
5. `## Commands run` in `verify.md` lists the URLs checked with WebFetch.

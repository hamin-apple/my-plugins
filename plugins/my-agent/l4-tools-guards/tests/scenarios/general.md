# Scenario: general profile

**Request (type as is):**

```text
/my-agent Make a meeting notes template. One Markdown page with tables for agenda, decisions, and action items (owner, due date), saved at templates/meeting-notes.md. No other templates needed.
```

**Expected:** `Profile: general`. Explore is skipped (`Skipped:` in `explore.md`). No interview (purpose, completion criteria, non-goals and location are in the request).

| Popup | Answer to pick |
|---|---|
| `.gitignore` (first time only) | `Don't commit (Recommended)` |
| G1b Plan approval | `Approve (Recommended)` — first check that the full `## Mock-up` was pasted in the chat |
| G3 Final acceptance | `Accept (Recommended)` — check that the popup shows the save path `…/templates/meeting-notes.md` |

**Check**

1. `check-run.py` exit 0, `info popups: 2`.
2. Before G1b, no `Write` went outside the task folder (no `fix`/`deliver` in the run-log before G1b).
3. `templates/meeting-notes.md` exists and `intake.md` has `Delivered:`.
4. `.active` is removed.

# Scenarios (design section 4.13)

For each profile, run one small task from start to finish together with the person. Run them again every time an L1 or L2 file changes (SKILL.md, phase and profile files, agent definitions), and record the results in `maintenance-notes.md`.

- Where: `~/dev/labs/my-agent-sandbox`, `claude --plugin-dir ~/dev/my-plugins/plugins/my-agent` (before install). Permission mode auto.
- Before starting: if the sandbox still has a `docs/agent/.active`, pick `Abort that task and start new` in Intake popup 1.
- Pass condition: after the run, `python3 ~/dev/my-plugins/plugins/my-agent/l4-tools-guards/scripts/check-run.py ~/dev/labs/my-agent-sandbox/docs/agent/<task-id>` exits 0, and the "Check" items in each file hold.
- Pick popup answers as written in the file. If a popup not listed appears, note its content in the results and pick the recommended option.

| File | Profile | Normal-path popups |
|---|---|---|
| `general.md` | general | G1b, G3 |
| `research.md` | research | G1a, G1b, G3 |
| `dev.md` | dev (small task) | G1b, G3 commit |

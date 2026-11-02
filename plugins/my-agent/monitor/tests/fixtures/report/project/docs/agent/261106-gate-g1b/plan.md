# Plan: 261106-gate-g1b

Two coder units: the dated file name, then the docs.

## Work units

### u1 Dated export names
- Agent: my-agent:coder
- Files to change: `src/app.py`
- Parallel group: group 1
- Completion criteria: 1
- Status: pending

### u2 Docs
- Agent: my-agent:coder
- Files to change: `README.md`
- Parallel group: group 2
- Completion criteria: 2
- Status: pending

## Estimate
- Subagents: 6 (2 my-agent:coder plus 4 judges).
- Workflow: none.

## Models
Preset: standard (definition values)

| Agent | Model | Effort | Note |
|---|---|---|---|
| architect | opus | high | |
| coder | sonnet | medium | |

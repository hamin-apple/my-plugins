#!/usr/bin/env python3
"""Plugin hook (hooks.json, PreToolUse: Agent|Workflow|Edit|Write|NotebookEdit|Bash): the G1b hard gate
(architecture 4.4 "G1b hard gate").

Runs in every session where the plugin is on, so it first narrows down: a call from inside a subagent (`agent_id` in
the input) passes; no task found passes (a `.active` without `task:` warns, before the session check); a `.active`
whose `session:` differs from the input `session_id` (both set) passes. Only then the verdict below.

While a task is active and its `plan.md` has no `Approved` line under `## Approval`, deny delegation and writes,
whatever the phase. Allowed before approval: my-agent:explorer / architect / plan-reviewer (and writer once
`Prototype: requested` is under plan.md's `## Prototype`), and writes under `<location>/docs/agent/` or to the data folder's
`active-index.json` / `projects.txt` (and `mkdir -p` of the data folder itself, Intake step 7). A `.active` without `task:` → pass with a warning (C9). A task folder that is gone → pass with a
warning. Any error → exit 2, so the tool call is blocked (and `onFailure: block` covers a crash or timeout).

After approval, a write outside the location, the data folder and the result path that plan.md / scope.md
declare (`- Deliverable location: `…`` or `- Save path: `…``) gets `ask`: auto mode lets such a write through without a
prompt (probe 2026-10-25). A Bash write whose target cannot be told passes, as before (git commit asks via G2).
The gate-report copy folder (`ma_gate_report.report_dir()`, $MA_GATE_REPORT_DIR) counts as a place too; G1b is unchanged.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_bash  # noqa: E402
import ma_gate_report  # noqa: E402
import ma_plan  # noqa: E402
import ma_schema  # noqa: E402
from ma_path import same, under  # noqa: E402

BEFORE_APPROVAL = {f'my-agent:{name}' for name in ma_schema.BEFORE_APPROVAL}
REASON = 'Task {task}: plan.md has no approval line, so delegation and writes are blocked (G1b). {what}'
ASK = 'Task {task}: a write outside the task location ({paths}). It is not the deliverable location in the scope document, so confirm it.'
RESULT_LINE = re.compile(r'(?m)^\s*-\s*(?:Deliverable location|Save path)\s*:\s*`([^`]+)`')


def allowed_write(p: Path, active, tasks_dir: Path) -> bool:
    return (under(p, active.location / 'docs' / 'agent')
            or any(same(p, tasks_dir / n) for n in ('', 'active-index.json', 'projects.txt')))  # '' = mkdir -p


def result_paths(active) -> list:
    """Result locations declared in plan.md and scope.md (relative ones against the location)."""
    out = []
    for name in ('plan.md', 'scope.md'):
        try:
            text = (active.task_dir / name).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for raw in RESULT_LINE.findall(text):
            p = Path(os.path.expanduser(raw.strip()))
            out.append((p if p.is_absolute() else active.location / p).resolve())
    return out


def write_paths(tool: str, ti: dict, cwd: Path):
    """Paths a call writes ([] for none), or None when a Bash write cannot be told."""
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        p = Path(os.path.expanduser(ti.get('file_path') or ti.get('notebook_path') or ''))
        return [(p if p.is_absolute() else cwd / p).resolve()]
    if tool == 'Bash':
        return ma_bash.write_targets(ti.get('command') or '', cwd)
    return []


def outside_ask(inp: dict, active, tasks_dir: Path):
    """Ask reason for an approved task's write outside its places, or None."""
    cwd = Path(inp.get('cwd') or os.getcwd())
    paths = write_paths(inp.get('tool_name'), inp.get('tool_input') or {}, cwd) or []
    places = [active.location, tasks_dir, ma_gate_report.report_dir().resolve()] + result_paths(active)
    outside = [str(p) for p in paths if not any(under(p, q) for q in places)]
    return ASK.format(task=active.task, paths=', '.join(outside)) if outside else None


def decide(inp: dict, active, tasks_dir: Path):
    """Deny reason, or None to let the call through."""
    plan_md = active.task_dir / 'plan.md'
    if ma_plan.approved(plan_md):
        return None
    tool, ti = inp.get('tool_name'), inp.get('tool_input') or {}
    cwd = Path(inp.get('cwd') or os.getcwd())
    reason = lambda what: REASON.format(task=active.task, what=what)  # noqa: E731
    if tool == 'Agent':
        agent = ti.get('subagent_type') or ''
        if agent in BEFORE_APPROVAL or (agent == 'my-agent:writer' and ma_plan.prototype_requested(plan_md)):
            return None
        return reason(f'Before approval only explorer, architect and plan-reviewer get work (requested: {agent or "-"}).')
    if tool == 'Workflow':
        return reason('No workflow runs before approval.')
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        raw = ti.get('file_path') or ti.get('notebook_path') or ''
        p = Path(os.path.expanduser(raw))
        p = (p if p.is_absolute() else cwd / p).resolve()
        return None if allowed_write(p, active, tasks_dir) else reason(f'Write outside the task folder: {p}')
    if tool == 'Bash':
        targets = ma_bash.write_targets(ti.get('command') or '', cwd)
        if targets is None:
            return reason('Cannot tell where this command writes (a git change, a variable path, etc.).')
        outside = [str(t) for t in targets if not allowed_write(t, active, tasks_dir)]
        return reason(f'Write outside the task folder: {", ".join(outside)}') if outside else None
    return None


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read())
        if not isinstance(inp, dict):
            raise ValueError('hook input is not an object')
        if ma_active.in_subagent(inp):
            return 0
        tasks_dir = ma_active.default_tasks_dir().expanduser().resolve()
        broken = []
        active = ma_active.find_active(inp.get('cwd') or os.getcwd(), tasks_dir, broken)
        if active is None:
            if broken:
                print(json.dumps({'systemMessage': ma_active.BROKEN.format(path=broken[0])}, ensure_ascii=False))
            return 0
        if not ma_active.owns(active, inp):
            return 0
        if not active.task_dir.is_dir():
            print(json.dumps({'systemMessage': f'my-agent: the task folder {active.task_dir} that .active points to does not exist'},
                             ensure_ascii=False))
            return 0
        why, decision = decide(inp, active, tasks_dir), 'deny'
        if not why and ma_plan.approved(active.task_dir / 'plan.md'):
            why, decision = outside_ask(inp, active, tasks_dir), 'ask'
        if why:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': decision,
                                                     'permissionDecisionReason': why}}, ensure_ascii=False))
        return 0
    except Exception as e:   # block the call: exit 2 is a blocking error for PreToolUse
        print(f'plan-approved-check: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

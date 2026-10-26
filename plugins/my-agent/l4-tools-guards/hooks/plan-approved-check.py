#!/usr/bin/env python3
"""Skill hook (PreToolUse: Agent|Workflow|Edit|Write|NotebookEdit|Bash): the G1b hard gate
(architecture 4.4 "G1b 하드 게이트").

While a task is active and its `plan.md` has no `Approved` line under `## Approval`, deny delegation and writes,
whatever the phase. Allowed before approval: my-agent:explorer / architect / plan-reviewer (and writer once
`Prototype: requested` is in plan.md), and writes under `<location>/docs/agent/` or to the agent-tasks
`active-index.json` / `projects.txt` (and `mkdir -p` of the agent-tasks folder itself, Intake step 7). No `.active` → exit 0 at once. A task folder that is gone → pass with a
warning. Any error → exit 2, so the tool call is blocked (and `onFailure: block` covers a crash or timeout).

After approval, a write outside the location, the agent-tasks folder and the result path that plan.md / scope.md
declare (`- 결과물 위치: `…`` or `- 저장 경로: `…``) gets `ask`: auto mode lets such a write through without a
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
from ma_path import same, under  # noqa: E402

BEFORE_APPROVAL = {'my-agent:explorer', 'my-agent:architect', 'my-agent:plan-reviewer'}
REASON = '작업 {task}: plan.md에 승인 줄이 없어 위임과 쓰기를 막았습니다 (G1b). {what}'
ASK = '작업 {task}: 작업 위치 밖 쓰기입니다 ({paths}). 범위 문서의 결과물 위치가 아니므로 확인합니다.'
RESULT_LINE = re.compile(r'(?m)^\s*-\s*(?:결과물 위치|저장 경로)\s*:\s*`([^`]+)`')


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
        return reason(f'승인 전에는 explorer, architect, plan-reviewer만 맡깁니다 (요청: {agent or "-"}).')
    if tool == 'Workflow':
        return reason('승인 전에는 workflow를 실행하지 않습니다.')
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        raw = ti.get('file_path') or ti.get('notebook_path') or ''
        p = Path(os.path.expanduser(raw))
        p = (p if p.is_absolute() else cwd / p).resolve()
        return None if allowed_write(p, active, tasks_dir) else reason(f'작업 폴더 밖 쓰기: {p}')
    if tool == 'Bash':
        targets = ma_bash.write_targets(ti.get('command') or '', cwd)
        if targets is None:
            return reason('어디에 쓰는지 알 수 없는 명령입니다 (git 변경, 변수 경로 등).')
        outside = [str(t) for t in targets if not allowed_write(t, active, tasks_dir)]
        return reason(f'작업 폴더 밖 쓰기: {", ".join(outside)}') if outside else None
    return None


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read())
        if not isinstance(inp, dict):
            raise ValueError('hook input is not an object')
        tasks_dir = ma_active.default_tasks_dir().expanduser().resolve()
        active = ma_active.find_active(inp.get('cwd') or os.getcwd(), tasks_dir)
        if active is None:
            return 0
        if not active.task_dir.is_dir():
            print(json.dumps({'systemMessage': f'my-agent: .active가 가리키는 작업 폴더 {active.task_dir}가 없습니다'},
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

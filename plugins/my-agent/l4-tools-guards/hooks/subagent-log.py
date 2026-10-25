#!/usr/bin/env python3
"""Plugin hook: record my-agent subagent calls in the active task's run-log (architecture 4.7.2).

usage: subagent-log.py call|start|stop   (hook input JSON on stdin)

call   PreToolUse(Agent): `call:` line with the call's model, effort, isolation, background
start  SubagentStart: `start:` line with the expected model and effort (call → definition file) and session
stop   SubagentStop: `stop:` line with the answering model, tokens, time, result, end (from the transcript),
       permission mode and effort; once per agent id
start and stop first sweep agents that ended without SubagentStop (lib/ma_subagent.py).

Writes nothing when no `.active` is found or the agent is not `my-agent:*`.
Always exits 0 with no output; a failure becomes a `log-error` line when it can.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_logline  # noqa: E402
import ma_subagent  # noqa: E402

HANDBACK_WAIT = 3   # seconds to wait for a late SubagentHandback line (live run 2026-10-25)
PREFIX = 'my-agent:'


def plugin_root() -> Path:
    return Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or Path(__file__).resolve().parents[2])


def definition(name: str) -> dict:
    """Frontmatter `key: value` pairs of the plugin agent `<name>.md`, or {} when it is not listed."""
    root = plugin_root()
    try:
        agents = json.loads((root / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')).get('agents') or []
    except (OSError, ValueError):
        return {}
    for rel in [agents] if isinstance(agents, str) else agents:
        if Path(rel).name == f'{name}.md':
            try:
                text = (root / rel).read_text(encoding='utf-8')
            except OSError:
                return {}
            m = re.match(r'---\n(.*?)\n---', text, re.S)
            out = {}
            for line in (m.group(1).splitlines() if m else []):
                key, sep, value = line.partition(':')
                if sep:
                    out[key.strip()] = value.strip().strip('\'"')
            return out
    return {}


def do_call(inp, active):
    ti = inp.get('tool_input') or {}
    agent = ti.get('subagent_type') or ''
    if inp.get('tool_name') != 'Agent' or not agent.startswith(PREFIX):
        return
    bg = ti.get('run_in_background')
    ma_logline.append(active.log, ma_logline.format_line('call', [
        ('agent', agent), ('model', ti.get('model')), ('effort', ti.get('effort')),
        ('isolation', ti.get('isolation')), ('background', bool(bg) if bg is not None else False)]))


def do_start(inp, active):
    agent = inp.get('agent_type') or ''
    if not agent.startswith(PREFIX):
        return
    calls = [f for k, f in ma_logline.read(active.log) if k == 'call' and f.get('agent') == agent]
    last = calls[-1] if calls else {}
    defn = definition(agent[len(PREFIX):])
    configured = last.get('model') if last.get('model') not in (None, '-') else defn.get('model')
    effort = last.get('effort') if last.get('effort') not in (None, '-') else defn.get('effort')
    if os.environ.get('CLAUDE_CODE_EFFORT_LEVEL'):
        effort = f"{os.environ['CLAUDE_CODE_EFFORT_LEVEL']}(env)"
    if not defn:
        ma_logline.log_error(active, 'subagent-log start', LookupError(f'no definition for {agent} in plugin.json agents'))
    ma_logline.append(active.log, ma_logline.format_line('start', [
        ('agent', agent), ('id', inp.get('agent_id')), ('configured', configured or 'unknown'),
        ('effort', effort), ('session', inp.get('session_id'))]))


def do_stop(inp, active):
    if not (inp.get('agent_type') or '').startswith(PREFIX):
        return
    agent_id = inp.get('agent_id')
    lines = ma_logline.read(active.log)
    started, stopped = ma_subagent.runs(lines, agent_id)
    if stopped >= started > 0:
        return   # every run already closed (a repeated event, or the sweep)
    since = ma_subagent.run_since(active.log, agent_id) if stopped else None   # a resumed run (F33)
    message = (inp.get('last_assistant_message') or '').strip()
    sums, actual, secs, error = None, None, None, False
    try:
        sums, models, secs, last = ma_subagent.read_transcript(inp.get('agent_transcript_path') or '', since)
        actual = models.most_common(1)[0][0] if models else None
        if last and last.get('isApiErrorMessage'):
            error = True
        deadline = time.time() + HANDBACK_WAIT
        while not message:   # the SubagentHandback line can reach the transcript just after SubagentStop fires
            message = ma_subagent.handback_message(inp.get('agent_transcript_path') or '', since).strip()
            if message or time.time() >= deadline:
                break
            time.sleep(0.25)
    except OSError as exc:
        ma_logline.log_error(active, 'subagent-log stop', exc)
        error = True
    error = error or not message
    effort = inp.get('effort')
    ma_logline.append(active.log, ma_subagent.stop_line(
        lines, agent_id, sums, actual, secs, ma_subagent.first_line(message), 'error' if error else 'ok',
        mode=inp.get('permission_mode'), effort=effort.get('level') if isinstance(effort, dict) else effort))


def main(argv) -> int:
    active = None
    try:
        mode = argv[1] if len(argv) > 1 else ''
        inp = json.loads(sys.stdin.read() or '{}')
        if not isinstance(inp, dict):
            return 0
        active = ma_active.find_active(inp.get('cwd') or os.getcwd())
        if active is None:
            return 0
        handler = {'call': do_call, 'start': do_start, 'stop': do_stop}[mode]
        if mode in ('start', 'stop'):
            try:
                ma_subagent.sweep(active)
            except Exception as exc:
                ma_logline.log_error(active, 'subagent-log sweep', exc)
        handler(inp, active)
    except BaseException as exc:   # a record hook never fails the session
        if active is not None:
            ma_logline.log_error(active, f"subagent-log {argv[1:] or ''}", exc)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

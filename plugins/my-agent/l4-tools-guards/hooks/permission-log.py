#!/usr/bin/env python3
"""Plugin hook: record G2 permission prompts in the active task's run-log (architecture 4.7.2 "G2 records").

usage: permission-log.py ask|answer   (hook input JSON on stdin)

ask     PermissionRequest: `ask: gate=G2 agent= id= tool= q=` just before Claude Code shows the prompt
answer  PostToolUse: `answer: gate=G2 id= result=allowed`, only when this call is the newest
        unanswered G2 ask (same tool and q). A denial has no event and is not recorded.

Both lines carry `session=<session_id>` when the input has it. Writes nothing when no `.active` is found, or
when the input's `session_id` differs from `.active` `session:` (another session of the same repo, ma_active.owns).
Always exits 0 with no output.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_logline  # noqa: E402

Q_MAX = 200


def summary(tool, ti) -> str:
    ti = ti if isinstance(ti, dict) else {}
    if tool == 'Bash' and isinstance(ti.get('command'), str):
        text = ti['command']
    elif tool in ('Edit', 'Write', 'Read', 'NotebookEdit') and isinstance(ti.get('file_path') or ti.get('notebook_path'), str):
        text = ti.get('file_path') or ti.get('notebook_path')
    else:
        text = json.dumps(ti, ensure_ascii=False, separators=(',', ':'))
    text = ' '.join(text.splitlines())
    return text if len(text) <= Q_MAX else text[:Q_MAX - 1] + '…'


def running_agent(lines):
    """(agent, id) of the one subagent started and not stopped, else None."""
    started = {}
    for kind, f in lines:
        if kind == 'start' and f.get('id'):
            started[f['id']] = f.get('agent')
        elif kind == 'stop':
            started.pop(f.get('id'), None)
    return next(iter(started.items()))[::-1] if len(started) == 1 else None


def open_asks(lines):
    """G2 ask fields not yet answered, oldest first (an answer closes the newest open ask with its id)."""
    out = []
    for kind, f in lines:
        if f.get('gate') != 'G2':
            continue
        if kind == 'ask':
            out.append(f)
        elif kind == 'answer':
            for i in range(len(out) - 1, -1, -1):
                if out[i].get('id') == f.get('id'):
                    del out[i]
                    break
    return out


NOT_G2 = {'AskUserQuestion'}   # a question popup also raises PermissionRequest; L1 logs it as its own gate


def session_field(inp):
    sid = inp.get('session_id')
    return [('session', sid)] if isinstance(sid, str) and sid else []


def do_ask(inp, active):
    tool = inp.get('tool_name') or '-'
    if tool in NOT_G2:
        return
    agent, agent_id = inp.get('agent_type'), inp.get('agent_id')
    if not agent_id:
        guess = running_agent(ma_logline.read(active.log))
        agent, agent_id = guess if guess else ('main', None)
    ma_logline.append(active.log, ma_logline.format_line('ask', [
        ('gate', 'G2'), ('agent', agent or 'main'), ('id', agent_id), ('tool', tool),
        ('q', summary(tool, inp.get('tool_input')))] + session_field(inp)))


def do_answer(inp, active):
    pending = open_asks(ma_logline.read(active.log))
    if not pending:
        return
    newest = pending[-1]
    tool = inp.get('tool_name') or '-'
    if newest.get('tool') == tool and newest.get('q') == summary(tool, inp.get('tool_input')):
        ma_logline.append(active.log, ma_logline.format_line('answer', [
            ('gate', 'G2'), ('id', newest.get('id') or None), ('result', 'allowed')] + session_field(inp)))


def main(argv) -> int:
    active = None
    try:
        inp = json.loads(sys.stdin.read() or '{}')
        if not isinstance(inp, dict):
            return 0
        active = ma_active.find_active(inp.get('cwd') or os.getcwd())
        if active is None or not ma_active.owns(active, inp):
            return 0
        {'ask': do_ask, 'answer': do_answer}[argv[1] if len(argv) > 1 else ''](inp, active)
    except BaseException as exc:   # a record hook never fails the session
        if active is not None:
            ma_logline.log_error(active, f"permission-log {argv[1:] or ''}", exc)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

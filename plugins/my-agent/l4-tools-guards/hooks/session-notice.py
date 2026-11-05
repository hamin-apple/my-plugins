#!/usr/bin/env python3
"""Plugin hook (SessionStart): remind a new, resumed, cleared, compacted or forked session of an
unfinished my-agent task (architecture 4.8.2 "new-session notice"). Prints nothing when no `.active` is found.
The text depends on the session ids only, whatever the start source: the owner session (same id) gets the
"run /my-agent continue first" notice; any other session gets a text saying the original session is running the
task and how to take it over. A side without an id counts as the owner (so a fork start with no `session_id`
gets the owner notice). Always exits 0.
Codex: always prints exactly one line of plain text, also without an active task: `my-agent on Codex: plugin folder
<root> (read ${CLAUDE_PLUGIN_ROOT} in the skill text as this folder), data folder <data> (${user_config.data_dir}),
task folder <task> (${user_config.task_dir}). Before the first my-agent question, read l1-orchestration/hosts.md in
that plugin folder; ask the person only with request_user_input.`, then, with an active task, the notice text after one
space. Codex adds
a SessionStart hook's stdout to the developer context, and Codex does not expand those variables in skill text, so the
line names the folders. It is plain text, not the JSON of the Claude branch: a plain line cannot be malformed JSON.
On any failure nothing is printed.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_data  # noqa: E402
import ma_host  # noqa: E402

NOTICE = ('Unfinished my-agent task `{task}`, phase `{phase}`. Run `/my-agent continue` before doing anything else. '
          'If `plan.md` has no approval line, do not delegate or write.')
OTHER = ('The original session is running my-agent task {task} (phase {phase}). '
         'To take it over in this session, run /my-agent continue; otherwise work as usual.')


FOLDERS = ('my-agent on Codex: plugin folder {root} (read ${{CLAUDE_PLUGIN_ROOT}} in the skill text as this folder), '
           'data folder {data} (${{user_config.data_dir}}), task folder {task} (${{user_config.task_dir}}). '
           'Before the first my-agent question, read l1-orchestration/hosts.md in that plugin folder; '
           'ask the person only with request_user_input.')


def folder_line() -> str:
    root = ma_host.plugin_root(Path(__file__).resolve().parents[2])
    return FOLDERS.format(root=root, data=ma_data.data_dir(None), task=ma_data.task_dir(None))


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read() or '{}')
        if not isinstance(inp, dict):
            return 0
        codex = ma_host.hook_host(inp) == 'codex'
        inp = ma_host.record_input(inp)
        line = folder_line() if codex else None
        active = ma_active.find_active(inp.get('cwd') or os.getcwd())
        if active is None:
            if line:
                print(line)
            return 0
        text = NOTICE if ma_active.owns(active, inp) else OTHER
        msg = text.format(task=active.task, phase=active.phase or '-')
        if line:
            print(line + ' ' + msg)
            return 0
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': msg}},
                         ensure_ascii=False))
    except BaseException:   # the session starts as usual whatever happens
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Codex G2: a gate hook's ask becomes exit 2, and one L1 `answer gate=G2` line releases exactly one call.

Codex ignores the `ask` decision of a PreToolUse hook (capabilities row `ask-asymmetry`), so `ma_host.emit` hands a Codex
ask to `codex_ask()`. It blocks the call with exit 2, writes the hook's G2 `ask` line (`tool=`, `q=`, `key=`) and prints
a reason that tells L1 to ask the person in a G2 popup and to record the answer with `run-log.py answer gate=G2 ...`.

Run-log lines (all through `ma_logline`):

    ask:     gate=G2 agent=main id=- tool=<tool> q=<q> key=<key> hook=<hook> session=<sid>     (the hook)
    answer:  gate=G2 tool=<tool> q=<q> key=<key> result=allowed|denied session=<sid>           (L1, run-log.py)
    release: gate=G2 hook=<hook> tool=<tool> key=<key> session=<sid>                           (the hook)

`tool` is `apply_patch` for the file-change tool, else the input's tool name; the target is the patch's paths or the
Bash command; `key` is the first 16 hex digits of SHA-256 of `<tool>\\n<target>`, so it stands for the full target
while `q=` (one line, at most 200 characters) is for people and is not compared.

An answer is usable when it carries `tool=`, a `key=` of 16 hex digits and `result=allowed|denied`, and the newest
open ask has the same tool and key. `allowed` makes one grant for the hooks of every open ask with that tool and key;
each of those hooks releases the next call with that tool and key once (a `release` line uses its share). An answer
that is not usable is ignored, and the next block names the reason. A grant has no time limit. If the log cannot be
read or written the call stays blocked: a release is never assumed.
"""
import hashlib
import os
import re
import shlex
import sys
from pathlib import Path

import ma_active
import ma_data
import ma_host
import ma_logline
import ma_schema

Q_MAX = 200
KEY = re.compile(r'^[0-9a-f]{16}$')
RESULTS = ('allowed', 'denied')
PLUGIN = Path(__file__).resolve().parents[2]


def tool_and_target(call):
    """(tool, target) of a Call: `apply_patch` with the target paths in patch order (no repeats), else the tool name
    with the Bash command (or the path or input of another tool)."""
    first = call.inps[0] if call.inps else {}
    if call.file_change:
        paths = []
        for inp in call.inps:
            p = (inp.get('tool_input') or {}).get('file_path')
            if isinstance(p, str) and p not in paths:
                paths.append(p)
        return ma_host.FILE_TOOL, ', '.join(paths)
    tool = first.get('tool_name') or '-'
    ti = first.get('tool_input') if isinstance(first.get('tool_input'), dict) else {}
    for name in ('command', 'file_path', 'notebook_path'):
        if isinstance(ti.get(name), str):
            return tool, ti[name]
    return tool, str(ti)


def match_key(tool: str, target: str) -> str:
    return hashlib.sha256(f'{tool}\n{target}'.encode('utf-8')).hexdigest()[:16]


def one_line(target: str) -> str:
    text = ' '.join(target.splitlines())
    return text if len(text) <= Q_MAX else text[:Q_MAX - 1] + '…'


def read_log(log: Path) -> list:
    """[(stamp, kind, fields)] of the readable lines; [] when there is no log yet; OSError for any other failure."""
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except FileNotFoundError:
        return []
    return [p for p in map(ma_schema.split_line, text.splitlines()) if p]


def unusable(f: dict, newest):
    """Why an L1 answer cannot be used (None when it can); `newest` is the newest open ask or None."""
    if not f.get('key'):
        return 'it has no key='
    if not KEY.match(f['key']):
        return 'its key is not 16 hex digits'
    if not f.get('tool'):
        return 'it has no tool='
    if f.get('result') not in RESULTS:
        return f'its result is {f.get("result") or "-"}'
    if newest is None:
        return 'there is no open ask'
    if (newest.get('tool'), newest.get('key')) != (f['tool'], f['key']):
        return f'it answers {f["tool"]} {f["key"]}, but the newest open ask is {newest.get("tool")} {newest.get("key")}'
    return None


def scan(lines) -> tuple:
    """(grants, note): the grants not used up by every hook of theirs, and the sentence for the newest L1 answer line
    after the newest open ask when it was not usable (else '')."""
    open_asks, grants, note = [], [], ''
    for stamp, kind, f in lines:
        if f.get('gate') != 'G2':
            continue
        if kind == 'ask' and f.get('key'):
            open_asks.append(f)
            note = ''
        elif kind == 'answer' and 'id' not in f:   # permission-log's answers carry an id; L1's Codex answer has none
            why = unusable(f, open_asks[-1] if open_asks else None)
            if why:
                note = f'The G2 answer line of {stamp[11:]} was not used: {why}.' if open_asks else ''
                continue
            note = ''
            same = [a for a in open_asks if (a.get('tool'), a.get('key')) == (f['tool'], f['key'])]
            open_asks = [a for a in open_asks if a not in same]
            if f['result'] == 'allowed':
                grants.append({'tool': f['tool'], 'key': f['key'], 'hooks': {a.get('hook') for a in same}, 'used': set()})
        elif kind == 'release':
            for g in grants:
                if (g['tool'], g['key']) == (f.get('tool'), f.get('key')) and f.get('hook') in g['hooks'] - g['used']:
                    g['used'].add(f['hook'])
                    break
    return grants, note


def grant_for(grants, tool: str, key: str, hook: str):
    return next((g for g in grants if (g['tool'], g['key']) == (tool, key) and hook in g['hooks'] - g['used']), None)


def reason_text(why: str, hook: str, tool: str, q: str, key: str, cwd: str, note: str) -> str:
    """The hook's stderr text (Mock-up Part 5)."""
    script = ma_host.plugin_root(PLUGIN) / 'l4-tools-guards' / 'scripts' / 'run-log.py'
    command = (f'python3 "{script}" answer gate=G2 tool={tool} q={shlex.quote(q)} key={key} result=allowed '
               f'--cwd "{cwd}" --data-dir "{ma_data.data_dir()}" --task-dir "{ma_data.task_dir()}"')
    text = (f'my-agent G2 ({hook}): {why.rstrip(".")}. Codex shows no permission dialog: ask the person in a G2 popup '
            f'(Allow once / Deny) that names the tool {tool} and the target {q}. Then record the answer with {command} '
            f'(result=denied for Deny), and after Allow once retry the same call unchanged.')
    return f'{text} {note}' if note else text


def codex_ask(call, out: dict, hook: str) -> int:
    """The Codex form of a gate hook's ask: 0 (silent) for a released call, else 2 with the G2 reason on stderr."""
    why = out['hookSpecificOutput'].get('permissionDecisionReason') or 'blocked'
    tool, target = tool_and_target(call)
    key, q = match_key(tool, target), one_line(target)
    inp = call.inps[0] if call.inps else {}
    cwd = inp.get('cwd') or os.getcwd()
    sid = inp.get('session_id')
    session = [('session', sid)] if isinstance(sid, str) and sid else []
    active = ma_active.find_active(cwd, ma_active.default_tasks_dir().expanduser().resolve())
    if active is None:
        print(f'my-agent G2 ({hook}): {why.rstrip(".")}. No active task was found, so the call stays blocked.',
              file=sys.stderr)
        return 2
    try:
        grants, note = scan(read_log(active.log))
        if grant_for(grants, tool, key, hook):
            ma_logline.append(active.log, ma_logline.format_line('release', [
                ('gate', 'G2'), ('hook', hook), ('tool', tool), ('key', key)] + session))
            return 0
        ma_logline.append(active.log, ma_logline.format_line('ask', [
            ('gate', 'G2'), ('agent', 'main'), ('id', None), ('tool', tool), ('q', q), ('key', key), ('hook', hook)]
            + session))
    except OSError as exc:
        print(f'my-agent G2 ({hook}): {why.rstrip(".")}. The call stays blocked: the run-log {active.log} cannot be '
              f'read or written ({type(exc).__name__}: {exc}).', file=sys.stderr)
        return 2
    print(reason_text(why, hook, tool, q, key, str(cwd), note), file=sys.stderr)
    return 2

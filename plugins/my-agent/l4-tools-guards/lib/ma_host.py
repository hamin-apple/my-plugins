"""Host adapter: the one place where Codex differs from Claude Code for the gate hooks (scope-guard,
plan-approved-check, verdict-fresh-check).

`parse(raw)` reads a hook input and returns a `Call`: the host (`claude` or `codex`) and the Claude-shaped inputs the
scripts already judge. Claude input passes through unchanged (one input, the parsed object as it is). Codex input is
turned into the same shape:

- `Bash` stays `Bash` (one `command` string).
- The file-change tool `apply_patch` (input `{"command": "<patch text>"}`) becomes one `Write` (Add File) or `Edit`
  (Update, Delete, Move to) input per target path; an `Update File` hunk carries `old_string`/`new_string` so the
  architect's plan.md checks see what the hunk changes. The caller denies the call if any of them is denied. A patch
  whose targets cannot be read raises.
- The spawn tool `collaborationspawn_agent` becomes `Agent` with `subagent_type` from its `agent_type`.
- Codex agent names `my-agent-<role>` (the installed agent files of `codex/agents/`) map to `my-agent:<role>` in
  `agent_type` and in `subagent_type`. The identity of a subagent call is its own `agent_id`/`agent_type` (identity findings: Outcome I).

A Codex input with a missing or differently shaped field raises, so the scripts' fail-closed path runs (exit 2).
`emit()` writes the decision in the host's form: JSON on stdout as in Claude, except for a deny on the Codex
file-change tool, where Codex ignored the deny JSON and honored exit 2 (identity findings: `file-deny=exit2`), so the
reason goes to stderr with exit 2; and an ask on Codex (any tool), which Codex ignores: `ma_g2.codex_ask` makes it exit 2
and lets one G2 answer line release one call. Only the two hooks that emit `ask` reach it (scope-guard only denies). `scratch_base()` is the scratchpad base of the host.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

import ma_schema

CLAUDE_PREFIX = 'my-agent:'
CODEX_PREFIX = 'my-agent-'
FILE_TOOL = 'apply_patch'
SPAWN_TOOL = 'collaborationspawn_agent'
CODEX_TOOLS = (FILE_TOOL, SPAWN_TOOL)

_HEADER = re.compile(r'^\*\*\* (Add|Update|Delete) File: (.+)$')
_MOVE = re.compile(r'^\*\*\* Move to: (.+)$')
_RANK = {'deny': 3, 'ask': 2}


class Call(NamedTuple):
    host: str            # 'claude' or 'codex'
    inps: list           # Claude-shaped inputs to judge (more than one only for a multi-file patch)
    file_change: bool    # the Codex file-change tool (its deny is exit 2)


def claude_agent(name: str) -> str:
    """`my-agent-plan-reviewer` -> `my-agent:plan-reviewer`; any other name unchanged."""
    if isinstance(name, str) and name.startswith(CODEX_PREFIX) and len(name) > len(CODEX_PREFIX):
        return CLAUDE_PREFIX + name[len(CODEX_PREFIX):]
    return name


def codex_agent(name: str) -> str:
    """`my-agent:plan-reviewer` -> `my-agent-plan-reviewer`; any other name unchanged."""
    if isinstance(name, str) and name.startswith(CLAUDE_PREFIX):
        return CODEX_PREFIX + name[len(CLAUDE_PREFIX):]
    return name


def is_codex(inp) -> bool:
    if not isinstance(inp, dict):
        return False
    agent = inp.get('agent_type')
    return inp.get('tool_name') in CODEX_TOOLS or (isinstance(agent, str) and agent.startswith(CODEX_PREFIX))


def patch_calls(text: str) -> list:
    """Claude-shaped (tool, tool_input) pairs of a Codex patch; raises when it names no target."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '*** Begin Patch':
        raise ValueError('patch does not start with *** Begin Patch')
    out = []
    i = 1
    while i < len(lines):
        m = _HEADER.match(lines[i])
        i += 1
        if not m:
            continue
        kind, path = m.group(1), m.group(2).strip()
        moved = _MOVE.match(lines[i]) if kind == 'Update' and i < len(lines) else None
        if moved:
            i += 1
            if not moved.group(1).strip():
                raise ValueError('patch names an empty path')
            out.append(('Edit', {'file_path': moved.group(1).strip()}))
        body = []
        while i < len(lines) and (not lines[i].startswith('*** ') or lines[i].startswith('*** End of File')):
            body.append(lines[i])
            i += 1
        if not path:
            raise ValueError('patch names an empty path')
        if kind == 'Add':
            out.append(('Write', {'file_path': path, 'content': '\n'.join(b[1:] for b in body if b.startswith('+'))}))
            continue
        hunks, cur = [], None
        for b in body:
            if b.startswith('@@'):
                cur = None
                continue
            if b.startswith('*** End of File') or b == '':
                continue
            if cur is None:
                cur = ([], [])
                hunks.append(cur)
            if b[0] in ' -':
                cur[0].append(b[1:])
            if b[0] in ' +':
                cur[1].append(b[1:])
        if kind == 'Delete' or not hunks:
            out.append(('Edit', {'file_path': path}))
        for old, new in hunks:
            out.append(('Edit', {'file_path': path, 'old_string': '\n'.join(old), 'new_string': '\n'.join(new)}))
    if not out:
        raise ValueError('patch names no target path')
    return out


def _spawn_models(ti: dict) -> dict:
    """`model` and `effort` of the Claude-shaped Agent input, from the spawn input's `model` and `reasoning_effort`
    (only those given as text)."""
    return {k: ti[src] for k, src in (('model', 'model'), ('effort', 'reasoning_effort'))
            if isinstance(ti.get(src), str) and ti[src]}


def _adapt(inp: dict) -> Call:
    ti = inp.get('tool_input')
    tool = inp.get('tool_name')
    if not isinstance(tool, str) or not isinstance(ti, dict):
        raise ValueError('Codex hook input has no tool_name or tool_input object')
    base = dict(inp, _host='codex')
    if isinstance(inp.get('agent_type'), str):
        base['agent_type'] = claude_agent(inp['agent_type'])
    if tool == FILE_TOOL:
        patch = ti.get('command')
        if not isinstance(patch, str):
            raise ValueError('apply_patch input has no command text')
        return Call('codex', [dict(base, tool_name=t, tool_input=i) for t, i in patch_calls(patch)], True)
    if tool == SPAWN_TOOL:
        agent, message = ti.get('agent_type'), ti.get('message', '')
        if not isinstance(agent, str) or not agent or not isinstance(message, str):
            raise ValueError('spawn input has no agent_type text')
        return Call('codex', [dict(base, tool_name='Agent',
                                   tool_input=dict({'subagent_type': claude_agent(agent), 'prompt': message,
                                                    'description': ti.get('task_name', '')},
                                                   **_spawn_models(ti)))], False)
    if tool == 'Bash' and not isinstance(ti.get('command'), str):
        raise ValueError('Bash input has no command text')
    return Call('codex', [dict(base, tool_input=ti)], False)


def parse(raw: str) -> Call:
    """Hook input text -> Call. Invalid JSON raises; a Claude input (or any non-Codex object) passes unchanged."""
    inp = json.loads(raw)
    if hook_host(inp) == 'codex':
        mark_hook(inp)
    if not is_codex(inp):
        return Call('claude', [inp], False)
    return _adapt(inp)


def decision(out: Optional[dict]) -> Optional[str]:
    """'deny' or 'ask' of a hook output dict, else None."""
    h = out.get('hookSpecificOutput') if isinstance(out, dict) else None
    d = h.get('permissionDecision') if isinstance(h, dict) else None
    return d if d in _RANK else None


def stronger(a: Optional[dict], b: Optional[dict]) -> Optional[dict]:
    """The output that wins between two: deny, then ask, then any other output; the first one on a tie."""
    def rank(o):
        return _RANK.get(decision(o), 1 if o else 0)
    return b if rank(b) > rank(a) else a


def emit(call: Call, out: Optional[dict]) -> int:
    """Write the decision in the host's form; returns the exit code. A Codex ask is exit 2 and one G2 answer releases
    one call (`ma_g2`); a Codex main-session Bash input is not reshaped, so its host comes from `hook_host`."""
    if not out:
        return 0
    if decision(out) == 'ask' and (call.host == 'codex' or (call.inps and hook_host(call.inps[0]) == 'codex')):
        import ma_g2
        return ma_g2.codex_ask(call, out, Path(sys.argv[0]).stem)
    if call.file_change and decision(out):
        print(out['hookSpecificOutput'].get('permissionDecisionReason') or 'blocked', file=sys.stderr)
        return 2
    print(json.dumps(out, ensure_ascii=False))
    return 0


def scratch_base(inp=None) -> Path:
    """Scratchpad base: `<base>/<project slug>/<session_id>/scratchpad`. Claude Code keeps it under
    /tmp/claude-<uid>; for Codex it is `my-agent-codex` in the OS temp folder."""
    if isinstance(inp, dict) and inp.get('_host') == 'codex':
        return Path(tempfile.gettempdir()).resolve() / 'my-agent-codex'
    return Path('/tmp').resolve() / f'claude-{os.getuid()}'


# --- session records (Codex) and the expected main model per host ---

def codex_sessions() -> Path:
    """Root of the Codex session records, `<root>/YYYY/MM/DD/rollout-*.jsonl` ($MA_CODEX_SESSIONS, else
    ~/.codex/sessions). Claude's records are found by `ma_subagent.claude_projects()`."""
    return Path(os.environ.get('MA_CODEX_SESSIONS') or Path.home() / '.codex/sessions')


def _safe_id(session) -> bool:
    return isinstance(session, str) and bool(session) and not re.search(r'[/\\\0*?\[]', session) \
        and session not in ('.', '..')


def _meta(path):
    """The payload of a record's first line when that is a `session_meta`, else None."""
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            first = json.loads(fh.readline())
    except (OSError, ValueError):
        return None
    payload = first.get('payload') if isinstance(first, dict) and first.get('type') == 'session_meta' else None
    return payload if isinstance(payload, dict) else None


def _records() -> list:
    return sorted(codex_sessions().glob('*/*/*/*.jsonl'))


def codex_record(session):
    """Path of the main record of a Codex session (first `session_meta` with `id` = session and no parent), or None.
    The file name usually ends with the id, so those are read first."""
    if not _safe_id(session):
        return None
    files = _records()
    named = [p for p in files if p.name.endswith(f'{session}.jsonl')]
    for path in named + [p for p in files if p not in named]:
        meta = _meta(path)
        if meta and meta.get('id') == session and not meta.get('parent_thread_id'):
            return path
    return None


def _role(meta):
    source = meta.get('source')
    spawn = (source.get('subagent') or {}).get('thread_spawn') if isinstance(source, dict) else None
    role = spawn.get('agent_role') if isinstance(spawn, dict) else None
    return role if isinstance(role, str) and role else None


def codex_subagents(session) -> list:
    """[(thread id, record path, agent_role or None)] of the subagents of a Codex session: threads whose
    `session_meta` has `parent_thread_id` = session, in a record of their own or inline in the main record."""
    main = codex_record(session)
    if main is None:
        return []
    out, seen = [], set()

    def take(meta, path):
        tid = meta.get('id')
        if meta.get('parent_thread_id') == session and isinstance(tid, str) and tid != session and tid not in seen:
            seen.add(tid)
            out.append((tid, path, _role(meta)))

    root = codex_sessions()
    for path in _records():
        if path != main and path.relative_to(root) >= main.relative_to(root):   # a child starts after its parent
            meta = _meta(path)
            if meta:
                take(meta, path)
    try:
        with open(main, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if '"session_meta"' in line:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(e, dict) and e.get('type') == 'session_meta' and isinstance(e.get('payload'), dict):
                        take(e['payload'], main)
    except OSError:
        pass
    return out


# --- record hooks and hook health (Codex) ---
# Codex runs a plugin's hooks only after the person trusts them, and a changed hook needs trust again (findings:
# after a stale trust no hook of the plugin fired). Its trusted hash cannot be recomputed, so every my-agent hook
# marks a Codex run in the OS temp folder and `hook_health()` (data-dir.py, run at Intake) looks for the marks.

# PreToolUse hooks that run on the Intake call. scope-guard is not listed: it returns before `parse` for an input that
# names no my-agent agent, so it leaves no mark on a main-session call.
GATE_HOOKS = ('plan-approved-check', 'verdict-fresh-check')
NOTICE_HOOK = 'session-notice'                                                # SessionStart: once per session
FRESH_SECS = 120
_CLAUDE_ENV = ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_PROJECT_DIR', 'CLAUDE_CODE_SESSION_ID')


def hook_host(inp) -> str:
    """`codex` or `claude` for a hook input: $MA_HOST (tests), a Codex-shaped input (tool or agent name, `turn_id`),
    else Codex when the plugin root is set and no Claude Code variable is (SessionStart carries no marker)."""
    forced = os.environ.get('MA_HOST')
    if forced in ('claude', 'codex'):
        return forced
    if is_codex(inp) or (isinstance(inp, dict) and isinstance(inp.get('turn_id'), str)):
        return 'codex'
    if os.environ.get('CLAUDE_PLUGIN_ROOT') and not any(os.environ.get(k) for k in _CLAUDE_ENV):
        return 'codex'
    return 'claude'


def _marks_root() -> Path:
    return Path(tempfile.gettempdir()).resolve() / 'my-agent-codex' / 'marks'


def mark_hook(inp) -> None:
    """Record that this hook (the running script's name) ran for the input's session. Never raises."""
    try:
        session = inp.get('session_id') if isinstance(inp, dict) else None
        if not _safe_id(session):
            return
        d = _marks_root() / session
        d.mkdir(parents=True, exist_ok=True)
        (d / Path(sys.argv[0]).stem).write_text('ran\n', encoding='utf-8')
    except (OSError, IndexError):
        pass


def hook_health(session=None, now=None) -> list:
    """[(hook, 'missing'|'stale')] of the hooks that should have run for the session: the PreToolUse gate
    hooks within FRESH_SECS (they ran for the call that runs this check) and, with a known session, the session
    notice (any age). Without a session id the newest mark of any session counts."""
    import time
    now = time.time() if now is None else now
    root, out = _marks_root(), []

    def newest(hook):
        dirs = [root / session] if _safe_id(session) else (list(root.iterdir()) if root.is_dir() else [])
        times = []
        for d in dirs:
            try:
                times.append((d / hook).stat().st_mtime)
            except OSError:
                pass
        return max(times) if times else None

    for hook in GATE_HOOKS:
        t = newest(hook)
        if t is None:
            out.append((hook, 'missing'))
        elif now - t > FRESH_SECS:
            out.append((hook, 'stale'))
    if _safe_id(session) and newest(NOTICE_HOOK) is None:
        out.append((NOTICE_HOOK, 'missing'))
    return out


def health_message(problems) -> str:
    names = ', '.join(f'{h} ({why})' for h, why in problems)
    return (f'my-agent hooks did not run in this Codex session: {names}. Codex runs a plugin\'s hooks only after '
            'they are trusted, and a changed plugin must be trusted again: do the hook trust step in the Codex TUI, '
            'then start a new session. Until then the guards do not protect this session.')


def record_input(inp):
    """Claude-shaped copy of a record hook's input (`call`, `start`, `stop`, `ask`, `answer`, SessionStart). On
    Codex the hook is marked, `my-agent-<role>` becomes `my-agent:<role>` and the spawn tool `collaborationspawn_agent`
    becomes `Agent`; Claude input is returned as it is."""
    if not isinstance(inp, dict) or hook_host(inp) != 'codex':
        return inp
    mark_hook(inp)
    out = dict(inp, _host='codex')
    if isinstance(inp.get('agent_type'), str):
        out['agent_type'] = claude_agent(inp['agent_type'])
    ti = inp.get('tool_input')
    if inp.get('tool_name') == SPAWN_TOOL and isinstance(ti, dict):
        agent = ti.get('agent_type')
        out.update(tool_name='Agent', tool_input={
            'subagent_type': claude_agent(agent) if isinstance(agent, str) else '',
            'prompt': ti.get('message') if isinstance(ti.get('message'), str) else '',
            'description': ti.get('task_name', ''), **_spawn_models(ti)})
    return out


# --- session id, plugin root and plugin settings per host ---

def env_host() -> str:
    """`codex` or `claude` for a script run from the model's shell: $MA_HOST (tests), else Codex when its thread
    variable is set and Claude's session variable is not."""
    forced = os.environ.get('MA_HOST')
    if forced in ('claude', 'codex'):
        return forced
    if os.environ.get('CLAUDE_CODE_SESSION_ID') or os.environ.get('CLAUDECODE'):
        return 'claude'
    return 'codex' if os.environ.get('CODEX_THREAD_ID') else 'claude'


def session_id() -> Optional[str]:
    """The session id from the environment: $CLAUDE_CODE_SESSION_ID, else Codex's $CODEX_THREAD_ID (the findings
    do not list a Codex shell variable; the thread id is the session id of the Codex record), else None."""
    return os.environ.get('CLAUDE_CODE_SESSION_ID') or os.environ.get('CODEX_THREAD_ID') or None


def plugin_root(default) -> Path:
    """$CLAUDE_PLUGIN_ROOT (Codex sets it too, findings "Env and plugin root"), else `default`."""
    return Path(os.environ.get('CLAUDE_PLUGIN_ROOT') or default)


def plugin_option(env_name: str) -> Optional[str]:
    """A plugin setting from its environment variable. Codex's option variables are open in the findings, so the
    Claude names are read on both hosts; an unexpanded `${user_config.…}` literal is dropped by the caller."""
    return os.environ.get(env_name)


def main_family(model) -> str:
    """The model the main session is expected to run, by the host its model id belongs to: `opus` for Claude,
    the Codex default for a Codex id (D4: no per-role mapping)."""
    return ma_schema.CODEX_DEFAULT if ma_schema.codex_family(model) else 'opus'


def main_mismatch(model) -> bool:
    """True when `model` is not the expected main model of its host."""
    codex = ma_schema.codex_family(model)
    return codex != ma_schema.CODEX_DEFAULT if codex else ma_schema.family(model) != 'opus'

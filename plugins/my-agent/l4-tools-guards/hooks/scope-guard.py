#!/usr/bin/env python3
"""Plugin hook (PreToolUse, every tool): read/write scope of my-agent:* agents
(architecture 4.5 "read and write path limits", 4.12 "limiting read paths too").

Runs in every session with the plugin on (F18), so anything whose input has no `my-agent:` agent_type exits 0 before
the JSON is even parsed. For a my-agent agent: secrets are denied for everyone, reads must stay in the agent's read
roots, writes in its write roots. The rules start from the agent's level (ma_schema.AGENTS): an L2 agent reads the
task location, writes only its own file and its Bash only reads; an L3 agent reads the location and writes nothing.
Roles then widen or narrow that: the verifier and researcher may use the web, the researcher and writer read the
task folder and write `work/` (writer also `prototype/` and the plan's reference files), the coder writes the
location or its worktree but not `docs/agent/`, `.git/` or `.claude/` (hooks and settings run in L1's context), and
the gate-analyst reads only gate-tally.md and gate-report.md. The architect may not add the `Approved` or
`Prototype: requested` line L1 writes into plan.md (4.4 G1b) nor drop a `## Revisions` line (4.8.1).
Paths compare without case (ma_path). Any error → exit 2, so the call is blocked
(`onFailure: block` covers a crash or timeout).
"""
import fnmatch
import json
import os
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_bash  # noqa: E402
import ma_plan  # noqa: E402
import ma_schema  # noqa: E402
from ma_path import same, under  # noqa: E402

HOME = Path.home()
SECRET_DIRS = [HOME / '.ssh', HOME / '.aws', HOME / '.config' / 'gh']
SECRET_FILES = [HOME / '.netrc']
OWN_FILE = {'architect': 'plan.md', 'plan-reviewer': 'plan-review.md', 'verifier': 'verify.md',
            'reviewer': 'review.md', 'gate-analyst': 'gate-report.md'}   # the one file each L2 agent writes
WRITE_TOOLS = {'Edit', 'Write', 'NotebookEdit'}
GLOB_CHARS = re.compile(r'[*?\[]')
SECRET_NAMES = ['.env', '.env.local', 'server.pem', 'id.key']


class Rules(NamedTuple):
    read: List[Path]
    write: List[Path]
    deny_write: List[Path]
    bash_writes: bool      # False: Bash must not write anything (read-only judges, explorer)
    web: bool


def secret(p: Path) -> bool:
    name = p.name.casefold()
    return (name == '.env' or name.startswith('.env.') or name.endswith(('.pem', '.key'))
            or any(same(p, f) for f in SECRET_FILES) or any(under(p, d) for d in SECRET_DIRS))


def secret_glob(glob: str) -> bool:
    """A Grep `glob` that selects secret files by name (`.env`, `*.pem`); a bare `*` is not one."""
    g = glob.casefold().rsplit('/', 1)[-1]
    return g.strip('*') != '' and any(fnmatch.fnmatchcase(n, g) for n in SECRET_NAMES)


def resolve(raw: str, cwd: Path) -> Path:
    p = Path(os.path.expanduser(raw))
    return (p if p.is_absolute() else cwd / p).resolve()


def reference_files(plan_md: Path, location: Path) -> List[Path]:
    """Paths listed under `## Reference files` in plan.md (one per `-` line, backticks optional)."""
    out = []
    for line in ma_schema.section_lines(ma_plan.read(plan_md), 'Reference files') or []:
        item = re.match(r'\s*[-*]\s+(.+)', line)
        if item:
            tick = re.search(r'`([^`]+)`', item.group(1))
            out.append(resolve((tick.group(1) if tick else item.group(1)).strip(), location))
    return out


def worktree(cwd: Path, location: Path) -> Optional[Path]:
    root = ma_active.git_root(cwd)
    if root is not None and (root / '.git').is_file() and ma_active.main_worktree(root) == location:
        return root
    return None


def level_rules(level: str, role: str, active) -> Rules:
    L, T = active.location, active.task_dir
    if level == 'L2':
        return Rules([L], [T / OWN_FILE[role]], [], False, False)
    return Rules([L], [], [], False, False)   # L3


def rules(role: str, active, cwd: Path) -> Optional[Rules]:
    level = ma_schema.AGENTS.get(role)
    if level is None:
        return None
    r = level_rules(level, role, active)
    L, T = active.location, active.task_dir
    if role == 'gate-analyst':
        return r._replace(read=[T / 'gate-tally.md', T / 'gate-report.md'])
    if role == 'verifier':
        return r._replace(web=True)
    if role == 'researcher':
        return r._replace(read=[T], write=[T / 'work'], web=True)
    if role == 'writer':
        return r._replace(read=[T] + reference_files(T / 'plan.md', L), write=[T / 'work', T / 'prototype'])
    if role == 'coder':
        W = worktree(cwd, L)
        own = W or L
        return r._replace(write=[own], bash_writes=True,
                          deny_write=[L / 'docs' / 'agent', L / '.git', L / '.claude', own / 'docs' / 'agent',
                                      own / '.git'] if W is None else [own / 'docs' / 'agent', own / '.git'])
    return r


def glob_base(pattern: str, base: Path) -> Path:
    parts = []
    for part in Path(os.path.expanduser(pattern)).parts:
        if GLOB_CHARS.search(part):
            break
        parts.append(part)
    return resolve(str(Path(*parts)) if parts else '.', base)


def paths_of(tool: str, ti: dict, cwd: Path):
    """(read paths, write paths) the call touches; write None = Bash writes somewhere it cannot name."""
    if tool == 'Read':
        return [resolve(ti['file_path'], cwd)], []
    if tool in WRITE_TOOLS:
        return [], [resolve(ti.get('file_path') or ti['notebook_path'], cwd)]
    if tool == 'Grep':
        return [resolve(ti.get('path') or '.', cwd)], []  # the glob is checked in check()
    if tool == 'Glob':
        base = resolve(ti.get('path') or '.', cwd)
        return [base, glob_base(ti.get('pattern') or '', base)], []
    if tool == 'Bash':
        cmd = ti['command']
        writes = ma_bash.write_targets(cmd, cwd)
        if writes is not None and ma_bash.git_mutates(cmd):
            writes = None
        return ma_bash.read_paths(cmd, cwd), writes
    return [], []


def check(inp: dict, role: str, active) -> Optional[str]:
    """Deny reason, or None to let the call through."""
    tool, ti = inp.get('tool_name'), inp['tool_input']
    if not isinstance(ti, dict):
        raise TypeError('tool_input is not an object')
    cwd = Path(inp.get('cwd') or os.getcwd()).resolve()
    r = rules(role, active, cwd)
    if r is None:
        return f'Not a defined my-agent agent: {role}'
    if tool in ('WebFetch', 'WebSearch'):
        return None if r.web else f'{role} does not use the web.'
    if tool == 'Bash':
        dumped = ma_bash.env_reads(ti['command'])
        if dumped:
            return f'my-agent scope-guard: {role} may not read the environment ({dumped[0]})'
    reads, writes = paths_of(tool, ti, cwd)
    if reads is None:
        return 'Cannot tell what this command reads (a path built from a variable, command substitution, cd to a variable, etc.).'
    if tool == 'Grep' and secret_glob(ti.get('glob') or ''):
        return f'This glob selects secret files: {ti.get("glob")}'
    for p in reads + (writes or []):
        if secret(p):
            return f'Secret paths are not read or written: {p}'
    for p in reads:
        if not any(under(p, root) for root in r.read):
            return f'Outside the read scope of {role}: {p}'
    if tool == 'Bash' and role == 'verifier' and ma_bash.http_sends(ti['command']) is not False:
        return 'The verifier\'s curl and wget only fetch (GET) (this option sends data).'
    if tool == 'Bash' and not r.bash_writes and writes != []:
        return f'Bash for {role} only reads and checks (this command changes files or git state).'
    if writes is None:
        return 'Cannot tell where this command writes (a git change, a variable path, etc.).'
    for p in writes:
        if not any(under(p, root) for root in r.write) or any(under(p, d) for d in r.deny_write):
            return f'Outside the write scope of {role}: {p}'
    if role == 'architect' and tool in WRITE_TOOLS:
        return plan_write_problem(ti, writes[0])
    return None


def plan_write_problem(ti: dict, path: Path) -> Optional[str]:
    """Deny reason when the architect's write would add L1's `Approved` or `Prototype: requested` line, or drop or
    change a `## Revisions` line (the rewrite must carry that section over as it is, 4.8.1)."""
    before = ma_plan.read(path)
    if 'content' in ti:
        after = ti['content']
    else:
        old, new = ti.get('old_string', ''), ti.get('new_string', '')
        after = before.replace(old, new) if ti.get('replace_all') else before.replace(old, new, 1)
    for has, what in ((ma_plan.approved_text, 'approval line'), (ma_plan.prototype_text, '`Prototype: requested` line')):
        if has(after) and not has(before):
            return f'Only L1 writes the {what} of plan.md (G1b).'
    kept = {line.rstrip() for line in ma_schema.section_lines(after, 'Revisions') or []}
    if any(line.strip() and line.rstrip() not in kept for line in ma_schema.section_lines(before, 'Revisions') or []):
        return 'Do not delete or change the `## Revisions` lines of plan.md. Copy that section as is when you rewrite (4.8.1).'
    return None


def main() -> int:
    raw = sys.stdin.read()
    if 'my-agent:' not in raw:
        return 0
    try:
        inp = json.loads(raw)
        agent = inp.get('agent_type') if isinstance(inp, dict) else None
        if not isinstance(agent, str) or not agent.startswith('my-agent:'):
            return 0
        role = agent.split(':', 1)[1]
        broken = []
        active = ma_active.find_active(inp.get('cwd') or os.getcwd(), broken=broken)
        missing = (f'{broken[0]} has no `task:` line.' if broken else
                   'No active my-agent task (no .active).')
        why = missing if active is None else check(inp, role, active)
        if why:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                     'permissionDecisionReason': why if why.startswith('my-agent scope-guard:') else f'scope-guard: {why}'}},
                             ensure_ascii=False))
        return 0
    except Exception as e:   # block the call: exit 2 is a blocking error for PreToolUse
        print(f'scope-guard: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

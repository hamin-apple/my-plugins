#!/usr/bin/env python3
"""Plugin hook (PreToolUse, every tool): read/write scope of my-agent:* agents
(architecture 4.5 "읽기·쓰기 경로 제한", 4.12 "읽기 경로도 제한하기").

Runs in every session with the plugin on (F18), so anything whose input has no `my-agent:` agent_type exits 0 before
the JSON is even parsed. For a my-agent agent: secrets are denied for everyone, reads must stay in the agent's read
roots, writes in its write roots, judges' and explorer's Bash must not write, and only researcher and verifier may
use the web. The architect may not add the `Approved` or `Prototype: requested` line L1 writes into plan.md (4.4 G1b),
and the coder may not write `.git/` or `.claude/` (hooks and settings run in L1's context). Paths compare without
case (ma_path). Any error → exit 2, so the call is blocked (`onFailure: block` covers a crash or timeout).
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
from ma_path import same, under  # noqa: E402

HOME = Path.home()
SECRET_DIRS = [HOME / '.ssh', HOME / '.aws', HOME / '.config' / 'gh']
SECRET_FILES = [HOME / '.netrc']
JUDGE_FILE = {'architect': 'plan.md', 'plan-reviewer': 'plan-review.md', 'verifier': 'verify.md',
              'reviewer': 'review.md'}
READ_ONLY_BASH = {'verifier', 'reviewer', 'explorer'}
WEB = {'researcher', 'verifier'}
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
    """Paths listed under `## 참고 파일` in plan.md (one per `-` line, backticks optional)."""
    try:
        text = plan_md.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []
    m = re.search(r'(?m)^## 참고 파일\s*$', text)
    if not m:
        return []
    out = []
    for line in text[m.end():].splitlines():
        if line.startswith('## '):
            break
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


def rules(role: str, active, cwd: Path) -> Optional[Rules]:
    L, T = active.location, active.task_dir
    if role in JUDGE_FILE:
        return Rules([L], [T / JUDGE_FILE[role]], [], role not in READ_ONLY_BASH, role in WEB)
    if role == 'explorer':
        return Rules([L], [], [], False, False)
    if role == 'researcher':
        return Rules([T], [T / 'work'], [], False, True)
    if role == 'writer':
        return Rules([T] + reference_files(T / 'plan.md', L), [T / 'work', T / 'prototype'], [], False, False)
    if role == 'coder':
        W = worktree(cwd, L)
        own = W or L
        return Rules([L], [own], [L / 'docs' / 'agent', L / '.git', L / '.claude', own / 'docs' / 'agent',
                                  own / '.git'] if W is None else [own / 'docs' / 'agent', own / '.git'], True, False)
    return None


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
        return f'정의되지 않은 my-agent 에이전트입니다: {role}'
    if tool in ('WebFetch', 'WebSearch'):
        return None if r.web else f'{role}는 웹을 쓰지 않습니다.'
    reads, writes = paths_of(tool, ti, cwd)
    if reads is None:
        return '어디를 읽는지 알 수 없는 명령입니다 (변수로 만든 경로, 명령 치환, 변수로 간 cd 등).'
    if tool == 'Grep' and secret_glob(ti.get('glob') or ''):
        return f'비밀값 파일을 고르는 glob입니다: {ti.get("glob")}'
    for p in reads + (writes or []):
        if secret(p):
            return f'비밀값 경로는 읽거나 쓰지 않습니다: {p}'
    for p in reads:
        if not any(under(p, root) for root in r.read):
            return f'{role}의 읽기 범위 밖입니다: {p}'
    if tool == 'Bash' and role == 'verifier' and ma_bash.http_sends(ti['command']) is not False:
        return 'verifier의 curl·wget은 받기(GET)만 합니다 (데이터를 보내는 옵션).'
    if tool == 'Bash' and not r.bash_writes and writes != []:
        return f'{role}의 Bash는 읽기·확인만 합니다 (파일이나 git 상태를 바꾸는 명령).'
    if writes is None:
        return '어디에 쓰는지 알 수 없는 명령입니다 (git 변경, 변수 경로 등).'
    for p in writes:
        if not any(under(p, root) for root in r.write) or any(under(p, d) for d in r.deny_write):
            return f'{role}의 쓰기 범위 밖입니다: {p}'
    if role == 'architect' and tool in WRITE_TOOLS:
        return marker_added(ti, writes[0])
    return None


def marker_added(ti: dict, path: Path) -> Optional[str]:
    """Deny reason when the architect's write would add L1's `Approved` or `Prototype: requested` line."""
    before = ma_plan.read(path)
    if 'content' in ti:
        after = ti['content']
    else:
        old, new = ti.get('old_string', ''), ti.get('new_string', '')
        after = before.replace(old, new) if ti.get('replace_all') else before.replace(old, new, 1)
    for has, what in ((ma_plan.approved_text, '승인 줄'), (ma_plan.prototype_text, '`Prototype: requested` 줄')):
        if has(after) and not has(before):
            return f'plan.md의 {what}은 L1만 씁니다 (G1b).'
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
        active = ma_active.find_active(inp.get('cwd') or os.getcwd())
        why = '진행 중인 my-agent 작업이 없습니다 (.active 없음).' if active is None else check(inp, role, active)
        if why:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                     'permissionDecisionReason': f'scope-guard: {why}'}},
                             ensure_ascii=False))
        return 0
    except Exception as e:   # block the call: exit 2 is a blocking error for PreToolUse
        print(f'scope-guard: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

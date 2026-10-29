#!/usr/bin/env python3
"""Plugin hook (hooks.json, PreToolUse: Bash|Edit|Write|NotebookEdit): commit or deliver only on fresh verdicts
(architecture 4.4 G3, P11).

Runs in every session where the plugin is on, so it first narrows down: a call from inside a subagent (`agent_id` in
the input) passes; no task found passes (a `.active` without `task:` warns, before the session check); a `.active`
whose `session:` differs from the input `session_id` (both set) passes.

Applies while a task is active, to a `git commit` and to the G3 deliver: any write into the task folder's
`deliverable/` (the default save place, accept.md), and a Bash cp, mv or rsync from the task folder to a place outside
`<location>/docs/agent/` (other copy forms and plain reads do not count). It needs `verify.md` starting
`Verdict: ALL PASS` and `review.md` starting
`BLOCKER 0`, both no older than the newest changed file: git changes outside `docs/agent/`, plus the task folder's
`work/` (and `deliverable/` when the deliver leaves the task folder; a copy into `deliverable/` does not count the
copies made just before it). A `verify.md` older than a change is accepted when `review.md` is newer than every change
and has `## Applied after review`. No `.active`, or another command → exit 0 at once (a `.active` without `task:`
prints a warning, C9). Any error → exit 2 (blocked).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402
import ma_bash  # noqa: E402
import ma_schema  # noqa: E402
from ma_path import under  # noqa: E402

REASON = 'Task {task}: {why} Before G3, get Verify ALL PASS and Review BLOCKER 0 again as the latest results.'
UNPARSED = ('Task {task}: the command has a substitution such as `$(` or backticks, so it cannot tell whether this is a git commit. '
            'If it is not a commit, split the command and run it again without substitution. If it is a commit, get Verify ALL PASS and '
            'Review BLOCKER 0 as the latest results before G3.')


def first_line(path: Path) -> str:
    try:
        with path.open(encoding='utf-8') as f:
            return f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return ''


def files_in(d: Path):
    return [p for p in d.rglob('*') if p.is_file()] if d.is_dir() else []


def changed_files(active, with_deliverable: bool = True) -> list:
    """Files the verdicts must be newer than (see module docstring)."""
    L, agent = active.location, active.location / 'docs' / 'agent'
    out = files_in(active.task_dir / 'work') + (files_in(active.task_dir / 'deliverable') if with_deliverable else [])
    if (L / '.git').exists():
        r = subprocess.run(['git', '-C', str(L), 'status', '--porcelain', '-uall', '-z'],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise RuntimeError(f'git status failed: {r.stderr.strip()}')
        entries = r.stdout.split('\0')
        i = 0
        while i < len(entries):
            e = entries[i]
            i += 1
            if len(e) < 4:
                continue
            if e[0] in 'RC':
                i += 1          # -z: the rename source follows as its own entry
            p = (L / e[3:]).resolve()
            if not under(p, agent) and p.is_file():
                out.append(p)
    return out


def stale_reason(active, changed: list):
    verify, review = active.task_dir / 'verify.md', active.task_dir / 'review.md'
    if first_line(verify) != ma_schema.VERIFY_PASS:
        return f'The first line of verify.md is not `{ma_schema.VERIFY_PASS}`.'
    if first_line(review) != ma_schema.REVIEW_PASS:
        return f'The first line of review.md is not `{ma_schema.REVIEW_PASS}`.'
    newest = max((p.stat().st_mtime for p in changed), default=0)
    if review.stat().st_mtime < newest:
        return 'A file changed after review.md.'
    if verify.stat().st_mtime < newest:
        try:
            applied = ma_schema.has_section(review.read_text(encoding='utf-8'), ma_schema.APPLIED_AFTER_REVIEW)
        except (OSError, UnicodeDecodeError):
            applied = False
        if not applied:
            return f'A file changed after verify.md (review.md has no `## {ma_schema.APPLIED_AFTER_REVIEW}`).'
    return None


def applies(tool: str, ti: dict, cwd: Path, active):
    """None when the call is neither a commit nor a deliver; else whether `deliverable/` counts as changed."""
    T, agent = active.task_dir, active.location / 'docs' / 'agent'
    deliverable = T / 'deliverable'
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        raw = ti.get('file_path') or ti.get('notebook_path') or ''
        p = Path(os.path.expanduser(raw))
        return False if under((p if p.is_absolute() else cwd / p).resolve(), deliverable) else None
    if tool != 'Bash':
        return None
    cmd = ti.get('command') or ''
    if any(s in ('commit', '?') for s in ma_bash.git_subcommands(cmd)):
        return True
    targets = ma_bash.write_targets(cmd, cwd)
    from_task = any(under(s, T) for s in ma_bash.copy_sources(cmd, cwd))   # cp, mv, rsync sources only
    if targets is None:
        return True if from_task else None
    if from_task and any(not under(t, agent) for t in targets):
        return True
    return False if any(under(t, deliverable) for t in targets) else None


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read())
        if not isinstance(inp, dict):
            raise ValueError('hook input is not an object')
        if ma_active.in_subagent(inp):
            return 0
        broken = []
        active = ma_active.find_active(inp.get('cwd') or os.getcwd(), broken=broken)
        if active is None:
            if broken:
                print(json.dumps({'systemMessage': ma_active.BROKEN.format(path=broken[0])}, ensure_ascii=False))
            return 0
        if not ma_active.owns(active, inp):
            return 0
        cwd = Path(inp.get('cwd') or os.getcwd()).resolve()
        mode = applies(inp.get('tool_name'), inp.get('tool_input') or {}, cwd, active)
        if mode is None:
            return 0
        why = stale_reason(active, changed_files(active, mode))
        if why:
            unparsed = inp.get('tool_name') == 'Bash' and \
                '?' in ma_bash.git_subcommands((inp.get('tool_input') or {}).get('command') or '')
            reason = UNPARSED.format(task=active.task) if unparsed else REASON.format(task=active.task, why=why)
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                     'permissionDecisionReason': reason}},
                             ensure_ascii=False))
        return 0
    except Exception as e:   # block the call: exit 2 is a blocking error for PreToolUse
        print(f'verdict-fresh-check: {type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

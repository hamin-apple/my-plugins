#!/usr/bin/env python3
"""Changed-file map for Verify and Review (accept.md step 7): each changed file with its work units, criteria and fingerprint.

usage: changed-files.py --task TASK_FOLDER [--previous EARLIER_CHANGED_FILES_MD]

Writes <task folder>/changed-files.md and prints one line `changed-files: <N> files, <M> unmapped[, <K> changed since Run <r>]`.
Files: in the dev profile with a git task location, `git diff --name-only HEAD` plus the untracked files, without the
task records folder; otherwise the files under <task folder>/work/ and deliverable/.
A file maps to every plan unit that names it (`Files to change`, or any backticked path of the unit outside git); a file
no unit names is `unmapped`, a shared test helper or `ma_schema.py` is `shared`; both have the criteria `all`.
The criteria come from the units that name the file only: a criterion that also leans on a file of another unit is
re-judged when that file's own criteria are listed (or `all`).
With --previous, `Since previous` is `changed` or `same`, a file of the previous map that is no longer changed is a
`reverted` row (once: a row already `reverted` there is left out, so later maps do not keep it), and `Re-judge:` is the union of the criteria of the changed rows (`all` when one of them is unmapped or
shared, `none` when nothing changed). Without it, `Re-judge: all`.
exit: 0 written, 1 intake.md or plan.md missing (or the map could not be written), 2 bad arguments or --previous names no file.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_schema  # noqa: E402

PLUGIN_PREFIX = re.compile(r'^plugins/[^/]+/')
BACKTICKED = re.compile(r'`([^`\s]+)`')


def say(text: str, code: int) -> int:
    print(f'changed-files: {text}')
    return code


def field(text: str, name: str):
    m = re.search(rf'(?m)^{name}:\s*(.*\S)\s*$', text or '')
    return m.group(1) if m else None


def git(root: Path, *args):
    """stdout lines of a git command in `root`, or None when git fails."""
    try:
        res = subprocess.run(['git', '-C', str(root), '-c', 'core.quotepath=false', *args],   # real non-ASCII names
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.splitlines() if res.returncode == 0 else None


def unit_paths(plan: str) -> list:
    """[(id, criteria, files to change, every backticked path of the unit)] of the plan's work units."""
    details = {u['id']: u for u in ma_schema.unit_details(plan)}
    paths, current = {}, None
    for line in ma_schema.section_lines(plan, 'Work units') or []:
        head = ma_schema.UNIT_HEAD.match(line)
        if head:
            current = head.group(1)
            paths[current] = []
        elif current:
            paths[current] += BACKTICKED.findall(line)
    return [(uid, u['criteria'], u['files'], paths.get(uid, [])) for uid, u in details.items()]


def shared(path: str) -> bool:
    """A file many criteria lean on: a test helper, a test fixture or the shared format module."""
    name, in_tests = path.rsplit('/', 1)[-1], '/tests/' in f'/{path}'
    return name in ('conftest.py', 'ma_schema.py') or in_tests and (name == 'helpers.py' or '/fixtures/' in f'/{path}')


def fingerprint(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return 'deleted'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--task', required=True)
    ap.add_argument('--previous')
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    task = Path(args.task).resolve()
    intake, plan = task / 'intake.md', task / 'plan.md'
    if not intake.is_file() or not plan.is_file():
        return say(f'{"intake.md" if not intake.is_file() else "plan.md"} missing in {task}', 1)
    previous = Path(args.previous).resolve() if args.previous else None
    if previous is not None and not previous.is_file():
        return say(f'no such previous map: {previous}', 2)
    itext, ptext = intake.read_text(encoding='utf-8'), plan.read_text(encoding='utf-8')
    location = Path(field(itext, 'Location') or task.parent.parent)
    top = git(location, 'rev-parse', '--show-toplevel') if field(itext, 'Profile') == 'dev' else None
    units = unit_paths(ptext)

    if top:
        root = Path(top[0])
        try:
            records = task.parent.relative_to(root).as_posix() + '/'
        except ValueError:
            records = None
        names = (git(root, 'diff', '--name-only', 'HEAD') or []) + \
            (git(root, 'ls-files', '--others', '--exclude-standard', '--full-name') or [])
        files = sorted({n for n in names if n and not (records and n.startswith(records))})
        base = (git(root, 'rev-parse', '--short', 'HEAD') or ['-'])[0]

        def owners(f):
            return [(uid, crit) for uid, crit, named, _all in units if f in named or PLUGIN_PREFIX.sub('', f) in named]
    else:
        root = task
        files = sorted(p.relative_to(task).as_posix() for d in ('work', 'deliverable') if (task / d).is_dir()
                       for p in (task / d).rglob('*') if p.is_file())
        base = '-'

        def owners(f):
            return [(uid, crit) for uid, crit, _named, every in units if any(p == f or p.endswith('/' + f) for p in every)]

    prev_rows = {}
    run = None
    if previous is not None:
        prev_rows = {r['file']: r for r in ma_schema.changed_files_rows(previous.read_text(encoding='utf-8'))[0]}
        verify = previous.with_name('verify.md')
        run = ma_schema.run_number(verify.read_text(encoding='utf-8')) if verify.is_file() else None

    rows = []
    gone = {f for f in set(prev_rows) - set(files) if prev_rows[f]['fingerprint'] != 'reverted'}
    for f in files + sorted(gone):
        own = owners(f)
        if shared(f):
            unit_cell, crit_cell = 'shared', ma_schema.ALL_CRITERIA
        elif not own:
            unit_cell, crit_cell = 'unmapped', ma_schema.ALL_CRITERIA
        else:
            unit_cell = ', '.join(uid for uid, _c in own)
            nums = sorted({n for _u, crit in own for n in crit})
            crit_cell = ', '.join(map(str, nums)) or '-'
        fp = fingerprint(root / f) if f in files else 'reverted'
        if previous is None:
            since = '-'
        else:
            since = 'same' if f in prev_rows and prev_rows[f]['fingerprint'] == fp else 'changed'
        rows.append((f, unit_cell, crit_cell, fp, since))

    changed = [r for r in rows if r[4] == 'changed']
    if previous is None:
        rejudge = ma_schema.ALL_CRITERIA
    elif any(r[2] == ma_schema.ALL_CRITERIA for r in changed):
        rejudge = ma_schema.ALL_CRITERIA
    else:
        nums = sorted({int(n) for r in changed for n in re.findall(r'\d+', r[2])})
        rejudge = ', '.join(map(str, nums)) or 'none'

    run_text = '?' if run is None else str(run)
    lines = [f'# Changed files: {task.name}', f'Base: {base}',
             f'Previous: {previous} (Run {run_text})' if previous else 'Previous: none',
             f'Re-judge: {rejudge}', '',
             '| File | Units | Criteria | Fingerprint | Since previous |', '|---|---|---|---|---|']
    lines += [f'| {" | ".join(r)} |' for r in rows]
    try:
        (task / ma_schema.CHANGED_FILES).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except OSError as exc:
        return say(f'cannot write {task / ma_schema.CHANGED_FILES}: {exc}', 1)
    unmapped = sum(1 for r in rows if r[1] == 'unmapped')
    tail = f', {len(changed)} changed since Run {run_text}' if previous else ''
    print(f'changed-files: {len(rows)} files, {unmapped} unmapped{tail}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

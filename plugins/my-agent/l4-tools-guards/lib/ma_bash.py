"""What a Bash command line writes, reads, or copies from (architecture 4.4 "what is blocked", 4.5 "Bash for L2 judges",
4.12 "limiting read paths too"). Best effort by design: a write it cannot see (`python -c`, a script) is the accepted
risk of 4.4 "remaining risk"; the forms it knows are pinned case by case in tests/test_bash.py. What it cannot follow
(command substitution, a heredoc left open, a `cd` to a variable, a symlink made and written through in one command)
fails closed: None.
"""
import os
import re
import shlex
from pathlib import Path
from typing import List, NamedTuple, Optional

OPS = ';&|()<>\n'
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SUBST = re.compile(r'`|\$\(')
VAR_PATH_NOT = re.compile(r'://|^[sy]/|[\^\\|()<>"\'`]')
ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
NOT_PATH = re.compile(r'[\^$\\|(){}<>"\'`]|://|^[sy]/')
PREFIX = {'sudo', 'doas', 'env', 'command', 'time', 'nohup', 'nice', 'exec', 'builtin', 'timeout', 'xargs'}
PREFIX_VALUE = {'sudo': {'-u', '-g', '-h', '-p', '-C', '-D', '-r', '-t', '-U', '-T'}, 'doas': {'-u', '-C'},
                'env': {'-u', '-C', '-S', '--unset', '--chdir', '--split-string'}, 'nice': {'-n', '--adjustment'},
                'timeout': {'-s', '-k', '--signal', '--kill-after'},
                'xargs': {'-I', '-i', '-n', '-P', '-L', '-l', '-s', '-d', '-E', '-e', '-a'}}
RESERVED = {'if', 'then', 'else', 'elif', 'while', 'until', 'do', '!', '{', '}'}
SHELLS = {'bash', 'sh', 'zsh', 'dash', 'ksh'}
CD = {'cd', 'pushd'}
LAST_ARG = {'cp', 'mv', 'rsync', 'install', 'ln'}
ALL_ARGS = {'rm', 'rmdir', 'mkdir', 'touch', 'truncate', 'unlink', 'tee'}
COPY = {'cp', 'mv', 'rsync'}
GIT_READ = {'status', 'diff', 'log', 'show', 'blame', 'annotate', 'ls-files', 'ls-tree', 'rev-parse', 'grep',
            'cat-file', 'describe', 'shortlog', 'rev-list', 'merge-base', 'name-rev', 'show-ref', 'for-each-ref',
            'count-objects', 'check-ignore', 'whatchanged', 'var', 'help', 'version'}
GIT_BRANCH_WRITE = {'-d', '-D', '-m', '-M', '-c', '-C', '-f', '--delete', '--move', '--copy', '--force'}
FIND_WRITE = {'-delete', '-exec', '-execdir', '-ok', '-okdir', '-fprint', '-fprintf', '-fls'}


class Simple(NamedTuple):
    words: List[str]       # assignments and prefixes (sudo, env, xargs…) removed; words[0] is the command
    xargs: bool            # run through xargs: its arguments come from stdin
    redirects: List[str]   # output redirect targets, /dev/null and fd duplications left out
    inputs: List[str]      # input redirect files


def _strip_heredocs(cmd: str) -> str:
    """`cmd` without heredoc bodies; ValueError when a heredoc is never closed (`echo "<<EOF"` would hide the rest)."""
    out, waiting = [], []
    for line in cmd.split('\n'):
        if waiting:
            if line.strip() == waiting[0]:
                waiting.pop(0)
            continue
        out.append(line)
        waiting = [m.group(2) for m in HEREDOC.finditer(line)]
    if waiting:
        raise ValueError('heredoc not closed')
    return '\n'.join(out)


def _tokens(cmd: str) -> List[str]:
    lex = shlex.shlex(_strip_heredocs(cmd), posix=True, punctuation_chars=OPS)
    lex.whitespace = ' \t\r'
    lex.whitespace_split = True
    toks = list(lex)
    if any(SUBST.search(tok) for tok in toks):
        raise ValueError('command substitution')
    return toks


def _is_op(tok: str) -> bool:
    return tok != '' and all(c in OPS for c in tok)


def _inner(c: 'Simple') -> Optional[str]:
    """The command string run by `bash -c '<s>'` or `eval <s>`, else None."""
    if not c.words:
        return None
    name, args = os.path.basename(c.words[0]), c.words[1:]
    if name == 'eval':
        return ' '.join(args)
    if name in SHELLS:
        opts = [a for a in args if a.startswith('-') and not a.startswith('--')]
        rest = [a for a in args if not a.startswith('-')]
        if any('c' in o[1:] for o in opts) and rest:
            return rest[0]
    return None


def _commands(cmd: str, depth: int = 0) -> List[Simple]:
    """Simple commands of `cmd`, with `bash -c` and `eval` strings parsed in place; raises ValueError when it
    does not tokenize (an open quote, command substitution, an open heredoc) or nests too deep."""
    if depth > 3:
        raise ValueError('nested shells too deep')
    toks, out = _tokens(cmd), []
    words, redirects, inputs = [], [], []

    def flush():
        if words or redirects or inputs:
            s = _simple(words, redirects, inputs)
            inner = _inner(s)
            if inner is None:
                out.append(s)
            else:
                out.append(Simple(s.words[:1], s.xargs, s.redirects, s.inputs))
                out.extend(_commands(inner, depth + 1))

    i = 0
    while i < len(toks):
        t = toks[i]
        if _is_op(t) and ('>' in t or '<' in t):
            target = toks[i + 1] if i + 1 < len(toks) and not _is_op(toks[i + 1]) else None
            i += 2 if target is not None else 1
            if words and words[-1].isdigit():
                words.pop()          # the fd number of `2>`
            if target is None:
                continue
            if '>' in t:
                dup = '&' in t and (target.isdigit() or target == '-')
                if not dup and target != '/dev/null' and not target.startswith(('/dev/fd/', '/dev/std')):
                    redirects.append(target)
            elif t == '<':
                inputs.append(target)
            continue
        if _is_op(t):
            flush()
            words, redirects, inputs = [], [], []
        else:
            words.append(t)
        i += 1
    flush()
    return out


def _simple(words, redirects, inputs) -> Simple:
    rest, xargs = list(words), False
    while rest:
        name = os.path.basename(rest[0])
        if ASSIGN.match(rest[0]) or rest[0] in RESERVED:
            rest.pop(0)
        elif name in PREFIX:
            xargs = xargs or name == 'xargs'
            rest.pop(0)
            while rest and rest[0].startswith('-'):
                opt = rest.pop(0)
                if opt in PREFIX_VALUE.get(name, ()) and rest:
                    rest.pop(0)
            if name == 'timeout' and rest:
                rest.pop(0)      # the duration
        else:
            break
    return Simple(rest, xargs, list(redirects), list(inputs))


def _positional(args: List[str]) -> List[str]:
    out, after = [], False
    for a in args:
        if after:
            out.append(a)
        elif a == '--':
            after = True
        elif not a.startswith('-') or a == '-':
            out.append(a)
    return out


def _path(tok: str, cwd: Path) -> Optional[Path]:
    if '$' in tok or '`' in tok:
        return None
    p = Path(os.path.expanduser(tok))
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _git_sub(args: List[str]):
    """(subcommand, its arguments, the global options) of a git argument list (-C x, -c k=v, --no-pager…)."""
    i, opts = 0, []
    while i < len(args) and args[i].startswith('-'):
        opts.append(args[i])
        i += 2 if args[i] in ('-C', '-c') else 1
    return (args[i], args[i + 1:], opts) if i < len(args) else (None, [], opts)


def _git_mutating(args: List[str]) -> bool:
    """True unless the git command is a known read (an allowlist, 4.5 "read and check commands"): `-c` and `--exec-path`
    can run code, `--output` writes a file."""
    sub, rest, opts = _git_sub(args)
    if any(o in ('-c', '--config-env') or o.startswith(('--exec-path', '--config-env=')) for o in opts):
        return True
    if sub is None:
        return False
    if any(r.startswith('--output') for r in rest) or (sub == 'grep' and any(r.startswith(('-O', '--open-files'))
                                                                             for r in rest)):
        return True
    pos = _positional(rest)
    if sub in GIT_READ:
        return False
    if sub == 'stash':
        return not (pos and pos[0] in ('list', 'show'))
    if sub == 'branch':
        return bool(pos) or any(r in GIT_BRANCH_WRITE for r in rest)
    if sub == 'tag':
        return bool(pos) or any(r in ('-d', '--delete', '-a', '-s', '-f') for r in rest)
    if sub == 'config':
        return len(pos) >= 2 or any(r.startswith(('--unset', '--add', '--replace', '--rename', '--remove'))
                                    for r in rest)
    if sub in ('worktree', 'remote', 'submodule'):
        return bool(pos) and pos[0] not in ('list', 'show', 'status', '-v')
    return True


def _sed_files(args: List[str]) -> List[str]:
    inplace = any(a == '--in-place' or a.startswith('--in-place=')
                  or (a.startswith('-') and not a.startswith('--') and 'i' in a[1:]) for a in args)
    if not inplace:
        return []
    pos, script, i = [], False, 0
    while i < len(args):
        a = args[i]
        if a in ('-e', '-f', '--expression', '--file'):
            script, i = True, i + 2
            continue
        if a.startswith(('--expression=', '--file=')):
            script = True
        elif a == '-i' and i + 1 < len(args) and args[i + 1] == '':
            i += 1           # BSD `sed -i ''`: empty backup suffix
        elif not a.startswith('-') and a != '':
            pos.append(a)
        i += 1
    return pos if script else pos[1:]


def _writes(c: Simple) -> Optional[List[str]]:
    """Raw target words of one simple command, or None when it writes somewhere it cannot name."""
    if not c.words:
        return []
    name, args = os.path.basename(c.words[0]), c.words[1:]
    if name == 'git':
        return None if _git_mutating(args) else []
    if name == 'find':
        return None if any(a in FIND_WRITE for a in args) else []
    if name == 'sed':
        targets = _sed_files(args)
    elif name == 'dd':
        targets = [a[3:] for a in args if a.startswith('of=')]
    elif name in LAST_ARG:
        targets = _positional(args)[-1:]
    elif name in ALL_ARGS:
        targets = _positional(args)
    else:
        return []
    if c.xargs and (targets or name != 'tee'):
        return None
    return targets


def _walk(cmd: str, cwd: Path):
    """(simple command, every folder it may run in) in order: a literal `cd`/`pushd` adds its target to the
    folders (`&&`, `||` and subshells decide whether it applies, so all are kept). None when a `cd` goes to a
    folder it cannot name (`$VAR`, `-`) or `cmd` does not tokenize."""
    try:
        cmds = _commands(cmd)
    except ValueError:
        return None
    cwds, out = [Path(cwd)], []
    for c in cmds:
        out.append((c, list(cwds)))
        if c.words and c.words[0] in CD:
            args = _positional(c.words[1:])
            target = args[0] if args else '~'
            if target == '-':
                return None
            new = [_path(target, d) for d in cwds]
            if None in new:
                return None
            cwds += [n for n in new if n not in cwds]
    return out


def _resolve_all(tok: str, cwds: List[Path]) -> Optional[List[Path]]:
    out = []
    for d in cwds:
        p = _path(tok, d)
        if p is None:
            return None
        if p not in out:
            out.append(p)
    return out


def write_targets(cmd: str, cwd: Path) -> Optional[List[Path]]:
    """Absolute paths `cmd` creates, changes or deletes; [] when it writes nothing it knows of;
    None when it writes but a target cannot be named (git that changes the tree, `$VAR`, xargs, find -delete,
    a symlink made in the same command as another write, anything `_walk` cannot follow)."""
    walked = _walk(cmd, cwd)
    if walked is None:
        return None
    out, writers, link = [], 0, False
    for c, cwds in walked:
        raw = _writes(c)
        if raw is None:
            return None
        if c.redirects or raw:
            writers += 1
            link = link or os.path.basename(c.words[0]) == 'ln' if c.words else link
        for tok in c.redirects + raw:
            ps = _resolve_all(tok, cwds)
            if ps is None:
                return None
            out += ps
    if link and writers > 1:
        return None
    return out


def _looks_like_path(tok: str, cwd: Path) -> bool:
    if tok == '' or NOT_PATH.search(tok):
        return False
    if '/' in tok or tok.startswith(('.', '~')):
        return True
    try:
        return (Path(cwd) / tok).exists()
    except OSError:
        return False


def _var_path(tok: str) -> bool:
    return '$' in tok and not VAR_PATH_NOT.search(tok) and ('/' in tok or tok.startswith(('~', '.')))


def read_paths(cmd: str, cwd: Path) -> Optional[List[Path]]:
    """Every argument of `cmd` that looks like a path (has `/`, starts with `.` or `~`, or exists under `cwd`),
    resolved against every folder a `cd` may have reached; `--opt=/x` values included, the command word itself and
    patterns (`^/api`, `s/a/b/`, URLs) not. None when a read cannot be named: a path built from a variable
    (`$HOME/.ssh/x`), or anything `_walk` cannot follow."""
    walked = _walk(cmd, cwd)
    if walked is None:
        return None
    out = []
    for c, cwds in walked:
        for a in c.words[1:] + c.inputs:
            if a.startswith('-'):
                if '=' not in a:
                    continue
                a = a.split('=', 1)[1]
            if _var_path(a):
                return None
            if any(_looks_like_path(a, d) for d in cwds):
                for p in _resolve_all(a, cwds) or []:
                    if p not in out:
                        out.append(p)
    return out


def copy_sources(cmd: str, cwd: Path) -> List[Path]:
    """Source arguments of every cp, mv or rsync in `cmd` (all positional arguments but the last)."""
    try:
        cmds = _commands(cmd)
    except ValueError:
        return []
    out = []
    for c in cmds:
        if c.words and os.path.basename(c.words[0]) in COPY:
            for a in _positional(c.words[1:])[:-1]:
                p = _path(a, cwd)
                if p is not None:
                    out.append(p)
    return out


def git_mutates(cmd: str) -> bool:
    """True when any git in `cmd` changes the repository or work tree (or `cmd` does not tokenize)."""
    try:
        cmds = _commands(cmd)
    except ValueError:
        return True
    return any(c.words and os.path.basename(c.words[0]) == 'git' and _git_mutating(c.words[1:]) for c in cmds)


CURL_SEND_SHORT = set('dFT')                  # -d DATA, -F FORM, -T FILE (also clustered: -sd)
CURL_SEND_LONG = ('--data', '--form', '--upload-file', '--json', '--url-query')
WGET_SEND_LONG = ('--post-data', '--post-file', '--body-data', '--body-file', '--method')


def http_sends(cmd: str) -> Optional[bool]:
    """Whether a curl or wget in `cmd` sends data (POST/PUT, form, upload); None when `cmd` does not tokenize."""
    try:
        cmds = _commands(cmd)
    except ValueError:
        return None
    for c in cmds:
        if not c.words:
            continue
        name, args = os.path.basename(c.words[0]), c.words[1:]
        if name == 'wget' and any(a.split('=', 1)[0] in WGET_SEND_LONG for a in args):
            return True
        if name != 'curl':
            continue
        for i, a in enumerate(args):
            if a.startswith('--'):
                key = a.split('=', 1)[0]
                if key.startswith(CURL_SEND_LONG):
                    return True
                if key == '--request':
                    method = a.split('=', 1)[1] if '=' in a else (args[i + 1] if i + 1 < len(args) else '')
                    if method.upper() not in ('GET', 'HEAD'):
                        return True
            elif a.startswith('-') and len(a) > 1:
                flags = a[1:]
                for j, ch in enumerate(flags):
                    if ch in CURL_SEND_SHORT:
                        return True
                    if ch == 'X':
                        method = flags[j + 1:] or (args[i + 1] if i + 1 < len(args) else '')
                        if method.upper() not in ('GET', 'HEAD'):
                            return True
                        break
                    if ch in 'oHAeuUwbcEKm':   # options taking a value end the cluster
                        break
    return False


def git_subcommands(cmd: str) -> List[str]:
    """The subcommand of every git in `cmd`, in order; ['?'] when `cmd` does not tokenize and has the word git."""
    try:
        cmds = _commands(cmd)
    except ValueError:
        return ['?'] if re.search(r'\bgit\b', cmd) else []
    subs = [_git_sub(c.words[1:])[0] for c in cmds if c.words and os.path.basename(c.words[0]) == 'git']
    return [s for s in subs if s is not None]

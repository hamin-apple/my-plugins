#!/usr/bin/env python3
"""Claude Code skill-list check (repository tool, not shipped with a plugin).

Which skills does the Claude Code harness register for the my-agent plugin in a fresh session?

  claude-skill-check.py [--claude PATH] run <dir> --plugin <plugin folder> [--disable <plugin@marketplace> ...]

One short `claude -p` session runs in the empty folder <dir>/work. The listing is read from the harness's own
`system`/`init` event in the stream-json output, not from the model's answer. Installed copies named by --disable
(default `my-agent@my-plugins`) are switched off for that session so that only the folder under check loads.
Writes <dir>/outcome.md and prints it; line 1 is `Outcome: listed`, `Outcome: problem` or `Outcome: not run <reason>`.
Exit 0 for listed, 1 for problem, 3 for not run, 2 when <dir> is inside the repository (nothing written).
Nothing is written outside <dir>; Claude Code settings are not changed.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_NAME = 'my-agent'
DEFAULT_DISABLE = 'my-agent@my-plugins'
MAIN_FORMS = ('my-agent:my-agent', 'my-agent')
OTHER_SKILLS = ('my-agent:monitor', 'my-agent:mock-up')
PROMPT = 'Reply with exactly: ok.'
TIMEOUT = 300
DROPPED_ENV = ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_PROJECT_DIR',
               'CLAUDE_PLUGIN_ROOT')


class NotRun(Exception):
    pass


def inside_repo(path: Path) -> bool:
    path = Path(path).resolve()
    return path == REPO or REPO in path.parents


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def log_line(base: Path, text: str):
    with open(base / 'run.log', 'a', encoding='utf-8') as handle:
        handle.write(text + '\n')


def call(claude: str, argv: list, cwd=None, env=None):
    return subprocess.run([claude] + argv, capture_output=True, text=True, timeout=TIMEOUT,
                          cwd=cwd, env=env, stdin=subprocess.DEVNULL)


def first_line(text: str) -> str:
    return (text.strip().splitlines() or [''])[0]


def child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in DROPPED_ENV}


def parse_init(text: str):
    """First system/init event of the stream: (line number, event), or (None, None)."""
    for number, line in enumerate(text.splitlines(), 1):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get('type') == 'system' and obj.get('subtype') == 'init':
            return number, obj
    return None, None


def names(entries) -> list:
    out = []
    for entry in entries:
        name = entry.get('name') if isinstance(entry, dict) else entry
        if isinstance(name, str):
            out.append(name.lstrip('/'))
    return out


def judge(event: dict, plugin: Path):
    """(skills seen, problem lines) from the init event."""
    problems = []
    entries = [p for p in event['plugins'] if isinstance(p, dict) and p.get('name') == PLUGIN_NAME]
    paths = [str(p.get('path')) for p in entries]
    if not entries:
        problems.append(f'{PLUGIN_NAME} not loaded')
    elif len(entries) > 1 or Path(paths[0]).resolve() != plugin.resolve():
        problems.append(f'{PLUGIN_NAME} loaded from {", ".join(paths)}')
    counts = Counter()
    for key in ('skills', 'slash_commands'):
        if key in event:
            for name, number in Counter(names(event[key])).items():
                counts[name] = max(counts[name], number)
    mine = {n: c for n, c in counts.items() if n.startswith(PLUGIN_NAME + ':') or n == PLUGIN_NAME}
    main = [n for n in MAIN_FORMS if n in mine]
    if not main:
        problems.append(f'{MAIN_FORMS[0]} not listed')
    for name in main + list(OTHER_SKILLS):
        if name not in mine:
            if name in OTHER_SKILLS:
                problems.append(f'{name} not listed')
        elif mine[name] > 1:
            problems.append(f'{name} listed {mine[name]} times')
    if len(main) > 1:
        problems.append(f'main skill listed in two forms: {", ".join(main)}')
    for name in sorted(mine):
        if name not in MAIN_FORMS and name not in OTHER_SKILLS:
            problems.append(f'{name} listed')
    return list(mine), problems


def settings_json(disable: list) -> str:
    return json.dumps({'enabledPlugins': {name: False for name in disable}})


def execute(base: Path, args, plugin: Path):
    """Run the session; returns (version, validate line or None, validate problem, stdout, init number, init event)."""
    try:
        version = call(args.claude, ['--version'])
    except OSError as err:
        log_line(base, f'{args.claude}: not run: {type(err).__name__}: {err}')
        raise NotRun('no claude binary')
    write(base / 'claude-version.txt', version.stdout)
    log_line(base, f'{args.claude} --version -> exit {version.returncode}')
    helptext = call(args.claude, ['--help']).stdout
    validate = call(args.claude, ['plugin', 'validate', '--strict', str(plugin)])
    write(base / 'validate.txt', validate.stdout + validate.stderr)
    log_line(base, f'{args.claude} plugin validate --strict {plugin} -> exit {validate.returncode}')
    argv = ['-p', '--plugin-dir', str(plugin), '--settings', settings_json(args.disable),
            '--output-format', 'stream-json', '--verbose', '--max-turns', '1', '--model', 'haiku']
    argv += [flag for flag in ('--no-session-persistence', '--strict-mcp-config') if flag in helptext]
    argv.append(PROMPT)
    try:
        done = call(args.claude, argv, cwd=str(base / 'work'), env=child_env())
    except subprocess.TimeoutExpired:
        raise NotRun(f'timeout after {TIMEOUT} s')
    write(base / 'stdout.jsonl', done.stdout)
    write(base / 'stderr.txt', done.stderr)
    log_line(base, f'{args.claude} -p --plugin-dir {plugin} --max-turns 1 --model haiku -> exit {done.returncode}')
    number, event = parse_init(done.stdout)
    if event is None:
        if done.returncode != 0:
            raise NotRun(f'claude refused to start: {first_line(done.stderr) or "exit " + str(done.returncode)}')
        raise NotRun('no init event')
    write(base / 'init.json', json.dumps(event, indent=2) + '\n')
    if 'plugins' not in event:
        raise NotRun('init event lacks plugins')
    if not isinstance(event['plugins'], list):
        raise NotRun('init event plugins is not a list')
    if 'skills' not in event and 'slash_commands' not in event:
        raise NotRun('init event lacks skills and slash_commands')
    return version.stdout.strip(), validate, done.stdout, number, event


def cmd_run(args) -> int:
    base = Path(args.dir).resolve()
    if inside_repo(base):
        print(f'refusing to run inside the repository: {base}', file=sys.stderr)
        return 2
    plugin = Path(args.plugin).resolve()
    args.disable = args.disable or [DEFAULT_DISABLE]
    (base / 'work').mkdir(parents=True, exist_ok=True)
    try:
        version, validate, _, number, event = execute(base, args, plugin)
    except (NotRun, subprocess.TimeoutExpired) as err:
        reason = str(err) if isinstance(err, NotRun) else f'timeout after {TIMEOUT} s'
        text = f'Outcome: not run {reason}\n'
        write(base / 'outcome.md', text)
        print(text, end='')
        return 3
    seen, problems = judge(event, plugin)
    validate_line = 'passed'
    if validate.returncode != 0:
        validate_line = f'failed: {first_line(validate.stdout + validate.stderr) or "exit " + str(validate.returncode)}'
        problems.insert(0, f'validate {validate_line}')
    lines = [f'Outcome: {"problem" if problems else "listed"}',
             f'Claude Code: {version}',
             f'Plugin: {PLUGIN_NAME} from {plugin} (installed copies disabled: {", ".join(args.disable)})',
             f'Skills: {", ".join(seen) or "none"}',
             f'Validate: {validate_line}',
             f'Evidence: stdout.jsonl line {number} (system init)'] + problems
    text = '\n'.join(lines) + '\n'
    write(base / 'outcome.md', text)
    print(text, end='')
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--claude', default='claude')
    sub = parser.add_subparsers(dest='cmd', required=True)
    run = sub.add_parser('run')
    run.add_argument('dir')
    run.add_argument('--plugin', required=True)
    run.add_argument('--disable', action='append', default=None)
    run.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

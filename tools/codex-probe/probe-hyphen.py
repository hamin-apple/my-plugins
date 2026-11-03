#!/usr/bin/env python3
"""Hyphen agent-type probe (repository tool, not shipped with a plugin).

Does Codex accept a hyphenated agent_type (`my-explorer`) in its spawn tool?

Subcommands:
  run <dir> [--agent my-explorer]
                 one `codex exec` in the throwaway folder <dir>/work that starts one sub-agent of that type;
                 writes codex-version.txt, run.log, captures/hyphen-events.jsonl, captures/hyphen-stderr.txt and
                 the throwaway session's own records in sessions/
  outcome <dir>  write <dir>/outcome.md; line 1 is `Outcome: accepted`, `Outcome: refused` or `Outcome: not run <reason>`

The Codex binary comes from the global `--codex <path>` option (default `codex`), the Codex home from `--codex-home`.
Nothing is written under the Codex home and its agents folder is never read.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location('codex_probe_base', Path(__file__).resolve().parent / 'probe.py')
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
REPO, call, walk, write, log_line = _base.REPO, _base.call, _base.walk, _base.write, _base.log_line
codex_home, collect_ids, copy_sessions = _base.codex_home, _base.collect_ids, _base.copy_sessions
spawn_agent_type, spawn_error = _base.spawn_agent_type, _base.spawn_error

SCENARIO = 'hyphen'
DEFAULT_AGENT = 'my-explorer'
TASK_NAME = 'hyphen_probe'
PROMPT = ('Start exactly one sub-agent with your spawn tool: agent_type `{agent}`, task_name `{task}`, '
          'message `Reply with the single word ok.` Do not start any other agent and do not retry with another '
          'agent_type or task_name. Wait for it and report its answer, or the exact error text of the spawn call.')
SPAWN_NAME = re.compile(r'spawn_agent$')
TASK_NAME_ERROR = re.compile(r'agent_name must use only lowercase letters, digits, and underscores', re.I)
UNKNOWN_AGENT = re.compile(r'unknown agent[_ ]type|unknown agent', re.I)
EVENTS_REL = 'captures/hyphen-events.jsonl'


def inside_repo(path: Path) -> bool:
    path = Path(path).resolve()
    return path == REPO or REPO in path.parents


def not_run(base: Path, args, err: Exception):
    write(base / EVENTS_REL, '')
    write(base / 'captures' / 'hyphen-stderr.txt', '')
    write(base / 'codex-error.txt', f'{type(err).__name__}: {err}\n')
    log_line(base, f'{args.codex}: not run: {type(err).__name__}: {err}')


def parse_lines(text: str) -> list:
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        try:
            out.append((number, json.loads(line)))
        except ValueError:
            continue
    return out


def cmd_run(args) -> int:
    base = Path(args.dir).resolve()
    if inside_repo(base):
        sys.exit(f'refusing to run inside the repository: {base}')
    work = base / 'work'
    work.mkdir(parents=True, exist_ok=True)
    (base / 'captures').mkdir(parents=True, exist_ok=True)
    write(base / 'agent.txt', args.agent + '\n')
    try:
        version = call(args.codex, ['--version'])
        write(base / 'codex-version.txt', version.stdout)
        log_line(base, f'{args.codex} --version -> exit {version.returncode}')
        argv = ['exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check', '-C', str(work),
                PROMPT.format(agent=args.agent, task=TASK_NAME)]
        done = call(args.codex, argv, cwd=str(work))
    except Exception as err:  # no binary, timeout
        not_run(base, args, err)
        return 1
    write(base / EVENTS_REL, done.stdout)
    write(base / 'captures' / 'hyphen-stderr.txt', done.stderr)
    log_line(base, f'{args.codex} exec --json --sandbox read-only -C {work} -> exit {done.returncode}')
    ids, paths = collect_ids(base, SCENARIO, [obj for _, obj in parse_lines(done.stdout)])
    copied = copy_sessions(ids, paths, codex_home(args) / 'sessions', base / 'sessions')
    log_line(base, f'copied {len(copied)} session record(s) of {len(ids)} id(s)')
    return 0 if done.returncode == 0 else 1


def spawn_calls(source: str, lines: list, agent: str) -> list:
    """Spawn calls of the probed agent type with their output: dicts of source, call line, output line, error."""
    found, pending = [], {}
    for number, obj in lines:
        for node in walk(obj):
            if not isinstance(node, dict):
                continue
            if node.get('type') == 'function_call' and SPAWN_NAME.search(str(node.get('name'))):
                if spawn_agent_type(node) == agent:
                    entry = {'source': source, 'call': number, 'output': None, 'error': None}
                    found.append(entry)
                    pending[node.get('call_id')] = entry
            elif node.get('type') == 'function_call_output' and node.get('call_id') in pending:
                entry = pending.pop(node['call_id'])
                entry['output'], entry['error'] = number, spawn_error(node)
                raw = node.get('output')
                if not entry['error'] and isinstance(raw, str) and (TASK_NAME_ERROR.search(raw) or UNKNOWN_AGENT.search(raw)):
                    entry['error'] = re.sub(r'\s+', ' ', raw).strip()[:200]
    return found


def classify(entry) -> str:
    err = entry['error']
    if entry['output'] is None:
        return 'not run spawn error: no output for the spawn call'
    if not err:
        return 'accepted'
    if TASK_NAME_ERROR.search(err):
        return 'not run task_name rejected'
    if UNKNOWN_AGENT.search(err):
        return 'refused'
    return f'not run spawn error: {err}'


def read_text(path: Path, default='') -> str:
    return path.read_text(encoding='utf-8') if path.is_file() else default


def cmd_outcome(args) -> int:
    base = Path(args.dir).resolve()
    agent = read_text(base / 'agent.txt').strip() or DEFAULT_AGENT
    version = read_text(base / 'codex-version.txt').strip() or 'unknown'
    events = parse_lines(read_text(base / EVENTS_REL))
    evidence = []
    if not events:
        reason = (read_text(base / 'codex-error.txt').strip().splitlines() or ['exec with no events'])[0]
        outcome = f'not run codex: {reason}'
        paragraph = f'The probe has no events from `codex exec` ({reason}), so no spawn call was seen.'
    else:
        entries = []
        sessions = base / 'sessions'
        for path in sorted(sessions.glob('*.jsonl')) if sessions.is_dir() else []:
            entries += spawn_calls(f'sessions/{path.name}', parse_lines(path.read_text(encoding='utf-8')), agent)
        entries += spawn_calls(EVENTS_REL, events, agent)
        if not entries:
            outcome = 'not run no spawn call'
            paragraph = f'No spawn call with agent_type `{agent}` appears in the events or the session records.'
        else:
            entry = entries[0]
            outcome = classify(entry)
            evidence.append(f'{entry["source"]} line {entry["call"]} (spawn call)')
            if entry['output'] is not None:
                evidence.append(f'{entry["source"]} line {entry["output"]} (spawn output)')
            detail = entry['error'] or 'no error text'
            if outcome == 'accepted':
                paragraph = f'The spawn call with agent_type `{agent}` returned without an error: the hyphenated name is accepted.'
            elif outcome == 'refused':
                paragraph = f'The spawn call with agent_type `{agent}` was refused as an unknown agent: {detail}'
            elif outcome == 'not run task_name rejected':
                paragraph = (f'Codex rejected the task_name `{TASK_NAME}` (the task_name rule, not the agent name), so the '
                             f'hyphenated agent_type is still untested: {detail}')
            else:
                paragraph = f'The spawn call with agent_type `{agent}` ended in an error that says nothing about the name rule: {detail}'
    lines = [f'Outcome: {outcome}', f'Agent type: {agent}', f'Codex: {version}']
    lines += [f'Evidence: {item}' for item in evidence] or ['Evidence: none']
    lines += ['', paragraph]
    write(base / 'outcome.md', '\n'.join(lines) + '\n')
    print(lines[0])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--codex-home', default=None)
    sub = parser.add_subparsers(dest='cmd', required=True)
    run = sub.add_parser('run')
    run.add_argument('dir')
    run.add_argument('--agent', default=DEFAULT_AGENT)
    run.set_defaults(func=cmd_run)
    out = sub.add_parser('outcome')
    out.add_argument('dir')
    out.set_defaults(func=cmd_outcome)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

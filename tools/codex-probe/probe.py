#!/usr/bin/env python3
"""Codex hook-contract probe (repository tool, not shipped with a plugin).

Subcommands:
  kit <dir> [--bump]          write the throwaway ma-probe plugin and marketplace into <dir>/kit
  kit <dir> --change-market   rewrite only the kit's marketplace files (install scenario)
  run <dir> hooks|stale|agents|skills|identity|install
                              run `codex exec` (or, for install, read-only snapshots) in a throwaway folder
  snapshot --out <folder> [--skills <folder>] [--cache <marketplace>/<plugin>]
                              save the output of read-only Codex commands; --skills runs `codex debug prompt-input` there and adds
                              skills-list.txt, skills-source.txt and skills-evidence.txt;
                              --cache adds cache-files.txt and the .codex-plugin/plugin.json copies
  e2e-setup <dir>             make the throwaway repository <dir>/repo and data folder <dir>/data
  e2e-request <install snapshot folder>
                              print the Step S3 request (read the installed SKILL.md by its path); writes no file
  e2e-collect <dir> --out <folder>
                              copy the throwaway task's run-log, task files and session records; write summary-e2e.json
  report <e2e folder> --findings <json> [--findings <json> ...] --out <file>
                              write the gap report from capabilities.json, the findings and summary-e2e.json
  summary <dir> --out <folder> [--config <toml>]
                              write summary-hooks.json, summary-agents.json and reduced captures
  findings <dir> --out <folder>
                              write codex-findings.md and codex-findings.json from both summaries
  summary-identity <dir> --out <folder>
                              write probe-identity/summary-identity.json, reduced captures and run.log
  findings-identity <folder>  write codex-findings-identity.md and .json from probe-identity/summary-identity.json
  kit-skills <dir>            write the skills kit (six plugins) into <dir>/kit; print the Codex commands, run none
  run <dir> skills-live|skills-kit
                              help texts, `codex debug prompt-input` and one read-only `codex exec` in <dir>/work-<scenario>
  summary-skills <dir> --out <folder>
                              write probe-skills/summary-skills.json and reduced captures of the skill listing
  findings-skills <folder>    write codex-findings-skills.md and .json from probe-skills/summary-skills.json
  check findings <file>       exit 0 when every section is present and every cited capture exists
                              (identity kind: also exactly one Outcome line)
  check report <file> --e2e <folder> [--probe-root <folder>]
                              exit 0 when the gap report is complete, every cite exists and no failure is unlisted
  check install <folder> [--root <path>] [--version <v>]
                              exit 0 when the saved snapshot proves my-agent is installed from the new copy

The Codex binary comes from the global `--codex <path>` option (default `codex`).
Commands that change Codex settings are only printed by `kit`; the person runs them.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAME = 'ma-probe'
SECRET = re.compile(r'KEY|TOKEN|SECRET|AUTH|PASS', re.I)
EVENTS = ['PreToolUse', 'PostToolUse', 'PermissionRequest', 'SessionStart', 'SubagentStart', 'SubagentStop', 'Stop']
MARKERS = ['deny', 'exit2', 'bad']
# file-change deny forms: form -> file-name marker (each form has its own file name, so each outcome is separate)
FILE_FORMS = {'deny': 'ma-probe-deny-file', 'exit2': 'ma-probe-fexit2', 'block': 'ma-probe-fblock',
              'stop': 'ma-probe-fstop', 'both': 'ma-probe-fboth', 'matcher': 'ma-probe-fmatch'}
MODE_OF_FORM = {'deny': 'deny-file', 'exit2': 'fexit2', 'block': 'fblock', 'stop': 'fstop', 'both': 'fboth',
                'matcher': 'fmatch'}
EXTRA_MARKERS = ['deny-file', 'fexit2', 'fblock', 'fstop', 'fboth', 'exit1']
WORKERS = ['ma_probe_worker_a', 'ma_probe_worker_b']
# one dump hook per matcher: label -> (event, matcher). File-change name candidates: the Codex patch tool and Claude names.
MATCHERS = {'matcher-Bash': ('PreToolUse', 'Bash'), 'matcher-anchored-Bash': ('PreToolUse', '^Bash$'),
            'matcher-Ba-star': ('PreToolUse', 'Ba.*'), 'matcher-Bash-or-Write': ('PreToolUse', 'Bash|Write'),
            'matcher-apply_patch': ('PreToolUse', 'apply_patch'), 'matcher-ApplyPatch': ('PreToolUse', 'ApplyPatch'),
            'matcher-functions-apply_patch': ('PreToolUse', 'functionsapply_patch'),
            'matcher-Edit-or-Write': ('PreToolUse', 'Edit|Write'),
            'matcher-start-worker-a': ('SubagentStart', '^ma_probe_worker_a$')}
HOOKS_FILE = './hooks/hooks.json'
SCENARIOS = ['hooks', 'stale', 'agents', 'skills', 'identity', 'install', 'skills-live', 'skills-kit']

DUMP_SOURCE = '''#!/usr/bin/env python3
"""ma-probe dump hook: record what Codex passes to a hook. Env values are stored only for CODEX_*/CLAUDE_*/MA_PROBE_* names."""
import json, os, re, sys, time
from datetime import datetime, timezone

CAPTURES = __CAPTURES__
SECRET = re.compile(r'KEY|TOKEN|SECRET|AUTH|PASS', re.I)
MODES = {'deny': 'echo ma-probe-deny', 'exit2': 'echo ma-probe-exit2', 'bad': 'echo ma-probe-bad',
         'deny-file': 'ma-probe-deny-file', 'exit1': 'echo ma-probe-exit1', 'fexit2': 'ma-probe-fexit2',
         'fblock': 'ma-probe-fblock', 'fstop': 'ma-probe-fstop', 'fboth': 'ma-probe-fboth', 'fmatch': 'ma-probe-fmatch'}
DENY = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                               'permissionDecisionReason': 'ma-probe deny'}}


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if not SECRET.search(k)}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
    mode = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] in MODES else None
    raw = sys.stdin.read()
    try:
        parsed = redact(json.loads(raw))
        head = None
    except ValueError:
        parsed, head = None, raw[:500]
    allowed = {k: v for k, v in os.environ.items()
               if re.match(r'(CODEX_|CLAUDE_|MA_PROBE_)', k) and not SECRET.search(k)}
    record = {'label': label, 'argv': sys.argv[1:], 'time': datetime.now(timezone.utc).isoformat(),
              'cwd': os.getcwd(), 'scenario': os.environ.get('MA_PROBE_SCENARIO'),
              'stdin_json': parsed, 'stdin_head': head,
              'env_names': sorted(os.environ), 'env_values': allowed}
    os.makedirs(CAPTURES, exist_ok=True)
    name = '%d-%s-%d.json' % (time.time_ns(), re.sub(r'[^A-Za-z0-9_-]', '_', label), os.getpid())
    with open(os.path.join(CAPTURES, name), 'w') as f:
        json.dump(record, f, indent=1)
    if mode and MODES[mode] in raw:
        if mode in ('deny', 'deny-file', 'fmatch'):
            print(json.dumps(DENY))
        elif mode == 'fblock':
            print(json.dumps({'decision': 'block', 'reason': 'ma-probe block'}))
        elif mode == 'fstop':
            print(json.dumps({'continue': False, 'stopReason': 'ma-probe stop'}))
        elif mode == 'fboth':
            print(json.dumps(dict(DENY, decision='block', reason='ma-probe block')))
        elif mode in ('exit2', 'fexit2'):
            sys.stderr.write('ma-probe exit 2\\n')
            sys.exit(2)
        elif mode == 'exit1':
            sys.stderr.write('ma-probe exit 1\\n')
            sys.exit(1)
        else:
            print('{"hookSpecificOutput": ')


main()
'''


def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if not SECRET.search(k)}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


# ---- kit ----

def build_hooks(dump: Path, bump: bool) -> dict:
    def command(label, mode=None, extra=None):
        parts = [f'python3 "{dump}"', label, '"${CLAUDE_PLUGIN_ROOT}"']
        if mode:
            parts.append(mode)
        if extra:
            parts.append(extra)
        return ' '.join(parts)

    def entry(cmd):
        return {'hooks': [{'type': 'command', 'command': cmd, 'timeout': 10}]}

    hooks = {event: [entry(command(event, extra='bumped' if bump and event == 'Stop' else None))] for event in EVENTS}
    for mode in MARKERS + EXTRA_MARKERS:
        hooks['PreToolUse'].append(entry(command('marker-' + mode, mode=mode)))
    # a failing exit-1 hook must block the call (fail-closed), not pass it
    for item in hooks['PreToolUse']:
        if item['hooks'][0]['command'].endswith(' exit1'):
            item['hooks'][0]['onFailure'] = 'block'
    # the same deny, from one hook that has a matcher on the file-change tool name
    item = entry(command('marker-fmatch', mode='fmatch'))
    item['matcher'] = 'apply_patch'
    hooks['PreToolUse'].append(item)
    for label, (event, matcher) in MATCHERS.items():
        item = entry(command(label))
        item['matcher'] = matcher
        hooks[event].append(item)
    return {'hooks': hooks}


SKILL_LINE = ('MA-PROBE-EXPAND skill_dir=<${CLAUDE_SKILL_DIR}> plugin_root=<${CLAUDE_PLUGIN_ROOT}> '
              'arguments=<$ARGUMENTS> opt=<${user_config.probe_opt}>')
AGENT_NAMES = ['ma_probe_agent_claude', 'ma_probe_agent_plugin_toml', 'ma_probe_agent_plugin_codexdir',
               'ma_probe_agent_manifest_toml', 'ma_probe_agent_project', 'ma_probe_agent_project_model',
               'ma_probe_agent_project_turns', 'ma_probe_agent_project_tools']
AGENT_LOCATIONS = {'ma_probe_agent_claude': 'plugin agents/*.md (Claude form)',
                   'ma_probe_agent_plugin_toml': 'plugin agents/*.toml',
                   'ma_probe_agent_plugin_codexdir': 'plugin .codex/agents/*.toml',
                   'ma_probe_agent_manifest_toml': 'plugin codex-agents/*.toml named in .codex-plugin/plugin.json',
                   'ma_probe_agent_project': 'project .codex/agents/*.toml',
                   'ma_probe_agent_project_model': 'project .codex/agents/*.toml (model key)',
                   'ma_probe_agent_project_turns': 'project .codex/agents/*.toml (max_turns key)',
                   'ma_probe_agent_project_tools': 'project .codex/agents/*.toml (tools key)'}
WORKER_EXTRA = 'sandbox_mode = "workspace-write"\n'
DESC = {'claude': 'ma-probe-desc-claude-manifest', 'codex': 'ma-probe-desc-codex-manifest'}
MARKET_DESC = {'claude': 'ma-probe-market-claude', 'codex': 'ma-probe-market-codex', 'changed': 'ma-probe-market-changed'}


def toml_agent(name, extra='', instructions=None):
    text = instructions or f'Reply with exactly: {name}-done'
    return (f'name = "{name}"\ndescription = "Throwaway probe agent {name}"\n{extra}'
            f'developer_instructions = "{text}"\n')


def write_workers(base: Path):
    """Two worker agents as project-level TOML in the throwaway identity work folder."""
    for name in WORKERS:
        write(base / 'work-identity' / '.codex' / 'agents' / f'{name}.toml',
              toml_agent(name, WORKER_EXTRA, 'Do exactly what the task message says, one step after another.'))


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def write_json(path: Path, data):
    write(path, json.dumps(data, indent=2) + '\n')


def market_files(kit: Path, changed: bool):
    """Both marketplace files carry different descriptions so the run can tell which one Codex read."""
    def plugin_entry(label):
        return [{'name': NAME, 'source': f'./plugins/{NAME}', 'description': MARKET_DESC['changed' if changed else label]}]
    write_json(kit / '.claude-plugin' / 'marketplace.json', {
        'name': NAME, 'owner': {'name': 'ma-probe'}, 'plugins': plugin_entry('claude')})
    write_json(kit / '.agents' / 'plugins' / 'marketplace.json', {
        'name': NAME, 'owner': {'name': 'ma-probe'}, 'plugins': plugin_entry('codex')})


def cmd_kit(args) -> int:
    base = Path(args.dir).resolve()
    kit = base / 'kit'
    plugin = kit / 'plugins' / NAME
    dump = kit / 'dump.py'
    if args.change_market:
        market_files(kit, True)
        print(f'marketplace files in {kit} changed (plugin description: {MARKET_DESC["changed"]})')
        print(f'  then: codex plugin add {NAME}@{NAME}   (does Codex re-read the folder?)')
        print(f'  then: codex plugin marketplace upgrade {NAME}   (does it refresh a local path?)')
        return 0
    write(dump, DUMP_SOURCE.replace('__CAPTURES__', repr(str(base / 'captures'))))
    dump.chmod(0o755)
    market_files(kit, False)
    write_json(plugin / '.claude-plugin' / 'plugin.json', {
        'name': NAME, 'version': '0.0.1', 'description': DESC['claude'],
        'skills': ['./', './skills/ma-probe-dir'], 'hooks': HOOKS_FILE,
        'agents': ['./agents/ma_probe_agent_claude.md'],
        'userConfig': {'probe_opt': {'type': 'string', 'title': 'Probe option', 'description': 'Probe option',
                                     'required': False, 'default': 'probe-default'}}})
    write_json(plugin / '.codex-plugin' / 'plugin.json', {
        'name': NAME, 'version': '0.0.1', 'description': DESC['codex'], 'skills': './skills/',
        'hooks': HOOKS_FILE, 'agents': ['./codex-agents/ma_probe_agent_manifest_toml.toml']})
    write(plugin / 'hooks' / 'hooks.json', json.dumps(build_hooks(dump, args.bump), indent=2) + '\n')
    write(plugin / 'SKILL.md', '---\nname: ma-probe-root\ndescription: Probe skill at the plugin root. Use when asked to use ma-probe-root.\n---\n\n' + SKILL_LINE + '\n')
    write(plugin / 'skills' / 'ma-probe-dir' / 'SKILL.md',
          '---\nname: ma-probe-dir\ndescription: Probe skill in a skills folder. Use when asked to use ma-probe-dir.\n---\n\n' + SKILL_LINE + '\n')
    write(plugin / 'agents' / 'ma_probe_agent_claude.md',
          '---\nname: ma_probe_agent_claude\ndescription: Probe agent in Claude form\nmodel: sonnet\neffort: low\n'
          'tools: Read\nmaxTurns: 3\n---\n\nReply with exactly: ma_probe_agent_claude-done\n')
    write(plugin / 'agents' / 'ma_probe_agent_plugin_toml.toml', toml_agent('ma_probe_agent_plugin_toml'))
    write(plugin / '.codex' / 'agents' / 'ma_probe_agent_plugin_codexdir.toml',
          toml_agent('ma_probe_agent_plugin_codexdir'))
    write(plugin / 'codex-agents' / 'ma_probe_agent_manifest_toml.toml', toml_agent('ma_probe_agent_manifest_toml'))
    write_workers(base)
    # a second folder with the same marketplace name (can two be added?)
    dup = base / 'kit-dup'
    write_json(dup / '.agents' / 'plugins' / 'marketplace.json', {
        'name': NAME, 'owner': {'name': 'ma-probe'},
        'plugins': [{'name': NAME + '-dup', 'source': f'./plugins/{NAME}-dup', 'description': 'ma-probe-market-dup'}]})
    write_json(dup / 'plugins' / (NAME + '-dup') / '.codex-plugin' / 'plugin.json', {
        'name': NAME + '-dup', 'version': '0.0.1', 'description': 'ma-probe-dup'})
    print(f'kit written to {kit}' + (' (bumped: one Stop hook command changed)' if args.bump else ''))
    print('Commands for the person (they change Codex settings):')
    print(f'  codex plugin marketplace add {kit}')
    print(f'  codex plugin add {NAME}@{NAME}')
    print('  then confirm the ma-probe hooks are listed (codex plugin list, or the plugin page in the Codex TUI);')
    print('  if they are not listed, stop here: Codex did not load hooks/hooks.json')
    print('  then trust the ma-probe hooks with Codex\'s own trust step')
    if args.bump:
        print(f'  reinstall: codex plugin remove {NAME}@{NAME} && codex plugin add {NAME}@{NAME}')
    print(f'  python3 {Path(__file__).resolve()} run {base} hooks')
    return 0


# ---- run / snapshot ----

def log_line(base: Path, text: str):
    with open(base / 'run.log', 'a', encoding='utf-8') as f:
        f.write(f'{now()} {text}\n')


def call(codex: str, argv: list, cwd=None, env=None):
    return subprocess.run([codex] + argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)


FILE_LIST = ', '.join(f'{m}-{{x}}.txt' for m in FILE_FORMS.values())
PROMPT = ('Run these three shell commands one after another, each in its own call, and report what happened: '
          'echo ma-probe-deny ; echo ma-probe-exit2 ; echo ma-probe-bad . Then run `echo hello`.')
WORKER_TASK = ('Task for ma_probe_worker_{x}: run `echo ma-probe-sub-{x}-shell`; create the file sub-{x}-note.txt with your '
               'file edit tool; run `echo ma-probe-deny`, `echo ma-probe-exit2` and `echo ma-probe-exit1`, each in its own '
               'call; then try to create each of these files with your file edit tool, one call per file, and report '
               'every result and error: ' + FILE_LIST.format(x='{x}') + '.')
PROMPTS = {
    'hooks': PROMPT,
    'stale': PROMPT,
    'agents': ('List the names of the sub-agents you can start. Then start each of these one at a time and report '
               'its answer or the error: ' + ', '.join(AGENT_NAMES) + '. Then start ma_probe_agent_project and '
               'ma_probe_agent_claude in parallel. Say which tool you used to start them.'),
    'identity': ('Do these steps in order and report what happened. 1. Run the shell command `echo ma-probe-main-shell`. '
                 '2. Create the file main-note.txt with your file edit tool. 3. Try to create each of these '
                 'files with your file edit tool, one call per file, and report every error: ' +
                 FILE_LIST.format(x='main') + '. 4. Start the two agents '
                 'ma_probe_worker_a and ma_probe_worker_b in parallel. ' + WORKER_TASK.format(x='a') + ' ' +
                 WORKER_TASK.format(x='b') + ' Wait for both agents and report their answers.'),
    'skills': ('List the names of your available skills. Then use the skill ma-probe-root and the skill '
               'ma-probe-dir with the argument arg-one. For each, print the line that starts with MA-PROBE-EXPAND '
               'exactly as you received it.'),
}
PROJECT_AGENTS = {
    'ma_probe_agent_project': 'model_reasoning_effort = "low"\nsandbox_mode = "read-only"\n',
    'ma_probe_agent_project_model': 'model = "ma-probe-model"\n',
    'ma_probe_agent_project_turns': 'max_turns = 3\n',
    'ma_probe_agent_project_tools': 'tools = ["Read"]\n',
}
ID_KEY = re.compile(r'(session_id|thread_id|agent_id)$')
INSTALL_STEPS = [
    ('initial', []),
    ('added', ['codex plugin marketplace add {kit}', 'codex plugin add ma-probe@ma-probe']),
    ('changed', ['python3 {probe} kit {base} --change-market', 'codex plugin add ma-probe@ma-probe']),
    ('upgraded', ['codex plugin marketplace upgrade ma-probe']),
    ('dup', ['codex plugin marketplace add {dup}']),
]
INSTALL_CLEANUP = ['codex plugin remove ma-probe@ma-probe', 'codex plugin marketplace remove ma-probe',
                   '(if the dup marketplace was added: remove it the same way)']


def codex_home(args) -> Path:
    return Path(args.codex_home or os.environ.get('CODEX_HOME') or '~/.codex').expanduser()


def collect_ids(base: Path, scenario: str, events: list) -> tuple:
    """Session ids and transcript paths of this scenario's throwaway sessions only."""
    ids, paths = set(), set()
    for event in events:
        for node in walk(event):
            if isinstance(node, dict):
                for k, v in node.items():
                    if ID_KEY.search(k) and isinstance(v, str):
                        ids.add(v)
    for rec in read_captures(base):
        stdin = rec.get('stdin_json')
        if rec.get('scenario') != scenario or not isinstance(stdin, dict):
            continue
        for k, v in stdin.items():
            if ID_KEY.search(k) and isinstance(v, str):
                ids.add(v)
            if k == 'transcript_path' and isinstance(v, str):
                paths.add(v)
    return {i for i in ids if len(i) >= 8}, paths


def copy_sessions(ids, paths, root: Path, dest: Path) -> list:
    """Copy only the session records of the given ids (file name contains the id) or the given hook paths."""
    copied = []
    root = Path(root)
    if root.is_dir():
        for path in sorted(root.rglob('*.jsonl')):
            if any(i in path.name for i in ids):
                copied.append(path)
    for item in sorted(paths):
        path = Path(item)
        if path.is_file() and root in path.resolve().parents and path not in copied:
            copied.append(path)
    dest.mkdir(parents=True, exist_ok=True)
    for path in copied:
        shutil.copyfile(path, dest / path.name)
    return [p.name for p in copied]


def tool_names_of(text: str) -> list:
    return sorted(set(re.findall(r'"name"\s*:\s*"([A-Za-z_][\w.:-]*)"', text)))


def run_install(args, base: Path) -> int:
    kit = base / 'kit'
    cap = base / 'captures'
    cap.mkdir(parents=True, exist_ok=True)
    home = codex_home(args)
    reads = [('plugin-list', ['plugin', 'list']), ('marketplace-list', ['plugin', 'marketplace', 'list']),
             ('plugin-help', ['plugin', '--help']), ('add-help', ['plugin', 'add', '--help']),
             ('upgrade-help', ['plugin', 'marketplace', 'upgrade', '--help'])]
    fmt = {'kit': kit, 'dup': base / 'kit-dup', 'base': base, 'probe': Path(__file__).resolve()}
    for step, commands in INSTALL_STEPS:
        if commands:
            print(f'Step "{step}": run these commands yourself (they change Codex settings):')
            for command in commands:
                print('  ' + command.format(**fmt))
            try:
                input('Press Enter when done (the probe then saves read-only snapshots): ')
            except EOFError:
                pass
        for name, argv in reads:
            if step != 'initial' and name.endswith('help'):
                continue
            done = call(args.codex, argv)
            write(cap / f'install-{step}-{name}.txt', done.stdout + (f'\n[stderr]\n{done.stderr}' if done.stderr else ''))
            log_line(base, f'install/{step}: {args.codex} {" ".join(argv)} -> exit {done.returncode}')
        for found in sorted(home.glob(f'plugins/cache/{NAME}/**/plugin.json')) if home.is_dir() else []:
            rel = '-'.join(found.relative_to(home / 'plugins' / 'cache').parts[:-1] + (found.parent.name,))
            write(cap / f'install-{step}-cache-{re.sub(r"[^A-Za-z0-9_.-]", "_", rel)}.txt',
                  found.read_text(encoding='utf-8'))
    print('Cleanup (run always):')
    for command in INSTALL_CLEANUP:
        print('  ' + command)
    return 0


def cmd_run(args) -> int:
    base = Path(args.dir).resolve()
    if base == REPO or REPO in base.parents:
        sys.exit(f'refusing to run inside the repository: {base}')
    base.mkdir(parents=True, exist_ok=True)
    if args.scenario == 'install':
        return run_install(args, base)
    if args.scenario in ('skills-live', 'skills-kit'):
        return run_skills(args, base)
    work = base / f'work-{args.scenario}'
    work.mkdir(parents=True, exist_ok=True)
    (base / 'captures').mkdir(parents=True, exist_ok=True)
    version = call(args.codex, ['--version'])
    (base / 'codex-version.txt').write_text(version.stdout, encoding='utf-8')
    log_line(base, f'{args.scenario}: {args.codex} --version -> exit {version.returncode}')
    if args.scenario == 'identity':
        write_workers(base)
    if args.scenario == 'agents':
        # project-level agents folder of the throwaway work folder; never ~/.codex/agents
        for name, extra in PROJECT_AGENTS.items():
            write(work / '.codex' / 'agents' / (name + '.toml'), toml_agent(name, extra))
        done = call(args.codex, ['debug', 'prompt-input', 'hello'], cwd=str(work))
        write(base / 'captures' / 'agents-prompt-input.txt', '\n'.join(tool_names_of(done.stdout)) + '\n')
        log_line(base, f'agents: {args.codex} debug prompt-input -> exit {done.returncode}')
        done = call(args.codex, ['debug', 'models'], cwd=str(work))
        slugs = sorted(set(re.findall(r'"slug"\s*:\s*"([^"]+)"', done.stdout)))
        write(base / 'captures' / 'debug-models.txt', '\n'.join(slugs) + '\n')
        log_line(base, f'agents: {args.codex} debug models -> exit {done.returncode}')
    sandbox = 'workspace-write' if args.scenario == 'identity' else 'read-only'
    argv = ['exec', '--json', '--sandbox', sandbox, '--skip-git-repo-check', '-C', str(work), PROMPTS[args.scenario]]
    env = dict(os.environ, MA_PROBE_SCENARIO=args.scenario)
    done = call(args.codex, argv, cwd=str(work), env=env)
    (base / 'captures' / f'{args.scenario}-events.jsonl').write_text(done.stdout, encoding='utf-8')
    (base / 'captures' / f'{args.scenario}-stderr.txt').write_text(done.stderr, encoding='utf-8')
    log_line(base, f'{args.scenario}: {args.codex} exec --json --sandbox {sandbox} -C {work} -> exit {done.returncode}')
    events = []
    for line in done.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    ids, paths = collect_ids(base, args.scenario, events)
    copied = copy_sessions(ids, paths, codex_home(args) / 'sessions', base / 'sessions' / args.scenario)
    log_line(base, f'{args.scenario}: copied {len(copied)} session record(s) of {len(ids)} id(s)')
    return 0 if done.returncode == 0 else 1


E2E_STEPS = [(1, 'Intake'), (2, 'Explore-Scope'), (3, 'Plan'), (4, 'Plan-Review'), (5, 'Execute'), (6, 'Merge'),
             (7, 'Verify'), (8, 'Review-Deliver')]
E2E_ARGS = '--dev add a function add(a, b) in calc.py that returns the sum of two numbers, with a test'
CALC = 'def sub(a, b):\n    return a - b\n'
CALC_TEST = ('import unittest\n\nfrom calc import sub\n\n\nclass SubTest(unittest.TestCase):\n'
             '    def test_sub(self):\n        self.assertEqual(sub(3, 1), 2)\n\n\nif __name__ == \'__main__\':\n'
             '    unittest.main()\n')


def snapshot_skills(args, out: Path):
    """skills-list/-source/-evidence from `codex debug prompt-input` (the hard source); the raw output is not kept."""
    folder = Path(args.skills)
    done = call(args.codex, ['debug', 'prompt-input', SKILLS_INPUT_PROMPT], cwd=str(folder))
    home = codex_home(args)
    parts = (args.cache or 'my-plugins/my-agent').split('/')
    descs = my_agent_descriptions(home, *(parts if len(parts) == 2 and all(parts) else ['my-plugins', 'my-agent']))
    skills = {'root': descs['root'], 'monitor': descs['monitor']}
    names, lines, total = [], [], 0
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'prompt-input.txt'
        path.write_text(done.stdout, encoding='utf-8')
        entries = all_entries(path)
        total = len(entries)
        matched = [e for e in entries if any(description_matches(e['description'], d) for ds in skills.values() for d in ds)]
        for e in distinct_entries(matched):
            shown = 'unresolved' if e['path'] == 'unresolved' else scrub_text(e['path'], home)
            names.append(e['name'])
            lines.append(f'prompt-input:{e["at"]}  - {e["name"]}: '
                         f'{scrub_text(re.sub(chr(92) + "s+", " ", e["description"]).strip(), home)} (file: {shown})')
    if not lines:
        lines = [f'no listing entry of my-agent was found ({total} listing entries in all)']
    (out / 'skills-list.txt').write_text(''.join(n + '\n' for n in names), encoding='utf-8')
    (out / 'skills-source.txt').write_text(('prompt-input' if total else 'none') + '\n', encoding='utf-8')
    (out / 'skills-evidence.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def cmd_snapshot(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    steps = [('codex-version.txt', ['--version']), ('plugin-list.txt', ['plugin', 'list']),
             ('marketplace-list.txt', ['plugin', 'marketplace', 'list'])]
    for name, argv in steps:
        done = call(args.codex, argv)
        (out / name).write_text(done.stdout + (f'\n[stderr]\n{done.stderr}' if done.stderr else ''), encoding='utf-8')
    if args.skills:
        snapshot_skills(args, out)
    if args.cache:
        parts = args.cache.split('/')
        if len(parts) != 2 or not all(parts):
            sys.exit('--cache takes <marketplace>/<plugin>')
        base = codex_home(args) / 'plugins' / 'cache' / parts[0] / parts[1]
        files = sorted(str(p.relative_to(base)) for p in base.rglob('*') if p.is_file()) if base.is_dir() else []
        (out / 'cache-files.txt').write_text('\n'.join(files), encoding='utf-8')
        for manifest in sorted(base.glob('*/.codex-plugin/plugin.json')):
            dest = out / 'cache' / manifest.parent.parent.name / 'codex-plugin.json'
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(manifest, dest)
    return 0


# ---- summary ----

def read_captures(base: Path) -> list:
    records = []
    for path in sorted((base / 'captures').glob('*.json')):
        try:
            records.append(json.loads(path.read_text(encoding='utf-8')))
        except ValueError:
            continue
    return records


def type_map(obj) -> dict:
    return {k: type(v).__name__ for k, v in obj.items()} if isinstance(obj, dict) else {}


def walk(value):
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def output_seen(events: list, mode: str) -> bool:
    marker = f'ma-probe-{mode}'
    for event in events:
        for node in walk(event):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, str) and ('output' in k or 'stdout' in k) and v.strip() == marker:
                        return True
    return False


def load_events(base: Path) -> list:
    events = []
    for path in sorted((base / 'captures').glob('*-events.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def hash_candidates(hook: dict, entry: dict) -> dict:
    def dumps(o, **kw):
        return json.dumps(o, **kw).encode()
    return {
        'sorted-compact-hook': dumps(hook, sort_keys=True, separators=(',', ':')),
        'compact-hook': dumps(hook, separators=(',', ':')),
        'sorted-compact-entry': dumps(entry, sort_keys=True, separators=(',', ':')),
        'command-only': hook.get('command', '').encode(),
    }


def trust_entries(config: Path, kit_hooks: Path) -> tuple:
    if not config.is_file():
        return [], None
    state = tomllib.loads(config.read_text(encoding='utf-8')).get('hooks', {}).get('state', {})
    entries = [{'key': k, 'trusted_hash': v.get('trusted_hash')} for k, v in state.items()
               if k.startswith(NAME + '@') and isinstance(v, dict)]
    recomputed = None
    if kit_hooks.is_file() and entries:
        hooks = json.loads(kit_hooks.read_text(encoding='utf-8'))['hooks']
        by_snake = {re.sub(r'(?<!^)(?=[A-Z])', '_', ev).lower(): v for ev, v in hooks.items()}
        for item in entries:
            m = re.search(r':([a-z_]+):(\d+):(\d+)$', item['key'])
            if not m or m.group(1) not in by_snake:
                continue
            try:
                entry = by_snake[m.group(1)][int(m.group(2))]
                hook = entry['hooks'][int(m.group(3))]
            except (IndexError, KeyError):
                continue
            want = (item['trusted_hash'] or '').split(':')[-1]
            for name, data in hash_candidates(hook, entry).items():
                if hashlib.sha256(data).hexdigest() == want:
                    recomputed = name
                    break
            if recomputed:
                break
    return entries, recomputed


def cmd_summary(args) -> int:
    base = Path(args.dir).resolve()
    out = Path(args.out)
    records = read_captures(base)
    events = load_events(base)
    fields, shapes, tools, ids, env_names, env_values, roots = {}, {}, set(), set(), set(), {}, set()
    for rec in records:
        stdin = rec.get('stdin_json')
        label = rec.get('label')
        if isinstance(stdin, dict):
            fields.setdefault(label, {}).update(type_map(stdin))
            ids.update(k for k in stdin if k == 'cwd' or k == 'id' or k.endswith('_id'))
            name = stdin.get('tool_name')
            if isinstance(name, str):
                tools.add(name)
                shapes.setdefault(name, {}).update(type_map(stdin.get('tool_input')))
        env_names.update(rec.get('env_names', []))
        for k, v in rec.get('env_values', {}).items():
            if not SECRET.search(k):
                env_values.setdefault(k, v)
        argv = rec.get('argv', [])
        if len(argv) > 1:
            roots.add(argv[1])
    markers = {}
    for mode in MARKERS:
        text = f'echo ma-probe-{mode}'
        markers[mode] = {
            'hook_fired': any(r.get('label') == 'marker-' + mode for r in records),
            'post_tool_use_seen': any(r.get('label') == 'PostToolUse' and text in json.dumps(r.get('stdin_json'))
                                      for r in records),
            'output_seen': output_seen(events, mode),
        }
    entries, recomputed = trust_entries(Path(args.config).expanduser(),
                                        base / 'kit' / 'plugins' / NAME / 'hooks' / 'hooks.json')
    version_file = base / 'codex-version.txt'
    summary = {
        'codex_version': version_file.read_text(encoding='utf-8').strip() if version_file.is_file() else None,
        'events_seen': sorted(fields.keys() | {r.get('label') for r in records}),
        'fields': fields,
        'tool_names': sorted(tools),
        'tool_input_shapes': shapes,
        'id_fields': sorted(ids),
        'env_var_names': sorted(env_names),
        'env_values': env_values,
        'plugin_root': {'values': sorted(roots),
                        'expanded': any(r and '${' not in r for r in roots)},
        'markers': markers,
        'trust': {
            'hooks_ran_in_hooks_scenario': any(r.get('scenario') == 'hooks' for r in records),
            'hooks_ran_in_stale_scenario': any(r.get('scenario') == 'stale' for r in records),
            'bumped_hook_ran_in_stale': any(r.get('scenario') == 'stale' and 'bumped' in r.get('argv', [])
                                            for r in records),
            'config_entries': entries,
            'hash_recomputed_by': recomputed,
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary-hooks.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    cap_out = out / 'captures'
    cap_out.mkdir(exist_ok=True)
    for path in sorted((base / 'captures').glob('*.json')):
        try:
            rec = json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            continue
        rec['stdin_json'] = redact(rec.get('stdin_json'))
        rec['env_values'] = {k: v for k, v in rec.get('env_values', {}).items() if not SECRET.search(k)}
        (cap_out / path.name).write_text(json.dumps(rec, indent=1), encoding='utf-8')
    for path in sorted((base / 'captures').glob('*-events.jsonl')):
        lines = []
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                lines.append(json.dumps(redact(json.loads(line))))
            except ValueError:
                continue
        (cap_out / path.name).write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    if (base / 'run.log').is_file():
        shutil.copyfile(base / 'run.log', out / 'run.log')
    write_agents_summary(base, out, records, Path(args.config).expanduser())
    return 0


# ---- agents / skills / session / install summary ----

KEEP_KEY = re.compile(r'(^|_)(id|type|model|role|name|effort|kind|source|slug)$', re.I)
TOKEN_KEY = re.compile(r'tokens?', re.I)
COST_KEY = re.compile(r'cost|usd|price', re.I)
PARENT_PATH = re.compile(r'parent|fork|subagent|spawn|source', re.I)


def reduce_value(value, key=''):
    """Keep structure, numbers and id/type/model-like strings; every other string becomes a placeholder."""
    if isinstance(value, dict):
        return {k: reduce_value(v, k) for k, v in value.items()
                if not (SECRET.search(k) and isinstance(v, str))}
    if isinstance(value, list):
        return [reduce_value(v, key) for v in value[:20]]
    if isinstance(value, str):
        return value if KEEP_KEY.search(key) and len(value) <= 80 else '<str>'
    return value


def leaf_paths(value, prefix=''):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaf_paths(v, f'{prefix}.{k}' if prefix else k)
    elif isinstance(value, list):
        for v in value:
            yield from leaf_paths(v, prefix + '[]')
    else:
        yield prefix, value


def session_summary(files: list) -> dict:
    types, ids, models, tokens, token_fields, costs, parents, model_ids = set(), set(), set(), set(), set(), set(), set(), set()
    lines = 0
    for path in files:
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            lines += 1
            kind = obj.get('type') if isinstance(obj, dict) and isinstance(obj.get('type'), str) else '?'
            types.add(kind)
            for leaf, val in leaf_paths(obj):
                last = re.sub(r'\[\]', '', leaf.split('.')[-1])
                where = f'{kind}:{leaf}'
                if last == 'id' or ID_KEY.search(last):
                    ids.add(where)
                if last == 'model':
                    models.add(where)
                    if isinstance(val, str):
                        model_ids.add(val)
                if TOKEN_KEY.search(last):
                    tokens.add(where)
                    token_fields.add(last)
                if COST_KEY.search(last):
                    costs.add(where)
                if PARENT_PATH.search(leaf) and last != 'model':
                    parents.add(where)
    return {'files': len(files), 'lines': lines, 'line_types': sorted(types), 'id_paths': sorted(ids),
            'model_paths': sorted(models), 'model_ids': sorted(model_ids), 'token_paths': sorted(tokens),
            'token_fields': sorted(token_fields), 'cost_paths': sorted(costs), 'parent_links': sorted(parents)}


def agent_message_texts(events: list) -> list:
    return [n['text'] for e in events for n in walk(e)
            if isinstance(n, dict) and n.get('type') == 'agent_message' and isinstance(n.get('text'), str)]


def read_events(path: Path) -> list:
    out = []
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def parse_expansions(texts: list) -> dict:
    found = {}
    for text in texts:
        for line in text.splitlines():
            if 'MA-PROBE-EXPAND' not in line:
                continue
            for key, val in re.findall(r'(\w+)=<(.*?)>', line):
                literal = {'skill_dir': '${CLAUDE_SKILL_DIR}', 'plugin_root': '${CLAUDE_PLUGIN_ROOT}',
                           'arguments': '$ARGUMENTS', 'opt': '${user_config.probe_opt}'}.get(key)
                found.setdefault(key, {'value_kind': 'expanded' if val != literal else 'literal',
                                       'empty': val == ''})
    return found


def session_texts(base: Path, scenario: str, needle: str) -> list:
    """Strings of the scenario's session records that contain the needle (the text Codex gave the model)."""
    out = []
    folder = base / 'sessions' / scenario
    for path in sorted(folder.glob('*.jsonl')) if folder.is_dir() else []:
        for obj in read_events(path):
            out += [n for n in walk(obj) if isinstance(n, str) and needle in n]
    return out


def skills_summary(base: Path, records: list) -> dict:
    events = read_events(base / 'captures' / 'skills-events.jsonl')
    texts = agent_message_texts(events)
    from_sessions = parse_expansions(session_texts(base, 'skills', 'MA-PROBE-EXPAND'))
    blob = json.dumps(events)
    tools = sorted({r['stdin_json'].get('tool_name') for r in records
                    if r.get('scenario') == 'skills' and isinstance(r.get('stdin_json'), dict)
                    and isinstance(r['stdin_json'].get('tool_name'), str)})
    return {'ran': bool(events) or bool(from_sessions), 'root_skill_seen': 'ma-probe-root' in blob, 'dir_skill_seen': 'ma-probe-dir' in blob,
            'tools_used': tools, 'expansions': from_sessions or parse_expansions(texts),
            'expansions_source': 'session records' if from_sessions else 'model answer',
            'answer_head': [t[:300] for t in texts[:2]]}


def agents_summary(base: Path, records: list) -> dict:
    events = read_events(base / 'captures' / 'agents-events.jsonl')
    blob = json.dumps(events)
    mine = [r for r in records if r.get('scenario') == 'agents' and isinstance(r.get('stdin_json'), dict)]
    prompt_blob = (base / 'captures' / 'agents-prompt-input.txt').read_text(encoding='utf-8') \
        if (base / 'captures' / 'agents-prompt-input.txt').is_file() else ''
    spawn = [r for r in mine if r.get('label') == 'PreToolUse'
             and any(n in json.dumps(r['stdin_json'].get('tool_input')) for n in AGENT_NAMES)]
    stderr_path = base / 'captures' / 'agents-stderr.txt'
    stderr_text = stderr_path.read_text(encoding='utf-8') if stderr_path.is_file() else ''
    unknown = sorted(set(re.findall(r"unknown agent_type '?([\w:.-]+)", blob + '\n' + stderr_text)) & set(AGENT_NAMES))
    any_unknown = 'unknown agent_type' in blob or 'unknown agent_type' in stderr_text
    n_starts = len([r for r in mine if r.get('label') == 'SubagentStart'])
    # loaded = named in the events and not rejected; a rejection with no subagent ever started rejects all
    seen_names = {n: ((n in blob or any(n in json.dumps(r['stdin_json'].get('tool_input')) for r in spawn))
                      and n not in unknown and not (any_unknown and n_starts == 0))
                  for n in AGENT_NAMES}
    inputs = {}
    for r in spawn:
        inputs.update(type_map(r['stdin_json'].get('tool_input')))
    ident, sub_events = {}, {}
    for r in mine:
        keys = {k: type(v).__name__ for k, v in r['stdin_json'].items() if re.search(r'agent|parent|thread|subagent', k, re.I)}
        if keys:
            ident.setdefault(r['label'], {}).update(keys)
        if r.get('label') in ('SubagentStart', 'SubagentStop'):
            sub_events.setdefault(r['label'], {}).update(type_map(r['stdin_json']))
    post = [r for r in mine if r.get('label') == 'PostToolUse'
            and r['stdin_json'].get('tool_name') in {x['stdin_json'].get('tool_name') for x in spawn}]
    starts = sorted(r['time'] for r in mine if r.get('label') == 'SubagentStart')
    stops = sorted(r['time'] for r in mine if r.get('label') == 'SubagentStop')
    warnings = [ln.strip()[:200] for ln in stderr_path.read_text(encoding='utf-8').splitlines()
                if re.search(r'ignor|unknown|invalid|unsupported|unrecognized|error', ln, re.I)][:20] \
        if stderr_path.is_file() else []
    return {'ran': bool(events), 'names_seen': seen_names, 'unknown_agent_types': unknown,
            'spawn_tool_names': sorted({r['stdin_json'].get('tool_name') for r in spawn}),
            'spawn_tool_input_fields': inputs,
            'per_call_model_or_effort': sorted(k for k in inputs if re.search(r'model|effort|reasoning', k, re.I)),
            'identity_fields': ident, 'subagent_event_fields': sub_events,
            'handback_fields': sorted({k for r in post for k in (r['stdin_json'].get('tool_response') or {})}
                                      if post and isinstance(post[0]['stdin_json'].get('tool_response'), dict) else []),
            'subagent_starts': len(starts), 'subagent_stops': len(stops),
            'parallel_overlap': len(starts) > 1 and bool(stops) and starts[1] < stops[0],
            'stderr_warnings': warnings, 'prompt_input_tool_names': [x for x in prompt_blob.split('\n') if x]}


def main_tools_summary(base: Path, records: list) -> dict:
    names = set()
    path = base / 'captures' / 'agents-prompt-input.txt'
    if path.is_file():
        names.update(x for x in path.read_text(encoding='utf-8').split('\n') if x)
    names.update(r['stdin_json']['tool_name'] for r in records if isinstance(r.get('stdin_json'), dict)
                 and isinstance(r['stdin_json'].get('tool_name'), str))
    def pick(pattern):
        return sorted(n for n in names if re.search(pattern, n, re.I))
    return {'names': sorted(names), 'question_tool': pick(r'ask|question|user_input|request_user'),
            'plan_tool': pick(r'plan|todo'), 'web_tools': pick(r'web|search|fetch|browse'),
            'worktree': pick(r'worktree')}


def install_summary(base: Path) -> dict:
    cap = base / 'captures'
    steps = {}
    for path in sorted(cap.glob('install-*.txt')):
        m = re.match(r'install-([a-z]+)-(.*)\.txt$', path.name)
        if m:
            steps.setdefault(m.group(1), {})[m.group(2)] = path.read_text(encoding='utf-8')
    def has(step, marker):
        return any(marker in text for name, text in steps.get(step, {}).items())
    def seen(step):
        return {k: has(step, v) for k, v in {**{'plugin_' + a: b for a, b in DESC.items()},
                                              **{'market_' + a: b for a, b in MARKET_DESC.items()}}.items()}
    dup = steps.get('dup', {}).get('marketplace-list', '')
    return {'ran': bool(steps), 'steps': sorted(steps),
            'markers_by_step': {step: seen(step) for step in steps},
            'manifest_read': ('both' if has('added', DESC['claude']) and has('added', DESC['codex'])
                              else 'claude' if has('added', DESC['claude'])
                              else 'codex' if has('added', DESC['codex']) else None),
            'market_file_read': ('claude' if has('added', MARKET_DESC['claude']) else
                                 'codex' if has('added', MARKET_DESC['codex']) else None),
            'reread_at_plugin_add': has('changed', MARKET_DESC['changed']) if 'changed' in steps else None,
            'refreshed_by_upgrade': has('upgraded', MARKET_DESC['changed']) if 'upgraded' in steps else None,
            'dup_marketplace_count': dup.count(NAME) if 'dup' in steps else None,
            'plugin_list_added_head': steps.get('added', {}).get('plugin-list', '')[:600] or None,
            'plugin_help_head': steps.get('initial', {}).get('plugin-help', '')[:600] or None}


def write_agents_summary(base: Path, out: Path, records: list, config: Path):
    cap_out = out / 'captures'
    sessions = {}
    for sdir in sorted((base / 'sessions').glob('*')) if (base / 'sessions').is_dir() else []:
        reduced = []
        for i, path in enumerate(sorted(sdir.glob('*.jsonl'))):
            lines = []
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    lines.append(json.dumps(reduce_value(json.loads(line))))
                except ValueError:
                    continue
            target = cap_out / f'session-{sdir.name}-{i + 1}.reduced.jsonl'
            target.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
            reduced.append(target)
        if reduced:
            sessions[sdir.name] = session_summary(reduced)
    merged = session_summary([p for p in sorted(cap_out.glob('session-*.reduced.jsonl'))])
    models_file = base / 'captures' / 'debug-models.txt'
    default_model = None
    if config.is_file():
        default_model = tomllib.loads(config.read_text(encoding='utf-8')).get('model')
    summary = {
        'skills': skills_summary(base, records), 'agents': agents_summary(base, records),
        'main_tools': main_tools_summary(base, records),
        'session_record': {**merged, 'by_scenario': {k: v['files'] for k, v in sessions.items()},
                           'models_listed': [x for x in models_file.read_text(encoding='utf-8').split('\n') if x]
                           if models_file.is_file() else [], 'default_model_setting': default_model},
        'install': install_summary(base)}
    (out / 'summary-agents.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for path in sorted((base / 'captures').glob('*.txt')):
        if path.name.endswith('-stderr.txt') or path.name == 'codex-version.txt':
            continue
        shutil.copyfile(path, cap_out / path.name)


# ---- identity summary / findings ----

CALL_FIELDS = ['session_id', 'transcript_path', 'turn_id', 'cwd']
START_FIELDS = ['agent_id', 'session_id', 'transcript_path', 'turn_id']
STOP_FIELDS = ['agent_transcript_path']
# marker text of a tool call -> (who, kind); a call is attributed by this text, not by an identity field
ATTRIBUTION = ([('main', 'shell', 'ma-probe-main-shell'), ('main', 'file', 'main-note.txt')]
               + [('main', 'file', f'{m}-main') for m in FILE_FORMS.values()]
               + [('a', 'shell', 'ma-probe-sub-a-shell'), ('a', 'file', 'sub-a-note.txt')]
               + [('a', 'file', f'{m}-a') for m in FILE_FORMS.values()]
               + [('b', 'shell', 'ma-probe-sub-b-shell'), ('b', 'file', 'sub-b-note.txt')]
               + [('b', 'file', f'{m}-b') for m in FILE_FORMS.values()]
               + [('worker', 'shell', 'echo ma-probe-deny'), ('worker', 'shell', 'echo ma-probe-exit')])
ID_VALUE_KEY = re.compile(r'(^id$|_id$|_path$|^cwd$)')
PATCH_TARGET = re.compile(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', re.M)
DENY_CASES = {'worker_shell_deny': r'echo ma-probe-deny(?!-)', 'worker_shell_exit2': r'echo ma-probe-exit2',
              'worker_shell_exit1': r'echo ma-probe-exit1'}
FILE_CASES = {}  # form -> {'main': case, 'a': case, 'b': case}
for _form, _marker in FILE_FORMS.items():
    FILE_CASES[_form] = {'main': f'main_file_{_form}', 'a': f'worker_a_file_{_form}', 'b': f'worker_b_file_{_form}'}
    for _who, _case in FILE_CASES[_form].items():
        DENY_CASES[_case] = rf'{_marker}-{_who}'
DENY_OUTPUT = {'worker_shell_deny': 'deny', 'worker_shell_exit2': 'exit2', 'worker_shell_exit1': 'exit1'}
N_DENY_CASES = ['worker_shell_deny', 'worker_shell_exit2']


def read_capture_files(base: Path) -> list:
    out = []
    for path in sorted((base / 'captures').glob('*.json')):
        try:
            out.append((path.name, json.loads(path.read_text(encoding='utf-8'))))
        except ValueError:
            continue
    return out


def attribute(text: str):
    for who, kind, marker in ATTRIBUTION:
        if marker in text:
            return who, kind
    return None, None


def when(rec: dict):
    try:
        return datetime.fromisoformat(rec.get('time'))
    except (TypeError, ValueError):
        return None


def targets_of(tool_input, roots: list) -> list:
    found = []
    for node in walk(tool_input):
        if isinstance(node, str):
            found += PATCH_TARGET.findall(node)
        elif isinstance(node, dict):
            found += [v for k, v in node.items() if isinstance(v, str) and re.fullmatch(r'(file_?path|path|file|filename)', k, re.I)]
    out = []
    for item in found:
        path = Path(item.strip())
        if path.is_absolute():
            for root in roots:
                try:
                    path = path.relative_to(root)
                    break
                except ValueError:
                    continue
            else:
                path = Path('<outside>') / path.name
        out.append(str(path))
    return sorted(set(out))


def evaluate_pair(call_field, source_event, source_field, sources, worker_calls, main_calls, starts):
    """Booleans for one (call field, source field) pair; the matched source record is found by value."""
    res = {'call_field': call_field, 'source_event': source_event, 'source_field': source_field}
    matched, values = {}, {}
    for w in ('a', 'b'):
        calls_w = worker_calls[w]
        have = [c['stdin'].get(call_field) for c in calls_w]
        src = None
        if calls_w and all(isinstance(v, str) and v for v in have) and len(set(have)) == 1:
            src = next((s for s in sources if s['stdin'].get(source_field) == have[0]), None)
        matched[w], values[w] = src, (have[0] if src else None)
        res['equal_on_every_call_' + w] = src is not None
    res['different_between_workers'] = bool(matched['a'] and matched['b'] and values['a'] != values['b'])
    seen = {v for v in values.values() if v}
    res['equal_on_a_main_call'] = any(c['stdin'].get(call_field) in seen for c in main_calls)
    for w in ('a', 'b'):
        first = min((when(c['rec']) for c in worker_calls[w] if when(c['rec'])), default=None)
        start = matched[w]
        if start is not None and source_event == 'SubagentStop':
            ident = start['stdin'].get('agent_id')
            start = next((s for s in starts if ident and s['stdin'].get('agent_id') == ident), None)
        res['start_before_first_call_' + w] = bool(start and first and when(start['rec']) and when(start['rec']) < first)
    res['qualifies'] = (res['equal_on_every_call_a'] and res['equal_on_every_call_b'] and res['different_between_workers']
                        and not res['equal_on_a_main_call'] and res['start_before_first_call_a']
                        and res['start_before_first_call_b'])
    return res


def file_present(work: Path, pattern: str) -> bool:
    return work.is_dir() and any(work.rglob(pattern))


def identity_summary(base: Path) -> dict:
    work = base / 'work-identity'
    roots = [work, work.resolve()]
    files = [(n, r) for n, r in read_capture_files(base) if r.get('scenario') == 'identity' and isinstance(r.get('stdin_json'), dict)]
    events = read_events(base / 'captures' / 'identity-events.jsonl')
    calls, posts, starts, stops = [], [], [], []
    for name, rec in files:
        stdin = rec['stdin_json']
        item = {'name': name, 'rec': rec, 'stdin': stdin}
        text = json.dumps(stdin.get('tool_input', {}))
        if rec.get('label') == 'PreToolUse' and isinstance(stdin.get('tool_name'), str):
            item['who'], item['kind'] = attribute(text)
            calls.append(item)
        elif rec.get('label') == 'PostToolUse':
            item['text'] = text
            posts.append(item)
        elif rec.get('label') == 'SubagentStart':
            starts.append(item)
        elif rec.get('label') == 'SubagentStop':
            stops.append(item)
    attributed = [c for c in calls if c['who']]
    by_who = {w: [c for c in attributed if c['who'] == w] for w in ('main', 'a', 'b', 'worker')}
    worker_all = by_who['a'] + by_who['b'] + by_who['worker']

    def shape(c):
        stdin = c['stdin']
        agent_type = stdin.get('agent_type')
        want = f'ma_probe_worker_{c["who"]}' if c['who'] in ('a', 'b') else None
        return {'capture': c['name'], 'who': c['who'], 'kind': c['kind'], 'event': c['rec'].get('label'),
                'tool_name': stdin.get('tool_name'), 'input_fields': type_map(stdin.get('tool_input')),
                'agent_id_present': 'agent_id' in stdin, 'agent_type_present': 'agent_type' in stdin,
                'agent_id_nonempty': isinstance(stdin.get('agent_id'), str) and bool(stdin.get('agent_id')),
                'agent_type_is_worker': isinstance(agent_type, str) and (agent_type == want if want else agent_type in WORKERS)}
    shapes = [shape(c) for c in attributed]

    def file_group(items):
        calls_f = [c for c in items if c['kind'] == 'file']
        return {'tool_names': sorted({c['stdin']['tool_name'] for c in calls_f}),
                'input_fields': {k: v for c in calls_f for k, v in type_map(c['stdin'].get('tool_input')).items()},
                'targets': sorted({x for c in calls_f for x in targets_of(
                    c['stdin'].get('tool_input'), roots + [Path(c['stdin'].get('cwd') or '/nonexistent')])}),
                'capture': calls_f[0]['name'] if calls_f else None}
    file_change = {'main': file_group(by_who['main']), 'worker': file_group(worker_all)}

    links = []
    for cf in CALL_FIELDS:
        for sf in START_FIELDS:
            links.append(evaluate_pair(cf, 'SubagentStart', sf, starts, by_who, by_who['main'], starts))
        for sf in STOP_FIELDS:
            links.append(evaluate_pair(cf, 'SubagentStop', sf, stops, by_who, by_who['main'], starts))
    qualifying = [x for x in links if x['qualifies']]
    before = {}
    for w in ('a', 'b'):
        if qualifying:
            before[w] = qualifying[0]['start_before_first_call_' + w]
            continue
        start = next((s for s in starts if s['stdin'].get('agent_type') == f'ma_probe_worker_{w}'), None)
        first = min((when(c['rec']) for c in by_who[w] if when(c['rec'])), default=None)
        before[w] = bool(when(start['rec']) and when(start['rec']) < first) if start and first and when(start['rec']) else None

    deny, deny_capture = {}, None
    for case, pattern in DENY_CASES.items():
        hit = [c for c in calls if re.search(pattern, json.dumps(c['stdin'].get('tool_input', {})))]
        if not hit:
            deny[case] = None
            continue
        deny_capture = deny_capture or hit[0]['name']
        ran = any(re.search(pattern, p['text']) for p in posts)
        if case in DENY_OUTPUT:
            ran = ran or output_seen(events, DENY_OUTPUT[case])
        else:
            ran = ran or file_present(work, pattern + '*')
        deny[case] = not ran

    post_hits = [p for p in posts if p['stdin'].get('tool_name') == 'apply_patch'
                 or (p['kind'] if 'kind' in p else attribute(p['text'])[1]) == 'file']
    post_file_change = {'seen': bool(post_hits), 'capture': post_hits[0]['name'] if post_hits else None,
                        'tool_names': sorted({p['stdin'].get('tool_name') for p in post_hits
                                              if isinstance(p['stdin'].get('tool_name'), str)}),
                        'input_fields': type_map(post_hits[0]['stdin'].get('tool_input')) if post_hits else {}}

    matchers = {}
    for label, (event, matcher) in MATCHERS.items():
        hit = [(n, r) for n, r in files if r.get('label') == label]
        matchers[label] = {'matcher': matcher, 'event': event, 'fired': bool(hit),
                           'tool_names': sorted({r['stdin_json'].get('tool_name') for _, r in hit
                                                 if isinstance(r['stdin_json'].get('tool_name'), str)}),
                           'agent_types': sorted({r['stdin_json'].get('agent_type') for _, r in hit
                                                  if isinstance(r['stdin_json'].get('agent_type'), str)}),
                           'capture': hit[0][0] if hit else None}

    all_records = [r for _, r in read_capture_files(base)]
    agents = agents_summary(base, all_records)
    version = base / 'codex-version.txt'
    summary = {
        'codex_version': version.read_text(encoding='utf-8').strip() if version.is_file() else None,
        'hooks_ran': bool(files),
        'calls': shapes,
        'file_change': file_change,
        'deny_honored': deny,
        'file_deny': file_deny_forms(deny),
        'post_tool_use_file_change': post_file_change,
        'links': links,
        'start_before_first_call': before,
        'matchers': matchers,
        'agents': {'names_seen': agents['names_seen'], 'locations': AGENT_LOCATIONS,
                   'unknown_agent_types': agents['unknown_agent_types'],
                   'warnings': agents['stderr_warnings'], 'ran': agents['ran']},
        'skills': skills_summary(base, all_records),
        'capture_refs': {
            'subagent_calls': next((c['name'] for c in worker_all if c['kind'] == 'shell'), None),
            'file_change': file_change['worker']['capture'] or file_change['main']['capture'],
            'deny': deny_capture,
            'identity_link': starts[0]['name'] if starts else None,
            'matchers': next((m['capture'] for m in matchers.values() if m['capture']), None),
            'agents': 'agents-events.jsonl' if (base / 'captures' / 'agents-events.jsonl').is_file() else None,
            'skills': 'skills-events.jsonl' if (base / 'captures' / 'skills-events.jsonl').is_file() else None},
    }
    summary['outcome'] = decide_outcome(summary, by_who, events, work)
    return summary


def file_deny_forms(deny: dict) -> dict:
    """Per form: honored (marked file absent) by the main session and by every worker call that was made."""
    out = {}
    for form, cases in FILE_CASES.items():
        workers = [deny.get(cases['a']), deny.get(cases['b'])]
        out[form] = {'main': deny.get(cases['main']), 'worker_a': workers[0], 'worker_b': workers[1],
                     'honored': deny.get(cases['main']) is True and any(w is True for w in workers)
                     and not any(w is False for w in workers)}
    return out


def shell_evidence(events: list) -> bool:
    """A command_execution item that ran a worker marker command, whether or not a hook saw it."""
    return any(isinstance(n, dict) and isinstance(n.get('command'), str) and 'ma-probe-sub-' in n['command']
               for e in events for n in walk(e))


def decide_outcome(summary: dict, by_who: dict, events: list, work: Path) -> str:
    if not summary['hooks_ran']:
        return 'Outcome: open hooks did not run (no capture of the identity scenario)'
    bad = [c for c in N_DENY_CASES if summary['deny_honored'].get(c) is False]
    if bad:
        return 'Outcome: N deny not honored: ' + ', '.join(bad)
    honored = [f for f, v in summary['file_deny'].items() if v['honored']]
    suffix = f' file-deny={honored[0]}' if honored else ''
    if not honored:
        refused = [c for cases in FILE_CASES.values() for c in cases.values() if summary['deny_honored'].get(c) is False]
        if refused:
            return 'Outcome: N deny not honored: ' + ', '.join(refused)
    worker_all = by_who['a'] + by_who['b'] + by_who['worker']
    if not worker_all:
        if shell_evidence(events):
            return 'Outcome: N no PreToolUse for worker calls'
        return 'Outcome: open no worker tool call was made'
    missing = [w for w in ('a', 'b') if not by_who[w]]
    if missing:
        return 'Outcome: open no tool call from worker ' + ', '.join(missing)
    unseen = [w for w in ('a', 'b') if file_present(work, f'sub-{w}-note.txt')
              and not any(c['kind'] == 'file' for c in by_who[w])]
    if unseen:
        return 'Outcome: N no PreToolUse for file-change calls of worker ' + ', '.join(unseen)
    if not any(c['kind'] == 'file' for c in worker_all):
        return 'Outcome: open no file-change tool call from a worker'
    shapes = [s for s in summary['calls'] if s['who'] != 'main']
    if all(s['agent_id_nonempty'] and s['agent_type_is_worker'] for s in shapes):
        return 'Outcome: I' + suffix
    for link in summary['links']:
        if link['qualifies']:
            return f'Outcome: L {link["call_field"]}={link["source_field"]}' + suffix
    return 'Outcome: N no field pair links a worker call to its SubagentStart'


def tokenize(value, table: dict):
    """Replace id-like string values by stable placeholders, so equality survives but values do not."""
    if isinstance(value, dict):
        return {k: (table.setdefault((k, v), f'<{k}#{len(table) + 1}>') if ID_VALUE_KEY.search(k) and isinstance(v, str)
                    else tokenize(v, table)) for k, v in value.items()}
    if isinstance(value, list):
        return [tokenize(v, table) for v in value]
    return value


def scrub(text: str, base: Path) -> str:
    for path, token in ((str(base / 'work-identity'), '<work>'), (str(Path.home()), '<home>')):
        text = text.replace(path, token)
    return text


def cmd_summary_identity(args) -> int:
    base = Path(args.dir).resolve()
    out = Path(args.out) / 'probe-identity'
    cap_out = out / 'captures'
    cap_out.mkdir(parents=True, exist_ok=True)
    summary = identity_summary(base)
    (out / 'summary-identity.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    table = {}
    for name, rec in read_capture_files(base):
        if rec.get('scenario') != 'identity':
            continue
        reduced = {'label': rec.get('label'), 'time': rec.get('time'), 'scenario': 'identity',
                   'stdin_json': tokenize(redact(rec.get('stdin_json')), table)}
        (cap_out / name).write_text(scrub(json.dumps(reduced, indent=1), base) + '\n', encoding='utf-8')
    for name in ('identity-events.jsonl', 'agents-events.jsonl', 'skills-events.jsonl'):
        if (base / 'captures' / name).is_file():
            lines = [scrub(json.dumps(tokenize(redact(e), table)), base) for e in read_events(base / 'captures' / name)]
            (cap_out / name).write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    names = base / 'captures' / 'agents-prompt-input.txt'
    if names.is_file():
        shutil.copyfile(names, cap_out / names.name)
    if (base / 'run.log').is_file():
        (out / 'run.log').write_text(scrub((base / 'run.log').read_text(encoding='utf-8'), base), encoding='utf-8')
    print(f'{summary["outcome"]} -> {out / "summary-identity.json"}')
    return 0


IDENTITY_SECTIONS = ['Subagent tool calls', 'File-change tool', 'Deny and fail-closed on subagent and file-change calls',
                     'Identity link', 'Matcher semantics', 'Agent names and locations', 'Skill text expansion',
                     'Outcome', 'Open']


def cmd_findings_identity(args) -> int:
    out = Path(args.folder).resolve()
    sdir = out / 'probe-identity'
    summary = load_json(sdir / 'summary-identity.json')
    refs = summary.get('capture_refs') or {}

    def cap(key):
        return f'probe-identity/captures/{refs[key]}' if refs.get(key) and (sdir / 'captures' / refs[key]).is_file() else None
    groups = {}
    for call in summary.get('calls') or []:
        key = (call['who'], call['kind'], call['tool_name'])
        groups.setdefault(key, {k: call[k] for k in ('input_fields', 'agent_id_present', 'agent_type_present',
                                                    'agent_id_nonempty', 'agent_type_is_worker')})
    qualifying = [f'{x["call_field"]}={x["source_field"]}' for x in summary.get('links') or [] if x['qualifies']]
    fired = {k: v['tool_names'] or v['agent_types'] for k, v in (summary.get('matchers') or {}).items() if v['fired']}
    agents = summary.get('agents') or {}
    skills = summary.get('skills') or {}
    changes = summary.get('file_change') or {}
    rows = [
        ('Subagent tool calls', 'Hooks ran in the identity scenario', cap('subagent_calls') or cap('identity_link'), 'u5, u7, u9',
         summary.get('hooks_ran')),
        ('Subagent tool calls', 'Attributed calls by who, kind and tool (fields; agent_id/agent_type presence)',
         cap('subagent_calls'), 'u5, u7, u9, u20',
         {f'{w}/{k}/{n}': v for (w, k, n), v in sorted(groups.items())} or None),
        ('File-change tool', 'File-change tool name, input shape and targets (main and worker)', cap('file_change'),
         'u5, u9, u20', changes if any(g['tool_names'] for g in changes.values()) else None),
        ('Deny and fail-closed on subagent and file-change calls', 'Deny honored per case (true = blocked)', cap('deny'),
         'u5, u9, u20', {k: v for k, v in (summary.get('deny_honored') or {}).items() if v is not None} or None),
        ('Deny and fail-closed on subagent and file-change calls',
         'File-change deny per form (honored = marked file absent for main and workers)', cap('deny'), 'u5, u9, u20',
         {k: v for k, v in (summary.get('file_deny') or {}).items()
          if any(v[w] is not None for w in ('main', 'worker_a', 'worker_b'))} or None),
        ('File-change tool', 'PostToolUse seen on file-change calls', cap('file_change'), 'u5, u9',
         summary.get('post_tool_use_file_change') if (summary.get('post_tool_use_file_change') or {}).get('seen') else None),
        ('Identity link', 'Field pairs that link a worker call to its SubagentStart (booleans only)', cap('identity_link'),
         'u7, u9, u20', {'qualifying': qualifying, 'start_before_first_call': summary.get('start_before_first_call'),
                         'pairs_checked': len(summary.get('links') or [])} if summary.get('links') else None),
        ('Matcher semantics', 'Matcher hooks that fired, with the tool names or agent types they saw', cap('matchers'),
         'u6, u9, u10', fired or None),
        ('Agent names and locations', 'Which renamed agents Codex loaded, and where each was placed', cap('agents'), 'u8, u10',
         {'loaded': agents.get('names_seen'), 'unknown': agents.get('unknown_agent_types'),
          'locations': agents.get('locations')} if agents.get('ran') else None),
        ('Skill text expansion', 'Skill text variables as Codex gave them to the model', cap('skills'), 'u8, u11',
         {'source': skills.get('expansions_source'), 'expansions': skills.get('expansions')}
         if skills.get('expansions') else None),
    ]
    by_section = {name: [] for name in IDENTITY_SECTIONS}
    settled, opened = [], []
    for section, fact, capture, units, value in rows:
        has_value = present(value) or value is False
        if has_value and capture:
            settled.append({'section': section, 'fact': fact, 'value': value, 'capture': capture, 'used_by': units})
            by_section[section].append(f'- {fact}: `{fmt_value(value)}` (`{capture}`)')
        else:
            opened.append({'section': section, 'fact': fact, 'used_by': units,
                           'why': 'no capture file found' if has_value else 'no value in the summary'})
    outcome = summary.get('outcome') or 'Outcome: open no summary-identity.json'
    lines = ['# Codex findings: subagent identity', '', f'Codex version: {summary.get("codex_version") or "unknown"}', '']
    for section in IDENTITY_SECTIONS:
        lines += [f'## {section}', '']
        if section == 'Outcome':
            lines.append(outcome)
        elif section == 'Open':
            lines += [f'- {o["fact"]} ({o["section"]}; needed by {o["used_by"]}): {o["why"]}' for o in opened] or ['- none']
        else:
            lines += by_section[section] or ['- no fact settled in this section']
        lines.append('')
    lines += ['## Fact table', '', '| Fact | Capture | Used by unit |', '| --- | --- | --- |']
    lines += [f'| {r["fact"]} | `{r["capture"]}` | {r["used_by"]} |' for r in settled]
    out.mkdir(parents=True, exist_ok=True)
    (out / 'codex-findings-identity.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'codex-findings-identity.json').write_text(json.dumps(
        {'codex_version': summary.get('codex_version'), 'outcome': outcome, 'facts': settled, 'open': opened},
        indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'{outcome}; {len(settled)} fact(s) settled, {len(opened)} open -> {out / "codex-findings-identity.md"}')
    return 0


# ---- findings ----

SECTIONS = ['Hook events and fields', 'Tool names and inputs', 'Output contract and fail-closed', 'Env and plugin root',
            'Trust and stale trust', 'Skills', 'Agents', 'Main-session tools', 'Session record, tokens and cost',
            'Install form and marketplace', 'Open']


def present(value) -> bool:
    return value not in (None, '', [], {}, False)


def dig(data, *path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def facts():
    """(section, fact, capture globs, used by, getter(hooks, agents) -> value or None)."""
    def marker(mode):
        return lambda h, a: dig(h, 'markers', mode) if dig(h, 'markers', mode, 'hook_fired') else None
    def expansion(key):
        return lambda h, a: dig(a, 'skills', 'expansions', key)
    ses = ['session-*.reduced.jsonl']
    inst = ['install-*.txt']
    return [
        ('Hook events and fields', 'Events seen and their input fields', ['*PreToolUse*.json', 'hooks-events.jsonl'], 'u5, u7, u9, u15',
         lambda h, a: {'events': h.get('events_seen'), 'fields': h.get('fields')} if h.get('fields') else None),
        ('Hook events and fields', 'Id fields in hook input', ['*PreToolUse*.json'], 'u5, u7, u15',
         lambda h, a: h.get('id_fields')),
        ('Tool names and inputs', 'Tool names seen by hooks', ['*PreToolUse*.json'], 'u5, u15', lambda h, a: h.get('tool_names')),
        ('Tool names and inputs', 'Tool input shapes per tool', ['*PreToolUse*.json'], 'u5, u15',
         lambda h, a: h.get('tool_input_shapes')),
        ('Output contract and fail-closed', 'Deny decision output (hook fired, tool output seen)', ['*marker-deny*.json'], 'u5, u9', marker('deny')),
        ('Output contract and fail-closed', 'Exit code 2 behavior', ['*marker-exit2*.json'], 'u5, u9', marker('exit2')),
        ('Output contract and fail-closed', 'Unparseable hook output behavior (fail-closed or open)', ['*marker-bad*.json'], 'u5, u9',
         marker('bad')),
        ('Env and plugin root', 'Hook environment values (CODEX_*, CLAUDE_*)', ['*SessionStart*.json', '*PreToolUse*.json'], 'u5, u7, u9',
         lambda h, a: h.get('env_values')),
        ('Env and plugin root', 'Plugin root as passed to a hook command', ['*SessionStart*.json', '*PreToolUse*.json'], 'u5, u9, u10',
         lambda h, a: h.get('plugin_root')),
        ('Env and plugin root', 'Plugin option (userConfig) env names',
         ['*SessionStart*.json', '*PreToolUse*.json'], 'u8, u9, u10',
         lambda h, a: [n for n in h.get('env_var_names', []) if re.search(r'PLUGIN_OPTION|USER_CONFIG|PROBE_OPT', n)]),
        ('Trust and stale trust', 'Hooks ran after trust, and the bumped hook in the stale run',
         ['stale-events.jsonl', '*Stop*.json'], 'u9, u12',
         lambda h, a: h.get('trust') if dig(h, 'trust', 'hooks_ran_in_hooks_scenario')
         or dig(h, 'trust', 'hooks_ran_in_stale_scenario') else None),
        ('Skills', 'Skills listed and found (root SKILL.md, skills folder)', ['skills-events.jsonl'], 'u8, u11',
         lambda h, a: {'root': dig(a, 'skills', 'root_skill_seen'), 'dir': dig(a, 'skills', 'dir_skill_seen')}
         if dig(a, 'skills', 'ran') else None),
        ('Skills', '${CLAUDE_SKILL_DIR} in skill text', ['skills-events.jsonl'], 'u8, u11', expansion('skill_dir')),
        ('Skills', '${CLAUDE_PLUGIN_ROOT} in skill text', ['skills-events.jsonl'], 'u8, u11', expansion('plugin_root')),
        ('Skills', '$ARGUMENTS in skill text', ['skills-events.jsonl'], 'u8, u11', expansion('arguments')),
        ('Skills', '${user_config.*} in skill text', ['skills-events.jsonl'], 'u8, u11', expansion('opt')),
        ('Agents', 'Which agent forms and locations Codex loaded', ['agents-events.jsonl'], 'u8, u10',
         lambda a_h, a: dig(a, 'agents', 'names_seen') if dig(a, 'agents', 'ran') else None),
        ('Agents', 'Agent names rejected as unknown agent_type', ['agents-events.jsonl'], 'u8, u10',
         lambda h, a: dig(a, 'agents', 'unknown_agent_types')),
        ('Agents', 'Tool name and input fields used to start an agent', ['*PreToolUse*.json'], 'u7, u8, u10',
         lambda h, a: {'tool': dig(a, 'agents', 'spawn_tool_names'), 'input': dig(a, 'agents', 'spawn_tool_input_fields')}
         if dig(a, 'agents', 'spawn_tool_names') else None),
        ('Agents', 'Per-call model or effort argument on start', ['*PreToolUse*.json'], 'u6, u8, u10',
         lambda h, a: ({'fields': dig(a, 'agents', 'per_call_model_or_effort')} if dig(a, 'agents', 'spawn_tool_names') else None)),
        ('Agents', 'Agent identity fields in subagent hook input', ['*PreToolUse*.json', '*Subagent*.json'], 'u5, u7, u15',
         lambda h, a: dig(a, 'agents', 'identity_fields')),
        ('Agents', 'Subagent start/stop events and their fields', ['*Subagent*.json'], 'u7, u9, u15',
         lambda h, a: dig(a, 'agents', 'subagent_event_fields')),
        ('Agents', 'How a subagent hands back its answer', ['*PostToolUse*.json', '*SubagentStop*.json'], 'u7, u8',
         lambda h, a: dig(a, 'agents', 'handback_fields')),
        ('Agents', 'Parallel start (overlapping subagents)', ['*Subagent*.json'], 'u8, u10',
         lambda h, a: {'starts': dig(a, 'agents', 'subagent_starts'), 'overlap': dig(a, 'agents', 'parallel_overlap')}
         if dig(a, 'agents', 'subagent_starts') else None),
        ('Agents', 'Warnings about unknown agent keys or names', ['agents-events.jsonl'], 'u8',
         lambda h, a: dig(a, 'agents', 'stderr_warnings')),
        ('Main-session tools', 'Tool names of the main session', ['agents-prompt-input.txt'], 'u7, u8, u10',
         lambda h, a: dig(a, 'main_tools', 'names')),
        ('Main-session tools', 'Question/popup tool', ['agents-prompt-input.txt'], 'u7, u10',
         lambda h, a: dig(a, 'main_tools', 'question_tool')),
        ('Main-session tools', 'Plan tool', ['agents-prompt-input.txt'], 'u7, u10', lambda h, a: dig(a, 'main_tools', 'plan_tool')),
        ('Main-session tools', 'Web tools', ['agents-prompt-input.txt'], 'u7, u10', lambda h, a: dig(a, 'main_tools', 'web_tools')),
        ('Main-session tools', 'Worktree support', ['agents-prompt-input.txt'], 'u7, u10',
         lambda h, a: dig(a, 'main_tools', 'worktree')),
        ('Session record, tokens and cost', 'Session record line types', ses, 'u6, u15',
         lambda h, a: dig(a, 'session_record', 'line_types')),
        ('Session record, tokens and cost', 'Where the session id is', ses, 'u6, u15',
         lambda h, a: dig(a, 'session_record', 'id_paths')),
        ('Session record, tokens and cost', 'Where the model id is, and model ids seen', ses, 'u6',
         lambda h, a: {'paths': dig(a, 'session_record', 'model_paths'), 'ids': dig(a, 'session_record', 'model_ids')}
         if dig(a, 'session_record', 'model_paths') else None),
        ('Session record, tokens and cost', 'Where token counts are (input, cached, output, reasoning)', ses, 'u6',
         lambda h, a: {'paths': dig(a, 'session_record', 'token_paths'), 'fields': dig(a, 'session_record', 'token_fields')}
         if dig(a, 'session_record', 'token_paths') else None),
        ('Session record, tokens and cost', 'USD cost in the record', ses, 'u6, S2',
         lambda h, a: dig(a, 'session_record', 'cost_paths')),
        ('Session record, tokens and cost', 'Parent and subagent links', ses, 'u6, u15',
         lambda h, a: dig(a, 'session_record', 'parent_links')),
        ('Session record, tokens and cost', 'Codex default model and models listed', ['debug-models.txt'], 'u6',
         lambda h, a: {'default_setting': dig(a, 'session_record', 'default_model_setting'),
                       'listed': dig(a, 'session_record', 'models_listed')}
         if dig(a, 'session_record', 'models_listed') or dig(a, 'session_record', 'default_model_setting') else None),
        ('Install form and marketplace', 'Manifest read when both .claude-plugin and .codex-plugin exist', inst, 'u12',
         lambda h, a: dig(a, 'install', 'manifest_read')),
        ('Install form and marketplace', 'Marketplace file read when both exist', inst, 'u12',
         lambda h, a: dig(a, 'install', 'market_file_read')),
        ('Install form and marketplace', 'Local marketplace re-read at plugin add', inst, 'u12',
         lambda h, a: {'reread': dig(a, 'install', 'reread_at_plugin_add')}
         if dig(a, 'install', 'reread_at_plugin_add') is not None else None),
        ('Install form and marketplace', 'marketplace upgrade refreshes a local path', inst, 'u12',
         lambda h, a: {'refreshed': dig(a, 'install', 'refreshed_by_upgrade')}
         if dig(a, 'install', 'refreshed_by_upgrade') is not None else None),
        ('Install form and marketplace', 'Two marketplaces with the same name', inst, 'u12',
         lambda h, a: {'name_count_in_list': dig(a, 'install', 'dup_marketplace_count')}
         if dig(a, 'install', 'dup_marketplace_count') is not None else None),
        ('Install form and marketplace', 'plugin list form for installed and enabled', inst, 'u12',
         lambda h, a: dig(a, 'install', 'plugin_list_added_head')),
    ]


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def fmt_value(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def trust_notes(hooks: dict) -> list:
    """Plain statements for the trust section when trust entries or hook runs are missing."""
    if not hooks:
        return ['no summary-hooks.json: the hooks and stale scenarios were not summarized']
    trust = hooks.get('trust') or {}
    notes = []
    if not trust.get('config_entries'):
        notes.append(f'no {NAME} trust entry in hooks.state; hooks did not load or were not trusted')
    if not trust.get('hooks_ran_in_hooks_scenario'):
        notes.append('no hook fired in the hooks scenario')
    if not trust.get('hooks_ran_in_stale_scenario'):
        notes.append('no hook fired in the stale scenario')
    if not any(m.get('hook_fired') for m in (hooks.get('markers') or {}).values()):
        notes.append('no marker hook fired: the deny, exit-2 and bad-output behavior is unknown')
    return notes


def cmd_findings(args) -> int:
    out = Path(args.out).resolve()
    probe_dir = out / 'probe'
    hooks = load_json(probe_dir / 'summary-hooks.json')
    agents = load_json(probe_dir / 'summary-agents.json')
    caps = probe_dir / 'captures'
    rows, by_section, opened = [], {name: [] for name in SECTIONS}, []
    for section, fact, globs, units, getter in facts():
        value = getter(hooks, agents)
        cited = None
        for pattern in globs:
            found = sorted(caps.glob(pattern)) if caps.is_dir() else []
            if found:
                cited = f'probe/captures/{found[0].name}'
                break
        if present(value) and cited:
            rows.append({'section': section, 'fact': fact, 'value': value, 'capture': cited, 'used_by': units,
                         'status': 'settled'})
            by_section[section].append(f'- {fact}: `{fmt_value(value)}` (`{cited}`)')
        else:
            why = 'no value in the summaries' if not present(value) else 'no capture file found'
            opened.append({'section': section, 'fact': fact, 'used_by': units, 'status': 'open', 'why': why})
    notes = trust_notes(hooks)
    by_section['Trust and stale trust'] += [f'- {n}' for n in notes]
    lines = ['# Codex findings', '',
             f'Codex version: {hooks.get("codex_version") or "unknown"}', '']
    for section in SECTIONS:
        lines += [f'## {section}', '']
        if section == 'Open':
            lines += [f'- {o["fact"]} ({o["section"]}; needed by {o["used_by"]}): {o["why"]}' for o in opened] or ['- none']
        else:
            lines += by_section[section] or ['- no fact settled in this section']
        lines.append('')
    lines += ['## Fact table', '', '| Fact | Capture | Used by unit |', '| --- | --- | --- |']
    lines += [f'| {r["fact"]} | `{r["capture"]}` | {r["used_by"]} |' for r in rows]
    out.mkdir(parents=True, exist_ok=True)
    (out / 'codex-findings.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'codex-findings.json').write_text(json.dumps(
        {'codex_version': hooks.get('codex_version'), 'facts': rows, 'open': opened, 'trust_notes': notes}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    print(f'{len(rows)} fact(s) settled, {len(opened)} open -> {out / "codex-findings.md"}')
    return 0


def cmd_check(args) -> int:
    if args.what == 'report':
        return check_report(args)
    if args.what == 'install':
        return check_install(args)
    path = Path(args.file).resolve()
    if not path.is_file():
        print(f'missing file: {path}')
        return 1
    text = path.read_text(encoding='utf-8')
    identity = 'identity' in path.name
    skills = 'skills' in path.name
    sections = IDENTITY_SECTIONS if identity else SKILLS_SECTIONS if skills else SECTIONS
    problems = [f'missing section: ## {name}' for name in sections if not re.search(rf'^## {re.escape(name)}\s*$', text, re.M)]
    if '| Fact | Capture | Used by unit |' not in text:
        problems.append('missing table: | Fact | Capture | Used by unit |')
    if identity or skills:
        body = re.split(r'^## Outcome\s*$', text, flags=re.M)
        part = re.split(r'^## ', body[1], flags=re.M)[0] if len(body) > 1 else ''
        n = len(re.findall(r'^Outcome: \S', part, re.M))
        if n != 1:
            problems.append(f'## Outcome must hold exactly one "Outcome:" line, found {n}')
    for cited in sorted(set(re.findall(r'probe(?:-identity|-skills)?/captures/[\w.\-]+', text))):
        if not (path.parent / cited).is_file():
            problems.append(f'cited capture missing: {cited}')
    for problem in problems:
        print(problem)
    if skills and not problems:
        found = re.search(r'^Outcome: .*$', text, re.M)
        print(f'OK: {len(sections)} sections, {len(table_rows(text.split("| Fact | Capture | Used by unit |")[1]))} facts, '
              f'every cited capture present; {found.group(0) if found else ""}')
    return 1 if problems else 0


# ---- end-to-end tooling ----

CAPABILITIES = Path(__file__).resolve().parent / 'capabilities.json'
RUN_STEP = re.compile(r'step: n=(\d+) name=(\S+)')
RUN_ID = re.compile(r'\b(?:session|id)=([\w\-]{8,})')
CITE = re.compile(r'(?<![\w/.\-])(probe-identity|probe-skills|probe|e2e)/([^\s;|`,)]+)(?: lines? (\d+)(?:-(\d+))?)?')
ERROR_KEY = re.compile(r'^error$')


def inside_repo(path: Path) -> bool:
    path = Path(path).resolve()
    return path == REPO or REPO in path.parents


def cmd_e2e_setup(args) -> int:
    base = Path(args.dir).resolve()
    if inside_repo(base):
        sys.exit(f'refusing to set up inside the repository: {base}')
    repo, data = base / 'repo', base / 'data'
    repo.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    write(repo / 'calc.py', CALC)
    write(repo / 'test_calc.py', CALC_TEST)
    if not (repo / '.git').is_dir():
        git = ['git', '-C', str(repo), '-c', 'user.name=e2e', '-c', 'user.email=e2e@example.invalid']
        subprocess.run(git + ['init', '-q'], check=True)
        subprocess.run(git + ['add', '.'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'start'], check=True)
    print(f'Launch (in a terminal; the data folder is set through $MA_TASKS_DIR):\n'
          f'  cd {repo} && MA_TASKS_DIR={data} codex\n'
          'Request text: run probe.py e2e-request <install snapshot folder> after the install')
    return 0


def cmd_e2e_request(args) -> int:
    folder = Path(args.folder)
    listing = folder / 'plugin-list.txt'
    found = parse_plugin_list(listing.read_text(encoding='utf-8')) if listing.is_file() else None
    if not found or not found[2]:
        print(f'{listing} has no my-agent@my-plugins row with a version', file=sys.stderr)
        return 1
    version = found[2]
    files = (folder / 'cache-files.txt').read_text(encoding='utf-8').split() if (folder / 'cache-files.txt').is_file() else []
    if f'{version}/SKILL.md' not in files:
        print(f'cache-files.txt lacks {version}/SKILL.md', file=sys.stderr)
        return 1
    skill = Path(os.path.abspath(codex_home(args))) / 'plugins' / 'cache' / 'my-plugins' / 'my-agent' / version / 'SKILL.md'
    if not skill.is_file():
        print(f'missing file: {skill}', file=sys.stderr)
        return 1
    print(f'Read the file {skill} and follow it as your instructions, with these arguments: {E2E_ARGS}')
    return 0


def failure_text(obj):
    """Text of the first failure in one session record line, or None."""
    for node in walk(obj):
        if not isinstance(node, dict):
            continue
        err = next((v for k, v in node.items() if ERROR_KEY.match(k) and v), None)
        if err is not None:
            return err if isinstance(err, str) else json.dumps(err)
        code = node.get('exit_code')
        if node.get('status') == 'failed' or (isinstance(code, int) and not isinstance(code, bool) and code != 0):
            return str(node.get('aggregated_output') or node.get('output') or node.get('command') or node.get('status'))
    return None


def scrub_home(text: str) -> str:
    return text.replace(str(Path.home()), '<home>')


def one_line(text, size=200) -> str:
    text = scrub_home(re.sub(r'\s+', ' ', str(text)).replace('"', "'").replace('|', '/').strip())
    return text[:size]


SPAWN_NAME = re.compile(r'spawn_agent$')
SPAWN_ERROR = re.compile(r'^\s*(error|failed|unknown|invalid|unsupported|refused)|unknown agent[_ ]type', re.I)
MY_AGENT_ROLE = re.compile(r'my_agent_\w+')


def spawn_agent_type(payload):
    args = payload.get('arguments')
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return '-'
    value = args.get('agent_type') if isinstance(args, dict) else None
    return value[:80] if isinstance(value, str) else '-'


def spawn_error(payload):
    """One-line error text of a spawn_agent call output, or None when it succeeded."""
    out = payload.get('output')
    if payload.get('success') is False:
        return one_line(out if isinstance(out, str) else 'failed')
    if isinstance(out, str):
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if isinstance(data, dict):
            err = data.get('error')
            return one_line(err if isinstance(err, str) else json.dumps(err)) if err else None
        return one_line(out) if SPAWN_ERROR.search(out) else None
    if isinstance(out, dict) and out.get('error'):
        return one_line(out['error'] if isinstance(out['error'], str) else json.dumps(out['error']))
    return None


def reduce_session(src: Path, dest: Path, name: str, failures: list, spawns=None):
    lines, pending = [], {}
    for line in src.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            lines.append(json.dumps({'unparsed': True}))
            continue
        text = failure_text(obj)
        if text is not None:
            failures.append({'step': '-', 'source': f'e2e/{name} line {len(lines) + 1}', 'text': one_line(text)})
        reduced = reduce_value(obj)
        payload = obj.get('payload') if isinstance(obj, dict) else None
        if spawns is not None and isinstance(payload, dict) and isinstance(reduced.get('payload'), dict):
            if payload.get('type') == 'function_call' and SPAWN_NAME.search(str(payload.get('name'))):
                kind = spawn_agent_type(payload)
                reduced['payload']['arguments'] = {'agent_type': kind}
                spawn = {'agent_type': kind, 'ok': True, 'line': f'e2e/{name} line {len(lines) + 1}'}
                spawns.append(spawn)
                pending[payload.get('call_id')] = spawn
            elif payload.get('type') == 'function_call_output' and payload.get('call_id') in pending:
                spawn = pending.pop(payload['call_id'])
                err = spawn_error(payload)
                reduced['payload']['output'] = {'error': err}
                if err:
                    spawn['ok'], spawn['error'] = False, err
        lines.append(json.dumps(reduced))
    dest.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def cmd_e2e_collect(args) -> int:
    base, out = Path(args.dir).resolve(), Path(args.out).resolve()
    if inside_repo(out):
        sys.exit(f'refusing to write inside the repository: {out}')
    logs = sorted((base / 'repo' / '.my-agent').glob('*/run-log.md'), key=lambda p: p.stat().st_mtime)
    if not logs:
        sys.exit(f'no run-log.md under {base / "repo" / ".my-agent"}')
    task = logs[-1].parent
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(logs[-1], out / 'run-log.txt')
    rel = []
    for path in sorted(task.rglob('*')):
        if path.is_file():
            dest = out / 'task' / path.relative_to(task)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            rel.append(str(path.relative_to(task)))
    (out / 'files.txt').write_text('\n'.join(rel) + '\n', encoding='utf-8')
    steps, hooks, subagents, failures, ids, spawns = [], {}, [], [], [], []
    current, seen = '-', set()
    for number, line in enumerate((out / 'run-log.txt').read_text(encoding='utf-8').splitlines(), 1):
        for value in RUN_ID.findall(line):
            if value not in ids:
                ids.append(value)
        m = RUN_STEP.search(line)
        if m:
            current = f'{m.group(1)} {m.group(2)}'
            if m.group(1) not in seen:
                seen.add(m.group(1))
                steps.append({'n': int(m.group(1)), 'name': m.group(2), 'line': number})
        m = re.search(r' (guard|start|stop): (.*)', line)
        if not m:
            continue
        fields = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', m.group(2)))
        if m.group(1) == 'guard' and 'hook' in fields:
            hooks[fields['hook']] = hooks.get(fields['hook'], 0) + 1
        elif m.group(1) == 'start':
            subagents.append({'agent': fields.get('agent', '-'), 'id': fields.get('id', '-'), 'line': number})
        elif m.group(1) == 'stop' and fields.get('end', 'ok') != 'ok':
            failures.append({'step': current, 'source': f'e2e/run-log.txt line {number}', 'text': one_line(m.group(2))})
    sessions = []
    root = codex_home(args) / 'sessions'
    for i in ids:
        for path in sorted(root.rglob('*.jsonl')) if root.is_dir() else []:
            if i in path.name and i not in sessions:
                name = f'session-{i}.jsonl'
                found = []
                reduce_session(path, out / name, name, failures, found)
                spawns += found
                for sp in found:
                    if not MY_AGENT_ROLE.fullmatch(sp['agent_type']):
                        failures.append({'step': '-', 'source': sp['line'], 'kind': 'spawn',
                                         'text': f'subagent started without a my-agent role: agent_type={sp["agent_type"]}'})
                    if not sp['ok']:
                        failures.append({'step': '-', 'source': sp['line'], 'kind': 'spawn', 'text': sp['error']})
                sessions.append(i)
    summary = {'task': task.name, 'repo': str(base / 'repo'), 'steps_reached': steps, 'hooks_fired': hooks,
               'subagents': subagents, 'spawns': spawns, 'sessions': sessions, 'failures': failures}
    (out / 'summary-e2e.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return 0


def cell(text) -> str:
    return re.sub(r'\s+', ' ', str(text)).replace('|', '/').strip() or '-'


def cmd_report(args) -> int:
    e2e = Path(args.e2e).resolve()
    summary = load_json(e2e / 'summary-e2e.json')
    rows = load_json(CAPABILITIES).get('rows', [])
    captures, version = {}, ''
    for path in args.findings:
        data = load_json(Path(path))
        version = version or data.get('codex_version', '')
        for fact in data.get('facts', []):
            cite = fact.get('capture')
            if cite and fact.get('line'):
                cite = f'{cite} line {fact["line"]}'
            captures.setdefault(fact.get('fact'), cite)
    manifest = load_json(REPO / 'plugins' / 'my-agent' / '.codex-plugin' / 'plugin.json')
    files = set((e2e / 'files.txt').read_text(encoding='utf-8').split()) if (e2e / 'files.txt').is_file() else set()
    reached = {s['n']: s for s in summary.get('steps_reached', [])}
    extra = {3: 'plan.md', 7: 'verify.md', 8: 'review.md'}
    lines = [f'# Codex gap report: {summary.get("task", "e2e")}',
             f'{version or "Codex CLI ?"} · my-agent {manifest.get("version", "?")} · '
             f'run {datetime.now(timezone.utc).date()} · throwaway repository {summary.get("repo", "?")}', '',
             '## Run summary', '| Step | Reached | Evidence |', '|---|---|---|']
    for n, name in E2E_STEPS:
        hit = reached.get(n)
        evidence = [f'e2e/run-log.txt line {hit["line"]}'] if hit else ['no step line in the run-log']
        if hit and extra.get(n) in files:
            evidence.append(f'e2e/task/{extra[n]}')
        lines.append(f'| {n} {name} | {"yes" if hit else "no"} | {"; ".join(evidence)} |')
    lines += ['', '## Gaps',
              '| # | Capability | Needed by | What was tried | Result | Effect on the workflow | Evidence |',
              '|---|---|---|---|---|---|---|']
    number = 0
    for row in rows:
        if row['status'] == 'available':
            continue
        number += 1
        cites = []
        for fact in row.get('facts', []):
            if captures.get(fact) and captures[fact] not in cites:
                cites.append(captures[fact])
        lines.append('| ' + ' | '.join(cell(x) for x in [
            f'gap-{number}', row['capability'], ', '.join(Path(n).name for n in row['needed_by']), row['how_tried'],
            row['result'], row['effect'], '; '.join(cites) or 'none: not probed']) + ' |')
    patterns = [p for row in rows for p in row.get('failure_patterns', [])]
    lines += ['', '## Unlisted failures']
    unlisted = [f for f in summary.get('failures', []) if not any(re.search(p, f['text'], re.I) for p in patterns)]
    for f in unlisted:
        lines.append(f'Unlisted failure: step {f["step"]}, "{cell(f["text"])}" ({f["source"]}) has no capability row')
    if not unlisted:
        lines.append('(none)')
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return 0


def section_of(text: str, name: str):
    m = re.search(rf'^## {re.escape(name)}\s*$', text, re.M)
    if not m:
        return None
    return re.split(r'^## ', text[m.end():], maxsplit=1, flags=re.M)[0]


def table_rows(body: str) -> list:
    rows = [[c.strip() for c in l.strip().strip('|').split('|')] for l in body.splitlines() if l.strip().startswith('|')]
    return [r for r in rows[1:] if not all(re.fullmatch(r':?-+:?', c) for c in r)]


def check_report(args) -> int:
    path = Path(args.file).resolve()
    if not path.is_file():
        print(f'missing file: {path}')
        return 1
    if not args.e2e:
        sys.exit('check report needs --e2e <folder>')
    e2e = Path(args.e2e).resolve()
    probe_root = Path(args.probe_root).resolve() if args.probe_root else path.parent
    text = path.read_text(encoding='utf-8')
    problems = []
    run, gaps, unlisted = (section_of(text, n) for n in ('Run summary', 'Gaps', 'Unlisted failures'))
    for name, body in (('Run summary', run), ('Gaps', gaps), ('Unlisted failures', unlisted)):
        if body is None:
            problems.append(f'missing section: ## {name}')
    for name, body, width in (('step', run, 3), ('gap', gaps, 7)):
        for row in table_rows(body or ''):
            if len(row) != width or not all(c and c != '-' for c in row):
                problems.append(f'{name} row without all {width} columns: {" | ".join(row)[:80]}')
    for m in CITE.finditer(text):
        kind, rest, first, last = m.groups()
        target = (e2e if kind == 'e2e' else probe_root / kind) / rest
        label = f'{kind}/{rest}'
        if not target.is_file():
            problems.append(f'cited file missing: {label}')
        elif first:
            count = len(target.read_text(encoding='utf-8').splitlines())
            if int(first) < 1 or int(last or first) > count or int(last or first) < int(first):
                problems.append(f'cited line missing: {label} line {first}{"-" + last if last else ""} (file has {count})')
    for line in (unlisted or '').splitlines():
        if line.strip() and line.strip() != '(none)':
            problems.append(line.strip())
    summary = load_json(e2e / 'summary-e2e.json')
    if summary.get('spawns') and not summary.get('subagents'):
        patterns = [p for row in load_json(CAPABILITIES).get('rows', []) for p in row.get('failure_patterns', [])]
        if not any(f.get('kind') == 'spawn' and any(re.search(p, f['text'], re.I) for p in patterns)
                   for f in summary.get('failures', [])):
            problems.append('spawn_agent calls in the session but no start line in the run-log and no capability row for them')
    for problem in sorted(set(problems), key=problems.index):
        print(problem)
    return 1 if problems else 0


def parse_plugin_list(text: str):
    """(marketplace root, status, version) of the my-agent@my-plugins row, or None."""
    path = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('Marketplace `'):
            path = next((l.strip() for l in lines[i + 1:] if l.strip()), '')
        m = re.match(r'^my-agent@my-plugins\s+(installed, enabled|installed, disabled|installed|not installed)\s*(.*)$', line)
        if m:
            tokens = m.group(2).split()
            root = re.sub(r'/(\.agents/plugins|\.claude-plugin)/marketplace\.json$', '', path or '')
            return root, m.group(1), tokens[0] if tokens and re.match(r'\d', tokens[0]) else ''
    return None


def check_install(args) -> int:
    folder = Path(args.file)
    root = os.path.normpath(args.root) if args.root else str(REPO)
    problems = []
    listing = folder / 'plugin-list.txt'
    found = parse_plugin_list(listing.read_text(encoding='utf-8')) if listing.is_file() else None
    version = ''
    if not found:
        problems.append('plugin-list.txt has no my-agent@my-plugins row')
    else:
        market, status, version = found
        if status != 'installed, enabled':
            problems.append(f'my-agent@my-plugins is "{status}", not "installed, enabled"')
        if os.path.normpath(market) != root:
            problems.append(f'marketplace root is {market}, not {root}')
    source = folder / 'skills-source.txt'
    if not source.is_file() or source.read_text(encoding='utf-8').strip() not in ('prompt-input', 'session-record'):
        problems.append('skills evidence is not from a hard source')
    skills = folder / 'skills-list.txt'
    listed = [l.strip() for l in skills.read_text(encoding='utf-8').splitlines() if l.strip()] if skills.is_file() else []
    if listed.count('my-agent:monitor') != 1:
        problems.append(f'skills-list.txt holds my-agent:monitor {listed.count("my-agent:monitor")} time(s), not exactly once')
    if 'my-agent:my-agent' in listed:
        problems.append('my-agent:my-agent is listed, which contradicts work/codex-findings-skills.md')
    else:
        print('expected gap: my-agent:my-agent not listed (Codex lists no plugin-root SKILL.md; '
              'capability plugin-skill-discovery)')
    cached = folder / 'cache' / version / 'codex-plugin.json' if version else None
    wanted = Path(root) / 'plugins' / 'my-agent' / '.codex-plugin' / 'plugin.json'
    if cached is None or not cached.is_file():
        problems.append(f'no cache copy of .codex-plugin/plugin.json for version {version or "?"} (an old Claude-format install has none)')
    elif not wanted.is_file():
        problems.append(f'missing {wanted}')
    elif load_json(cached) != load_json(wanted):
        problems.append('the cached .codex-plugin/plugin.json differs from the repository one')
    if args.version:
        if version != args.version:
            problems.append(f'plugin-list.txt shows version {version or "none"}, not {args.version}')
        if cached is not None and cached.is_file() and load_json(cached).get('version') != args.version:
            problems.append(f'the cached manifest version is {load_json(cached).get("version")}, not {args.version}')
    for problem in problems:
        print(problem)
    return 1 if problems else 0


# ---- skills diagnosis ----

SKILLS_SCENARIOS = ['skills-live', 'skills-kit']
SKILLS_EXEC_PROMPT = 'Reply with exactly: ok. Do not run any command.'
SKILLS_INPUT_PROMPT = 'Reply with exactly: ok.'
KIT_VERSION = '0.0.1'
VARIANT_IDS = ['s0', 's1', 's2', 's3', 's4', 's5']
SKILLS_SECTIONS = ['Sources', 'Live install', 'Variants', 'Names', 'Listed path', 'Outcome', 'Open']
FILLER = 'Filler line {i:04d} of the made-up probe body, repeated to reach the size of a long skill file.\n'
VARIANT_TEXT = {
    's0': 'baseline (my-agent shape, "skills": ["./"])',
    's1': '"skills": "./alt/", no skills/ folder, four alt/ skills',
    's2': 'no "skills" key in the Codex manifest',
    's3': '"skills": "./" (string)',
    's4': 'small root SKILL.md with its own name',
    's5': '"skills": "./codex/skills/", two relative symlinks',
}


def probe_desc(marker: str) -> str:
    return f'{marker} Probe skill, made-up text, use only when asked to use {marker}.'


def kit_skill_specs() -> dict:
    """Plugins of the skills kit: variant -> manifest keys, skills (marker, description, file) and symlinks."""
    def skill(v, key, name, directory, big=False, front='plain'):
        marker = f'MA-SKILL-{v}-{key}'
        return {'key': key, 'name': name, 'dir': directory, 'big': big, 'front': front, 'marker': marker,
                'description': probe_desc(marker), 'file': (directory + '/' if directory else '') + 'SKILL.md'}
    specs = {}
    for v in VARIANT_IDS:
        plugin = f'{NAME}-{v}'
        root = skill(v, 'root', plugin, '', big=True, front='root')
        sub = skill(v, 'sub', f'{plugin}-sub', f'skills/{plugin}-sub', front='sub')
        spec = {'plugin': plugin, 'changes': VARIANT_TEXT[v], 'manifest': {}, 'skills': [root, sub], 'links': []}
        if v == 's0':
            spec['manifest'] = {'skills': ['./']}
        elif v == 's1':
            spec['manifest'] = {'skills': './alt/'}
            spec['skills'] = [root,
                              skill(v, 'named', f'{plugin}-named', f'alt/{plugin}-dir'),
                              skill(v, 'plain', plugin, f'alt/{plugin}'),
                              skill(v, 'big', f'{plugin}-big', f'alt/{plugin}-big', big=True),
                              skill(v, 'front', f'{plugin}-front', f'alt/{plugin}-front', front='root')]
        elif v == 's3':
            spec['manifest'] = {'skills': './'}
        elif v == 's4':
            spec['manifest'] = {'skills': ['./']}
            spec['skills'][0] = skill(v, 'root', f'{plugin}-root', '')
        elif v == 's5':
            spec['manifest'] = {'skills': './codex/skills/'}
            spec['links'] = [{'path': f'codex/skills/{plugin}/SKILL.md', 'target': '../../../SKILL.md'},
                             {'path': f'codex/skills/{plugin}-sub', 'target': f'../../skills/{plugin}-sub'}]
        specs[v] = spec
    return specs


def skill_text(spec: dict) -> str:
    lines = [f'name: {spec["name"]}', f'description: {spec["description"]}']
    if spec['front'] == 'root':
        lines += ["argument-hint: '[--auto] <request> | status'", 'model: opus']
    elif spec['front'] == 'sub':
        lines += ['disable-model-invocation: true', "argument-hint: '[status|stop]'"]
    text = '---\n' + '\n'.join(lines) + f'\n---\n\n# {spec["name"]}\n'
    if spec['big']:
        i = 0
        while len(text.encode('utf-8')) < 45000:
            text += FILLER.format(i=i)
            i += 1
    return text


def cmd_kit_skills(args) -> int:
    base = Path(args.dir).resolve()
    kit = base / 'kit'
    specs = kit_skill_specs()
    write_json(kit / '.agents' / 'plugins' / 'marketplace.json', {
        'name': NAME, 'owner': {'name': NAME},
        'plugins': [{'name': s['plugin'], 'source': f'./plugins/{s["plugin"]}', 'description': f'{s["plugin"]} skills probe'}
                    for s in specs.values()]})
    for spec in specs.values():
        plugin = kit / 'plugins' / spec['plugin']
        if plugin.is_symlink() or plugin.exists():
            shutil.rmtree(plugin)
        head = {'name': spec['plugin'], 'version': KIT_VERSION, 'description': f'{spec["plugin"]} skills probe'}
        write_json(plugin / '.codex-plugin' / 'plugin.json', dict(head, **spec['manifest']))
        write_json(plugin / '.claude-plugin' / 'plugin.json', dict(head, skills=['./']))
        for skill in spec['skills']:
            write(plugin / skill['file'], skill_text(skill))
        for link in spec['links']:
            target = plugin / link['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(link['target'], target)
    print(f'skills kit written to {kit}')
    print('Commands for the person (they change Codex settings):')
    print(f'  codex plugin marketplace add {kit}')
    for spec in specs.values():
        print(f'  codex plugin add {spec["plugin"]}@{NAME}')
    print('Cleanup (run always):')
    for spec in specs.values():
        print(f'  codex plugin remove {spec["plugin"]}@{NAME}')
    print(f'  codex plugin marketplace remove {NAME}')
    return 0


def run_skills(args, base: Path) -> int:
    scenario = args.scenario
    work = base / f'work-{scenario}'
    raw = base / 'raw'
    work.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    version = call(args.codex, ['--version'])
    (base / 'codex-version.txt').write_text(version.stdout, encoding='utf-8')
    log_line(base, f'{scenario}: {args.codex} --version -> exit {version.returncode}')
    if scenario == 'skills-live':
        for name, argv in (('codex', ['--help']), ('plugin', ['plugin', '--help']), ('debug', ['debug', '--help'])):
            done = call(args.codex, argv, cwd=str(work))
            write(raw / f'{scenario}-help-{name}.txt', done.stdout + (f'\n[stderr]\n{done.stderr}' if done.stderr else ''))
            log_line(base, f'{scenario}: {args.codex} {" ".join(argv)} -> exit {done.returncode}')
    done = call(args.codex, ['debug', 'prompt-input', SKILLS_INPUT_PROMPT], cwd=str(work))
    write(raw / f'{scenario}-prompt-input.txt', done.stdout)
    log_line(base, f'{scenario}: {args.codex} debug prompt-input -> exit {done.returncode}')
    argv = ['exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check', '-C', str(work), SKILLS_EXEC_PROMPT]
    done = call(args.codex, argv, cwd=str(work))
    write(raw / f'{scenario}-events.jsonl', done.stdout)
    write(raw / f'{scenario}-stderr.txt', done.stderr)
    log_line(base, f'{scenario}: {args.codex} exec --json --sandbox read-only -C {work} -> exit {done.returncode}')
    events = []
    for line in done.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    ids, paths = collect_ids(base, scenario, events)
    copied = copy_sessions(ids, paths, codex_home(args) / 'sessions', base / 'sessions' / scenario)
    log_line(base, f'{scenario}: copied {len(copied)} session record(s) of {len(ids)} id(s)')
    return 0 if done.returncode == 0 else 1


# -- listing evidence rule (H3): one function for summary-skills and later units --

ALIAS_LINE = re.compile(r'^[ \t]*[-*][ \t]+`(r\d+)`[ \t]*=[ \t]*`([^`\n]+)`[ \t]*$', re.M)
ENTRY_LINE = re.compile(r'^- (\S+):\s+((?:(?!\n- \S+:\s|\n[ \t]*\n).)*?)\s*\(file:\s*([^)\s]+)\)', re.M | re.S)
HOME_PATH = re.compile(r'/(?:Users|home)/[^/\s]+')


def resolve_alias(raw_path: str, aliases: dict) -> str:
    m = re.match(r'(r\d+)/(.*)$', raw_path, re.S)
    if not m:
        return raw_path
    root = aliases.get(m.group(1))
    return root.rstrip('/') + '/' + m.group(2) if root else 'unresolved'


def parse_listing(text: str):
    """(entries, aliases) of one decoded text: entries of the form `- name: description (file: path)`."""
    aliases = dict(ALIAS_LINE.findall(text))
    entries = []
    for m in ENTRY_LINE.finditer(text):
        entries.append({'name': m.group(1), 'description': m.group(2), 'raw_path': m.group(3),
                        'path': resolve_alias(m.group(3), aliases), 'line': text.count('\n', 0, m.start()) + 1})
    return entries, aliases


def norm_desc(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'(?:…|\.\.\.)$', '', text).strip()


def description_matches(entry_desc: str, skill_desc: str) -> bool:
    a, b = norm_desc(entry_desc), norm_desc(skill_desc)
    return bool(a) and (a == b or (len(a) >= 60 and b.startswith(a)))


def json_strings(value, depth=0):
    """Every string of a decoded JSON value; a string that is itself JSON is decoded too."""
    for node in walk(value):
        if isinstance(node, str):
            yield node
            if depth < 3 and node.lstrip()[:1] in ('{', '['):
                try:
                    inner = json.loads(node)
                except ValueError:
                    continue
                yield from json_strings(inner, depth + 1)


def text_strings(raw: str) -> list:
    """Strings of a text that may be JSON (as a whole, or one value per line); plain text stays as it is."""
    for parse in (lambda: [json.loads(raw)], lambda: [json.loads(l) for l in raw.splitlines() if l.strip()]):
        try:
            strings = [s for v in parse() for s in json_strings(v)]
        except ValueError:
            continue
        if strings:
            return strings
    return [raw]


def record_item_is_input(obj) -> bool:
    """A session record item that is neither model output nor a tool call nor a tool output, nor the probe's prompt."""
    if not isinstance(obj, dict):
        return False
    kind = obj.get('type')
    payload = obj.get('payload') if isinstance(obj.get('payload'), dict) else {}
    if kind in ('world_state', 'turn_context', 'session_meta'):
        return True
    if kind == 'response_item' and payload.get('type') == 'message' and payload.get('role') in ('developer', 'system', 'user'):
        return not (payload.get('role') == 'user' and any(SKILLS_INPUT_PROMPT in s for s in json_strings(payload)))
    return False


def listing_texts(path) -> list:
    """(line, decoded text) pairs of one source: a session record (.jsonl) or the output of `codex debug prompt-input`."""
    path = Path(path)
    raw = path.read_text(encoding='utf-8', errors='replace')
    if path.suffix == '.jsonl':
        out = []
        for n, line in enumerate(raw.splitlines(), 1):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if record_item_is_input(obj):
                out += [(n, s) for s in json_strings(obj)]
        return out
    return [(0, s) for s in text_strings(raw)]


def all_entries(path) -> list:
    out = []
    for at, text in listing_texts(path):
        for e in parse_listing(text)[0]:
            out.append(dict(e, at=at or e['line']))
    return out


def listing_found(path) -> bool:
    return bool(all_entries(path))


def find_skill_entries(path, skills: dict) -> dict:
    """skill key -> listing entries whose description part matches the skill's description (a string or a list)."""
    found = {k: [] for k in skills}
    for e in all_entries(path):
        for key, desc in skills.items():
            if any(description_matches(e['description'], d) for d in ([desc] if isinstance(desc, str) else desc)):
                found[key].append(e)
    return found


def distinct_entries(entries: list) -> list:
    seen, out = set(), []
    for e in entries:
        if (e['name'], e['path']) not in seen:
            seen.add((e['name'], e['path']))
            out.append(e)
    return out


def scrub_text(text: str, codex: Path) -> str:
    text = str(text)
    codex = str(codex).rstrip('/')
    if codex:
        text = text.replace(codex, '<codex-home>')
    text = re.sub(r'/(?:Users|home)/[^/\s]+/\.codex(?=/|\s|$)', '<codex-home>', text)
    text = text.replace(str(Path.home()), '<home>')
    return HOME_PATH.sub('<home>', text)


def frontmatter_description(path: Path):
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return None
    parts = text.split('---')
    if not text.startswith('---') or len(parts) < 3:
        return None
    lines = parts[1].splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'description:\s*(.*)$', line)
        if not m:
            continue
        value = m.group(1).strip()
        if value in ('>', '|', '>-', '|-'):
            block = []
            for nxt in lines[i + 1:]:
                if nxt[:1] not in (' ', '\t'):
                    break
                block.append(nxt.strip())
            return ' '.join(block)
        if len(value) > 1 and value[0] == value[-1] and value[0] in '\'"':
            value = value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1]
        return value
    return None


def my_agent_descriptions(codex: Path, market: str = 'my-plugins', plugin: str = 'my-agent') -> dict:
    """Frontmatter descriptions of my-agent's root skill and monitor in the installed copies (every version)."""
    base = codex / 'plugins' / 'cache' / market / plugin
    out = {'root': [], 'monitor': []}
    for version in sorted(p for p in base.glob('*') if p.is_dir()) if base.is_dir() else []:
        for key, rel in (('root', 'SKILL.md'), ('monitor', 'skills/monitor/SKILL.md')):
            desc = frontmatter_description(version / rel)
            if desc:
                out[key].append(desc)
    return out


def parse_installed(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(rf'^(\S+)@{NAME}\s+(installed, enabled|installed, disabled|installed|not installed)\b', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def phase_ran(base: Path, scenario: str) -> bool:
    return any((base / 'raw' / f'{scenario}-{n}').is_file() for n in ('prompt-input.txt', 'events.jsonl')) \
        or (base / 'sessions' / scenario).is_dir()


def source_files(base: Path, scenario: str) -> dict:
    pi = base / 'raw' / f'{scenario}-prompt-input.txt'
    folder = base / 'sessions' / scenario
    return {'prompt-input': [pi] if pi.is_file() else [],
            'session-record': sorted(folder.glob('*.jsonl')) if folder.is_dir() else []}


def evaluate_phase(base: Path, scenario: str, skills: dict, caps: Path, codex: Path) -> dict:
    """Read one phase's sources, write one reduced capture per source, return the matches per skill key."""
    info = {'ran': phase_ran(base, scenario), 'sources': {}, 'matches': {k: [] for k in skills}, 'first': None}
    for source, files in source_files(base, scenario).items():
        total, lines = 0, []
        name = f'{scenario}-{source}.txt'
        for idx, path in enumerate(files):
            label = source if idx == 0 else f'{source}-{idx + 1}'
            for e in all_entries(path):
                total += 1
                hit = [k for k, d in skills.items()
                       if any(description_matches(e['description'], x) for x in ([d] if isinstance(d, str) else d))]
                if not hit:
                    continue
                shown = 'unresolved' if e['path'] == 'unresolved' else scrub_text(e['path'], codex)
                lines.append(f'{label}:{e["at"]}  - {e["name"]}: {scrub_text(re.sub(chr(92) + "s+", " ", e["description"]).strip(), codex)}'
                             f' (file: {shown})')
                ref = {'name': e['name'], 'path': shown, 'source': source, 'capture': f'probe-skills/captures/{name}',
                       'line': len(lines)}
                for k in hit:
                    info['matches'][k].append(ref)
                if info['first'] is None:
                    info['first'] = {'capture': ref['capture'], 'line': ref['line']}
        if files:
            if not lines:
                lines = [f'no listing entry of a probe skill or of my-agent was found ({total} listing entries in all)']
            write(caps / name, '\n'.join(lines) + '\n')
        info['sources'][source] = {'read': bool(files), 'found': total > 0, 'entries': total,
                                   'capture': f'probe-skills/captures/{name}' if files else None}
    info['hard'] = any(s['found'] for s in info['sources'].values())
    return info


def error_items(base: Path, scenario: str, codex: Path) -> list:
    """Error nodes of the events or session record that name a probe plugin."""
    objs = [('events', o) for o in read_events(base / 'raw' / f'{scenario}-events.jsonl')]
    folder = base / 'sessions' / scenario
    for path in sorted(folder.glob('*.jsonl')) if folder.is_dir() else []:
        objs += [('session-record', o) for o in read_events(path)]
    out, seen = [], set()
    for source, obj in objs:
        for node in walk(obj):
            if not isinstance(node, dict):
                continue
            if node.get('type') == 'error' or node.get('error') not in (None, '', {}, []):
                text = json.dumps(node, ensure_ascii=False)
                for v in sorted(set(re.findall(rf'{NAME}-(s[0-5])\b', text))):
                    if (v, text) not in seen:
                        seen.add((v, text))
                        out.append({'skill': v, 'duplicate': 'duplicate' in text.lower(), 'source': source,
                                    'scenario': scenario, 'text': scrub_text(re.sub(r'\s+', ' ', text), codex)[:240]})
    return out


def cache_facts(codex: Path, spec: dict) -> dict:
    root = codex / 'plugins' / 'cache' / NAME / spec['plugin']
    versions = sorted(p for p in root.glob('*') if p.is_dir()) if root.is_dir() else []
    out = {}
    for rel in [s['file'] for s in spec['skills']] + [l['path'] for l in spec['links']]:
        path = versions[0] / rel if versions else None
        if path is None or not os.path.lexists(path):
            out[rel] = {'present': False, 'kind': None, 'target': None}
        elif os.path.islink(path):
            out[rel] = {'present': True, 'kind': 'symlink', 'target': os.readlink(path)}
        else:
            out[rel] = {'present': True, 'kind': 'file' if path.is_file() else 'dir', 'target': None}
    return out


def cache_state(spec: dict, facts: dict) -> str:
    if not any(f['present'] for f in facts.values()):
        return 'not in cache'
    if spec['links']:
        kinds = [facts[l['path']]['kind'] for l in spec['links']]
        if None in kinds:
            return 'link missing'
        return 'symlinks kept' if all(k == 'symlink' for k in kinds) else 'links copied as files'
    return 'files' if all(facts[s['file']]['present'] for s in spec['skills']) else 'files missing'


def listed_path_values(var: dict) -> dict:
    """Judged on the resolved paths: root `resolved` (plugin-root SKILL.md) or `link` (codex/skills/...); sub `only` or `both`."""
    def paths(key):
        return [e['path'] for e in var['skills'][key]['entries'] if e['path'] != 'unresolved']
    root, sub = paths('root'), paths('sub')
    return {'root': ('link' if '/codex/skills/' in root[0] else 'resolved') if root else None,
            'sub': ('both' if any('/codex/skills/' not in p for p in sub) else 'only') if sub else None}


def decide_skills_outcome(s: dict):
    """(Outcome line, capture ref or None); the first matching rule wins."""
    phases = s['phases']
    ran = [p for p in phases.values() if p['ran']]
    if not ran or any(not p['hard'] for p in ran):
        return 'Outcome: open no hard source', None
    variants = s['variants']

    def count(v, key):
        return variants.get(v, {}).get('skills', {}).get(key, {}).get('count', 0)

    def ref(v, key):
        entries = variants.get(v, {}).get('skills', {}).get(key, {}).get('entries') or []
        return entries[0] if entries else None
    if phases['kit']['ran']:
        for v, var in variants.items():
            if not var['installed']:
                return f'Outcome: open {var["plugin"]} not installed', None
    if s['live']['root_listed']:
        return 'Outcome: listed-live', (s['live']['root_entries'] or [None])[0]
    if count('s0', 'root'):
        return 'Outcome: not-reproduced', ref('s0', 'root')
    if count('s3', 'root') == 1 and count('s3', 'sub'):
        return 'Outcome: fix manifest "./"', ref('s3', 'root')
    if count('s2', 'root') == 1 and count('s2', 'sub'):
        return 'Outcome: fix manifest absent', ref('s2', 'root')
    s5 = variants.get('s5')
    if s5:
        words = listed_path_values(s5)
        links_present = all(f['present'] for p, f in s5['cache'].items() if p.startswith('codex/'))
        if count('s5', 'root') == 1 and words['root'] and count('s5', 'sub') and links_present:
            return f'Outcome: fix folder {words["root"]} {words["sub"]}', ref('s5', 'root')
    if any(e['skill'] == 's5' and e['duplicate'] for e in s['errors']):
        reason = 'duplicate skill name'
    elif not count('s1', 'plain'):
        reason = 'path not honored'
    elif any(not count('s1', k) for k in ('named', 'big', 'front')):
        factor = next(k for k in ('named', 'big', 'front') if not count('s1', k))
        reason = 'content ' + {'named': 'name', 'big': 'size', 'front': 'frontmatter'}[factor]
    elif s5 is None or not count('s5', 'root') or not all(
            f['present'] for p, f in s5['cache'].items() if p.startswith('codex/')):
        reason = 'symlink not followed'
    else:
        reason = 'root not loaded'
    return f'Outcome: none {reason}', None


def cmd_summary_skills(args) -> int:
    base = Path(args.dir).resolve()
    out = Path(args.out).resolve() / 'probe-skills'
    caps = out / 'captures'
    if caps.exists():
        shutil.rmtree(caps)
    caps.mkdir(parents=True)
    codex = codex_home(args)
    specs = kit_skill_specs()
    desc = my_agent_descriptions(codex)
    live = evaluate_phase(base, 'skills-live', {'root': desc['root'], 'monitor': desc['monitor']}, caps, codex)
    kit_skills = {f'{v}:{sk["key"]}': sk['description'] for v, sp in specs.items() for sk in sp['skills']}
    kit_skills.update({'agent:root': desc['root'], 'agent:monitor': desc['monitor']})
    kit = evaluate_phase(base, 'skills-kit', kit_skills, caps, codex)
    installed_file = base / 'installed' / 'plugin-list.txt'
    installed = parse_installed(installed_file.read_text(encoding='utf-8')) if installed_file.is_file() else {}
    status = []
    for phase, info in (('live', live), ('kit', kit)):
        for source, item in info['sources'].items():
            status.append(f'{phase} {source}: read {"yes" if item["read"] else "no"}, '
                          f'listing entries found {"yes" if item["found"] else "no"} ({item["entries"]})')
    helps = ''.join((p.read_text(encoding='utf-8', errors='replace') + '\n')
                    for p in sorted((base / 'raw').glob('skills-live-help-*.txt')))
    help_match = re.search(r'(?im)^\s+skills?\b.*$|\bskills?\s+(?:list|ls)\b|\blist[- ]skills\b', helps)
    status.append(f'help: names a skill-listing command: {"yes" if help_match else "no"}')
    variants = {}
    cache_lines = []
    if kit['ran']:
        for v, spec in specs.items():
            skills = {}
            for sk in spec['skills']:
                entries = distinct_entries(kit['matches'][f'{v}:{sk["key"]}'])
                skills[sk['key']] = {'count': len(entries), 'entries': entries}
            facts = cache_facts(codex, spec)
            first = len(cache_lines) + 1
            cache_lines += [f'{v} {rel}: ' + ('absent' if not f['present'] else
                            (f'symlink -> {f["target"]}' if f['kind'] == 'symlink' else f['kind']))
                            for rel, f in facts.items()]
            state = installed.get(spec['plugin'], 'not installed')
            status.append(f'installed {spec["plugin"]}: {state}')
            variants[v] = {'plugin': spec['plugin'], 'changes': spec['changes'], 'installed': state == 'installed, enabled',
                           'skills': skills, 'cache': facts, 'cache_state': cache_state(spec, facts),
                           'cache_capture': {'capture': 'probe-skills/captures/cache-facts.txt', 'line': first}}
    errors = []
    for scenario, info in (('skills-live', live), ('skills-kit', kit)):
        if info['ran']:
            errors += error_items(base, scenario, codex)
    for e in errors:
        status.append(f'error item names {NAME}-{e["skill"]}{" (duplicate)" if e["duplicate"] else ""}: {e["text"][:120]}')
    write(caps / 'status.txt', '\n'.join(status) + '\n')
    if cache_lines:
        write(caps / 'cache-facts.txt', '\n'.join(cache_lines) + '\n')
    root_entries = distinct_entries(live['matches']['root'])
    monitor_entries = distinct_entries(live['matches']['monitor'])
    summary = {
        'codex_version': (base / 'codex-version.txt').read_text(encoding='utf-8').strip() if (base / 'codex-version.txt').is_file() else None,
        'phases': {'live': {k: live[k] for k in ('ran', 'hard', 'sources')}, 'kit': {k: kit[k] for k in ('ran', 'hard', 'sources')}},
        'live': {'ran': live['ran'], 'hard_source': live['hard'], 'root_description_known': bool(desc['root']),
                 'root_listed': bool(root_entries), 'monitor_listed': bool(monitor_entries),
                 'root_entries': root_entries, 'monitor_entries': monitor_entries},
        'variants': variants, 'errors': errors,
        'help': {'names_skill_listing_command': bool(help_match),
                 'line': help_match.group(0).strip() if help_match else None,
                 'capture': {'capture': 'probe-skills/captures/status.txt', 'line': len(status) - len(errors) - len(variants)}},
        'first_listing': live['first'] or kit['first'] or {'capture': 'probe-skills/captures/status.txt', 'line': 1},
        'status_capture': {'capture': 'probe-skills/captures/status.txt', 'line': 1},
        'listed_path': listed_path_values(variants['s5']) if 's5' in variants else None,
    }
    line, cite = decide_skills_outcome(summary)
    summary['outcome'] = line
    summary['outcome_capture'] = ({'capture': cite['capture'], 'line': cite['line']} if cite else summary['first_listing'])
    write(out / 'summary-skills.json', json.dumps(summary, indent=2, sort_keys=True) + '\n')
    if (base / 'run.log').is_file():
        write(out / 'run.log', scrub_text((base / 'run.log').read_text(encoding='utf-8'), codex))
    if not live['hard']:
        print('live: no hard source')
    else:
        print('live: root listed' if root_entries else 'live: root not listed')
    return 0


def cite_text(ref) -> str:
    return f'{ref["capture"]} line {ref["line"]}' if ref and ref.get('line') else (ref or {}).get('capture', '')


def cmd_findings_skills(args) -> int:
    out = Path(args.folder).resolve()
    sdir = out / 'probe-skills'
    s = load_json(sdir / 'summary-skills.json')
    outcome = s.get('outcome') or 'Outcome: open no summary-skills.json'
    variants = s.get('variants') or {}
    phases = s.get('phases') or {}
    live = s.get('live') or {}
    status = s.get('status_capture') or {'capture': 'probe-skills/captures/status.txt', 'line': 1}
    rows = []   # section, fact, value, ref, used_by

    def add(section, fact, value, ref, used='u27, u28, u14'):
        rows.append((section, fact, value, ref, used))
    add('Sources', 'Skill listing source', {p: {k: v['found'] for k, v in (i.get('sources') or {}).items()}
                                            for p, i in phases.items() if i.get('ran')} or None,
        s.get('first_listing'))
    add('Sources', 'Help texts name a skill-listing command', (s.get('help') or {}).get('names_skill_listing_command'),
        (s.get('help') or {}).get('capture'))
    if live.get('ran'):
        add('Live install', 'my-agent root skill listed in the live install', live.get('root_listed'),
            (live.get('root_entries') or [s.get('first_listing')])[0])
        add('Live install', 'my-agent monitor skill listed in the live install', live.get('monitor_listed'),
            (live.get('monitor_entries') or [s.get('first_listing')])[0])
    for v, var in variants.items():
        counts = {k: x['count'] for k, x in var['skills'].items()}
        entries = [e for x in var['skills'].values() for e in x['entries']]
        add('Variants', f'{v} listing entries per skill', counts, entries[0] if entries else status)
        add('Variants', f'{v} cache copy of the skill files', var.get('cache_state'), var.get('cache_capture'))
    names = [e['name'] for x in (variants.get('s1') or {'skills': {}})['skills'].values() for e in x['entries']]
    named = (variants.get('s1') or {'skills': {}})['skills'].get('named', {'entries': []})['entries']
    form = name_source = None
    if named:
        form = '<plugin>:<skill>' if re.match(r'^[\w.\-]+:[\w.\-]+$', named[0]['name']) else '<skill>'
        name_source = ('frontmatter name' if named[0]['name'].endswith(':ma-probe-s1-named') else
                       'folder name' if named[0]['name'].endswith('-dir') else 'unknown')
        add('Names', 'Form Codex lists a plugin skill in', {'form': form, 'example': named[0]['name']}, named[0])
        add('Names', 'Name Codex uses (folder or frontmatter)', name_source, named[0])
    lp = s.get('listed_path')
    s5_root = ((variants.get('s5') or {}).get('skills') or {}).get('root', {}).get('entries') or []
    if lp and (lp['root'] or lp['sub']):
        add('Listed path', 's5 listed path of the root skill and of the sub skill', lp, s5_root[0] if s5_root else status)
    add('Outcome', 'Plugin skill discovery outcome', outcome, s.get('outcome_capture'))
    by_section = {n: [] for n in SKILLS_SECTIONS}
    settled, opened = [], []
    for section, fact, value, ref, used in rows:
        ok = (value not in (None, '', [], {})) and bool(ref) and bool(ref.get('capture')) \
            and (out / ref['capture']).is_file()
        if ok:
            settled.append({'section': section, 'fact': fact, 'value': value, 'capture': ref['capture'],
                            'line': ref.get('line'), 'used_by': used})
            by_section[section].append(f'- {fact}: `{fmt_value(value)}` (`{ref["capture"]}` line {ref.get("line")})')
        else:
            opened.append({'section': section, 'fact': fact, 'used_by': used,
                           'why': 'no capture file found' if value not in (None, '', [], {}) else 'no value in the summary'})
    lines = ['# Codex findings: plugin skill discovery', '', f'Codex version: {s.get("codex_version") or "unknown"}', '']
    for section in SKILLS_SECTIONS:
        lines += [f'## {section}', '']
        if section == 'Outcome':
            lines.append(outcome)
        elif section == 'Open':
            lines += [f'- {o["fact"]} ({o["section"]}; needed by {o["used_by"]}): {o["why"]}' for o in opened] or ['- none']
        elif section == 'Variants':
            if variants:
                lines += ['| Variant | Changes | Root entries | Sub entries | Other skills listed | Listed name | Listed paths | Cache | Evidence |',
                          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
                for v, var in variants.items():
                    sk = var['skills']
                    entries = [e for x in sk.values() for e in x['entries']]
                    others = [k for k in sk if k not in ('root', 'sub') and sk[k]['count']]
                    lines.append('| ' + ' | '.join(cell(x) for x in [
                        v, var['changes'], sk['root']['count'], sk['sub']['count'] if 'sub' in sk else '-',
                        ', '.join(others) or '-', ', '.join(dict.fromkeys(e['name'] for e in entries)) or '-',
                        '; '.join(dict.fromkeys(e['path'] for e in entries)) or '-', var['cache_state'],
                        cite_text(entries[0]) if entries else '-']) + ' |')
                lines.append('')
            lines += by_section[section] or ['- no fact settled in this section']
        elif section == 'Listed path':
            if lp:
                lines += [f'- root skill: {lp["root"] or "not listed"}', f'- sub skill: {lp["sub"] or "not listed"}']
            lines += by_section[section] or ['- no fact settled in this section']
        else:
            lines += by_section[section] or ['- no fact settled in this section']
        lines.append('')
    lines += ['## Fact table', '', '| Fact | Capture | Used by unit |', '| --- | --- | --- |']
    lines += [f'| {r["fact"]} | `{r["capture"]}` line {r["line"]} | {r["used_by"]} |' for r in settled]
    out.mkdir(parents=True, exist_ok=True)
    (out / 'codex-findings-skills.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'codex-findings-skills.json').write_text(json.dumps(
        {'codex_version': s.get('codex_version'), 'outcome': outcome, 'facts': settled, 'open': opened},
        indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'{outcome}; {len(settled)} fact(s) settled, {len(opened)} open -> {out / "codex-findings-skills.md"}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='probe.py', description=__doc__.split('\n')[0])
    parser.add_argument('--codex', default='codex', help='path of the codex binary')
    parser.add_argument('--codex-home', default=None, help='Codex home folder (default $CODEX_HOME or ~/.codex)')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('kit')
    p.add_argument('dir')
    p.add_argument('--bump', action='store_true')
    p.add_argument('--change-market', action='store_true')
    p = sub.add_parser('run')
    p.add_argument('dir')
    p.add_argument('scenario', choices=SCENARIOS)
    p = sub.add_parser('snapshot')
    p.add_argument('--out', required=True)
    p.add_argument('--skills', default=None)
    p.add_argument('--cache', default=None)
    p = sub.add_parser('e2e-setup')
    p.add_argument('dir')
    p = sub.add_parser('e2e-request')
    p.add_argument('folder')
    p = sub.add_parser('e2e-collect')
    p.add_argument('dir')
    p.add_argument('--out', required=True)
    p = sub.add_parser('report')
    p.add_argument('e2e')
    p.add_argument('--findings', action='append', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('summary')
    p.add_argument('dir')
    p.add_argument('--out', required=True)
    p.add_argument('--config', default='~/.codex/config.toml')
    p = sub.add_parser('summary-identity')
    p.add_argument('dir')
    p.add_argument('--out', required=True)
    p = sub.add_parser('findings-identity')
    p.add_argument('folder')
    p = sub.add_parser('kit-skills')
    p.add_argument('dir')
    p = sub.add_parser('summary-skills')
    p.add_argument('dir')
    p.add_argument('--out', required=True)
    p = sub.add_parser('findings-skills')
    p.add_argument('folder')
    p = sub.add_parser('findings')
    p.add_argument('dir')
    p.add_argument('--out', required=True)
    p = sub.add_parser('check')
    p.add_argument('what', choices=['findings', 'report', 'install'])
    p.add_argument('file')
    p.add_argument('--e2e', default=None)
    p.add_argument('--probe-root', default=None)
    p.add_argument('--root', default=None)
    p.add_argument('--version', default=None)
    args = parser.parse_args(argv)
    return {'kit': cmd_kit, 'run': cmd_run, 'snapshot': cmd_snapshot, 'summary': cmd_summary,
            'summary-identity': cmd_summary_identity, 'findings-identity': cmd_findings_identity,
            'findings': cmd_findings, 'kit-skills': cmd_kit_skills, 'summary-skills': cmd_summary_skills,
            'findings-skills': cmd_findings_skills, 'check': cmd_check, 'e2e-setup': cmd_e2e_setup,
            'e2e-request': cmd_e2e_request, 'e2e-collect': cmd_e2e_collect, 'report': cmd_report}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())

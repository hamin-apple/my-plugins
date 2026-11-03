#!/usr/bin/env python3
"""Generate the Codex forms of the nine agents and the Codex manifest from the Claude sources.

usage: build-codex.py --write | --check | --install-agents | --check-agents [--root DIR] [--codex-home DIR]

Sources: the agent `.md` files listed in `.claude-plugin/plugin.json` and that file itself. Outputs, under the plugin
root: `codex/agents/my-agent-<role>.toml` (one per agent) and `.codex-plugin/plugin.json`.

Each agent file has `name` (`my-agent-<role>`: the name has no colon, which is unverified in an agent name; `ma_host` maps it
back to `my-agent:<role>`), `description` and `developer_instructions` (the `.md` body, verbatim). No model, effort, tools or
turn-limit key is written: the identity findings show Codex reading none of them, and the per-role model difference is
a gap row (decision D4). Nothing is read from `<data folder>/agent-models.json`.

The manifest copies name, version, description, author, skills and hooks (the shared `hooks.json`). It has no
`agents` key: the findings show no plugin place Codex loads agents from.

`--check` exits 1 and prints each file that differs or is missing, and each `codex/agents/*.toml` the build does not
produce; `--write` rewrites the files and removes those extra agent files (the folder holds generated files only). Exit 2 for bad arguments.

`--install-agents` copies the nine `codex/agents/*.toml` into `<codex home>/agents/` (`--codex-home`, else `$CODEX_HOME`, else
`~/.codex`), because Codex loads agents only from there. Line 1 of an installed file is `# my-agent <version>
(build-codex.py --install-agents)`, added at copy time; the repository files stay comment-free. It writes only the nine
named files, never deletes or renames, and leaves any same-named file without that comment (or a link or folder) as it is
(`skipped:`). `--check-agents` prints the same states without writing. Both end with the line `Codex agents: <form>`; exit 0
only when nothing was skipped (install) or all nine are up to date (check).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
COMMENT_RE = re.compile(r'^# my-agent (\S+) \(build-codex\.py --install-agents\)$')
MANIFEST_KEYS = ('name', 'version', 'description', 'author', 'skills', 'hooks')


def split_md(text: str):
    """(frontmatter dict, body) of an agent `.md`; the body starts after the closing `---` line."""
    head, body = text.split('\n---\n', 1)
    meta = {}
    for line in head.splitlines()[1:]:
        key, _, val = line.partition(':')
        meta[key.strip()] = val.strip()
    return meta, body


def toml_str(s: str) -> str:
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def toml_multiline(s: str) -> str:
    s = s.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
    return '"""\n' + s + '"""'


def codex_name(meta: dict) -> str:
    return 'my-agent-' + meta['name']


def agent_toml(meta: dict, body: str) -> str:
    name = codex_name(meta)
    return (f'name = {toml_str(name)}\n'
            f'description = {toml_str(meta["description"])}\n'
            f'developer_instructions = {toml_multiline(body)}\n')


def build(root: Path) -> dict:
    """{relative path: text} of every generated file."""
    plugin = json.loads((root / '.claude-plugin' / 'plugin.json').read_text())
    out = {}
    for ref in plugin['agents']:
        meta, body = split_md((root / ref).read_text())
        name = codex_name(meta)
        out[f'codex/agents/{name}.toml'] = agent_toml(meta, body)
    manifest = {k: plugin[k] for k in MANIFEST_KEYS}
    out['.codex-plugin/plugin.json'] = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    return out


def comment_line(version: str) -> str:
    return f'# my-agent {version} (build-codex.py --install-agents)\n'


def file_state(target: Path, text: str, version: str) -> str:
    """'missing', 'ok', 'stale:<old version>', 'stale:changed' or 'skipped' for one installed file."""
    if target.is_symlink():
        return 'skipped'
    if not target.exists():
        return 'missing'
    if not target.is_file():
        return 'skipped'
    try:
        line1, _, rest = target.read_bytes().decode('utf-8').partition('\n')
    except UnicodeDecodeError:
        return 'skipped'
    m = COMMENT_RE.match(line1)
    if not m:
        return 'skipped'
    if m.group(1) != version:
        return 'stale:' + m.group(1)
    return 'ok' if rest == text else 'stale:changed'


def summary(states: list, version: str) -> str:
    """The `Codex agents:` form for the states of the nine files, by the first rule that applies."""
    ok = states.count('ok')
    skipped = states.count('skipped')
    if skipped:
        return f'{ok} of 9 installed ({version}); {skipped} skipped'
    stale = []
    for s in states:
        if s.startswith('stale:') and s[6:] not in stale:
            stale.append(s[6:])
    if stale:
        return f'stale ({", ".join(stale)})'
    if ok == len(states):
        return f'installed 9 ({version})'
    if ok == 0:
        return 'not installed'
    return f'{ok} of 9 installed ({version})'


def agents_mode(root: Path, home: Path, install: bool) -> int:
    files = build(root)
    version = json.loads((root / '.claude-plugin' / 'plugin.json').read_text())['version']
    sources = {}
    for rel, text in files.items():
        if rel.startswith('codex/agents/'):
            p = root / rel
            if not p.is_file() or p.read_text() != text:
                print('build-codex: generated files differ; run --write first')
                return 1
            sources[rel.rsplit('/', 1)[1]] = text
    if not home.is_dir():
        print(f'build-codex: no Codex home at {home}; nothing installed')
        print(f'Codex agents: no Codex home ({home})')
        return 1
    folder = home / 'agents'
    if os.path.lexists(folder) and not folder.is_dir():
        print(f'build-codex: {folder} is not a folder; nothing installed')
        print('Codex agents: not installed')
        return 1
    if install:
        folder.mkdir(exist_ok=True)
    states = []
    for name, text in sources.items():
        target = folder / name
        state = file_state(target, text, version)
        if install and state != 'skipped':
            if state == 'ok':
                print(f'up to date: {name}')
            else:
                target.write_text(comment_line(version) + text)
                was = f' (was {state[6:]})' if state != 'missing' else ''
                print(f'installed: {name}{was}')
                state = 'ok'
        elif state == 'skipped':
            print(f'skipped: not generated by my-agent: {name}')
        elif state == 'missing':
            print(f'missing: {name}')
        elif state.startswith('stale:'):
            print(f'stale: {name} ({state[6:]})')
        else:
            print(f'up to date: {name}')
        states.append(state)
    print(f'Codex agents: {summary(states, version)}')
    if install:
        return 1 if 'skipped' in states else 0
    return 0 if all(s == 'ok' for s in states) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--install-agents', action='store_true')
    mode.add_argument('--check-agents', action='store_true')
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--codex-home', type=Path, default=None)
    args = ap.parse_args(argv)
    root = args.root
    if args.install_agents or args.check_agents:
        home = args.codex_home or Path(os.environ.get('CODEX_HOME') or '~/.codex').expanduser()
        return agents_mode(root, home, args.install_agents)
    files = build(root)
    if args.write:
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        agents = root / 'codex' / 'agents'
        if agents.is_dir():
            for p in sorted(agents.glob('*.toml')):
                if f'codex/agents/{p.name}' not in files:
                    p.unlink()
        return 0
    bad = [rel for rel, text in files.items()
           if not (root / rel).is_file() or (root / rel).read_text() != text]
    agents = root / 'codex' / 'agents'
    if agents.is_dir():
        bad += [f'codex/agents/{p.name}' for p in sorted(agents.glob('*.toml'))
                if f'codex/agents/{p.name}' not in files]
    for rel in bad:
        print(f'build-codex: differs: {rel}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

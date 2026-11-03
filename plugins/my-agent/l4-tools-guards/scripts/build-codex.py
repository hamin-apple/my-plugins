#!/usr/bin/env python3
"""Generate the Codex forms of the nine agents and the Codex manifest from the Claude sources.

usage: build-codex.py --write | --check [--root DIR]

Sources: the agent `.md` files listed in `.claude-plugin/plugin.json` and that file itself. Outputs, under the plugin
root: `codex/agents/my_agent_<role>.toml` (one per agent) and `.codex-plugin/plugin.json`.

Each agent file has `name` (`my_agent_<role>`: Codex allows only `[a-z0-9_]`; `ma_host` maps it back to
`my-agent:<role>`), `description` and `developer_instructions` (the `.md` body, verbatim). No model, effort, tools or
turn-limit key is written: the identity findings show Codex reading none of them, and the per-role model difference is
a gap row (decision D4). Nothing is read from `<data folder>/agent-models.json`.

The manifest copies name, version, description, author, skills and hooks (the shared `hooks.json`). It has no
`agents` key: the findings show no plugin place Codex loads agents from.

`--check` exits 1 and prints each file that differs or is missing; `--write` rewrites them. Exit 2 for bad arguments.
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
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


def agent_toml(meta: dict, body: str) -> str:
    name = 'my_agent_' + meta['name'].replace('-', '_')
    return (f'name = {toml_str(name)}\n'
            f'description = {toml_str(meta["description"])}\n'
            f'developer_instructions = {toml_multiline(body)}\n')


def build(root: Path) -> dict:
    """{relative path: text} of every generated file."""
    plugin = json.loads((root / '.claude-plugin' / 'plugin.json').read_text())
    out = {}
    for ref in plugin['agents']:
        meta, body = split_md((root / ref).read_text())
        name = 'my_agent_' + meta['name'].replace('-', '_')
        out[f'codex/agents/{name}.toml'] = agent_toml(meta, body)
    manifest = {k: plugin[k] for k in MANIFEST_KEYS}
    out['.codex-plugin/plugin.json'] = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)
    root = args.root
    files = build(root)
    if args.write:
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
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

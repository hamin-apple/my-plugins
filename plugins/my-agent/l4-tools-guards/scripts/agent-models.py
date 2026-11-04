#!/usr/bin/env python3
"""Print the model and effort of every my-agent agent for a preset (architecture 4.5).

usage: agent-models.py show --profile P --preset NAME [--data-dir DIR]
       agent-models.py show --plan PLAN.md
       agent-models.py presets --profile P [--data-dir DIR]

The presets are in `<data folder>/agent-models.json` (data folder: $MA_TASKS_DIR, else --data-dir, else
$CLAUDE_PLUGIN_OPTION_DATA_DIR, else ~/dev/log/my-agent); an agent or a key a preset leaves out keeps the value of
its definition file. A missing, empty or `{}` file, and a profile without presets, mean "no file": `show` prints
the definition values (for the preset `standard`) and `presets` prints `none`.

`show` prints a header and one line per agent (plugin.json order): `<agent> model=<m> effort=<e> pass=<fields>`,
where `pass=` lists the fields that differ from the definition file (`-` for none): the Agent call arguments L1
passes. An inline role (model value `inline`) prints `model=inline effort=- pass=inline`: `pass=inline` means no Agent
call, L1 performs the role itself (SKILL.md "Inline role"). `show --plan` reads the `## Models` table of a plan.md instead of the file. `presets` prints one line per
preset of the profile (`standard` first when present): the name, and after `: ` what differs from the definition.
Takes no --task-dir.

On the Codex host (ma_host.env_host()) the values come from the `codex` section of the file: the installed agent
files carry no model or effort, so the no-argument value is `-` and `pass=` lists the fields an entry sets. Without a
`codex` section `standard` prints every role as `model=- effort=- pass=-` (header `no codex section: no override`).
`show --plan` then takes Codex models (or `-`) in the model cells. Exit 0 on success, 1 for a rejected file, preset or table (one stderr line
`agent-models: <cause>`, nothing on stdout), 2 for bad arguments.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_data  # noqa: E402
import ma_host  # noqa: E402
import ma_models  # noqa: E402


def render(header, defs, values, width=6) -> str:
    fields = ma_models.diff(defs, values)
    lines = [header]
    for agent in defs:
        model, effort = values[agent]
        lines.append(f"{agent:<13}  model={model:<{width}} effort={effort:<6}  pass={','.join(fields[agent]) or '-'}")
    return '\n'.join(lines)


def _codex() -> bool:
    return ma_host.env_host() == 'codex'


def show(args) -> str:
    defs = ma_models.definitions()
    if _codex():
        defs = ma_models.codex_definitions(defs)
    if args.plan:
        try:
            text = Path(args.plan).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            raise ma_models.ModelsError(f'cannot read {args.plan}: {exc}')
        name, values = ma_models.parse_plan(text, defs, codex=_codex())
        return render(f'preset: {name} (plan.md ## Models)', defs, values, 10 if _codex() else 6)
    path, data = ma_models.load(ma_data.data_dir(args.data_dir), defs)
    profile = _profile(args.profile, data)
    if _codex():
        data = ma_models.codex_section(data)
        values = ma_models.resolve(data, profile, args.preset, defs)
        where = f'file {path}, codex section' if data.get(profile) else 'no codex section: no override'
        return render(f'preset: {profile}/{args.preset} ({where})', defs, values, 10)
    values = ma_models.resolve(data, profile, args.preset, defs)
    where = f'file {path}' if (data or {}).get(profile) else 'no file: definition values'
    return render(f'preset: {profile}/{args.preset} ({where})', defs, values)


def _profile(name, data):
    if name not in ma_models.PROFILES:
        raise ma_models.ModelsError(f'unknown profile "{name}" (profiles: {", ".join(ma_models.PROFILES)})')
    return name


def presets(args) -> str:
    defs = ma_models.definitions()
    if _codex():
        defs = ma_models.codex_definitions(defs)
    _, data = ma_models.load(ma_data.data_dir(args.data_dir), defs)
    profile = _profile(args.profile, data)
    if _codex():
        data = ma_models.codex_section(data)
    names = ma_models.preset_names(data, profile)
    if not names:
        return 'none'
    lines = []
    for name in names:
        text = ma_models.summary(defs, ma_models.merge(defs, data[profile][name]))
        lines.append(f'{name}: {text}' if text else name)
    return '\n'.join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('show')
    s.add_argument('--profile')
    s.add_argument('--preset')
    s.add_argument('--plan', metavar='PLAN.md')
    s.add_argument('--data-dir', help='the my-agent data folder (default: the setting, else ~/dev/log/my-agent)')
    p = sub.add_parser('presets')
    p.add_argument('--profile', required=True)
    p.add_argument('--data-dir', help='the my-agent data folder (default: the setting, else ~/dev/log/my-agent)')
    args = ap.parse_args(argv)
    if args.cmd == 'show' and not args.plan and not (args.profile and args.preset):
        ap.error('show needs --profile and --preset, or --plan')
    try:
        out = show(args) if args.cmd == 'show' else presets(args)
    except ma_models.ModelsError as exc:
        print(f'agent-models: {exc}', file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())

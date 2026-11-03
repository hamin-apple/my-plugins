"""Model presets: `<data folder>/agent-models.json` over the agent definition values (architecture 4.5).

File shape: {"<profile>": {"<preset>": {"<agent>": {"model": ..., "effort": ...}}}}. Both keys of an agent entry are
optional; a missing key (or a missing agent) keeps the definition value. A missing, empty or `{}` file means "no file".
The main session (L1) has no entry: it stays opus.

An optional top-level key `"codex"` holds the presets of the Codex host with the same nesting:
{"codex": {"<profile>": {"<preset>": {"<agent>": {"model": <one of CODEX_MODELS>, "effort": ...}}}}}. On Codex the
installed agent files carry no model or effort, so the "definition" is `-` (Codex chooses) and `pass=` lists the
fields an entry sets. The Claude host ignores the section.
"""
import json
import re
from pathlib import Path

import ma_schema

FILE_NAME = 'agent-models.json'
PROFILES = ('general', 'research', 'dev')
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
MODELS = ('opus', 'sonnet', 'haiku', 'fable')   # the families of ma_schema.FAMILY
CODEX_MODELS = ('gpt-6-luna', 'gpt-5.6-terra', 'gpt-5.6-luna')   # the ids the spawn tool lists
CODEX_KEY = 'codex'
STANDARD = 'standard'
KEYS = ('model', 'effort')
PLUGIN_ROOT = Path(__file__).resolve().parents[2]


class ModelsError(Exception):
    """A rejected file, preset or table; str() is the cause (the script prints `agent-models: <cause>`)."""


def definitions(root=None) -> dict:
    """{agent: {'model', 'effort', 'level'}} from the frontmatter of the agents in plugin.json, in its order."""
    root = Path(root or PLUGIN_ROOT)
    try:
        listed = json.loads((root / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')).get('agents') or []
    except (OSError, ValueError) as exc:
        raise ModelsError(f'cannot read plugin.json in {root}: {exc}')
    out = {}
    for rel in [listed] if isinstance(listed, str) else listed:
        try:
            text = (root / rel).read_text(encoding='utf-8')
        except OSError as exc:
            raise ModelsError(f'cannot read agent definition {rel}: {exc}')
        m = re.match(r'---\n(.*?)\n---', text, re.S)
        front = {}
        for line in (m.group(1).splitlines() if m else []):
            key, sep, value = line.partition(':')
            if sep:
                front[key.strip()] = value.strip().strip('\'"')
        out[Path(rel).stem] = {'model': front.get('model', '-'), 'effort': front.get('effort', '-'),
                               'level': front.get('level', '')}
    return out


def codex_definitions(defs) -> dict:
    """`defs` with the Codex no-argument values (`-`, `-`): the installed agent files set no model or effort."""
    return {a: dict(d, model='-', effort='-') for a, d in defs.items()}


def _check_entry(where, entry, models=MODELS):
    if not isinstance(entry, dict):
        raise ModelsError(f'{where}: agent entry is not a dictionary')
    if 'model' in entry and entry['model'] not in models:
        raise ModelsError(f'{where}: unknown model "{entry["model"]}" (one of: {", ".join(models)})')
    if 'effort' in entry and entry['effort'] not in EFFORTS:
        raise ModelsError(f'{where}: unknown effort "{entry["effort"]}" (one of: {", ".join(EFFORTS)})')


def validate(data, agents=None) -> dict:
    """The whole file checked; returns `data`. `agents`: agent names (default: those of plugin.json)."""
    agents = list(agents if agents is not None else definitions())
    if not isinstance(data, dict):
        raise ModelsError('the file is not a JSON object')
    for profile, presets in data.items():
        if profile == CODEX_KEY:
            _validate_codex(presets, agents)
            continue
        if profile not in PROFILES:
            raise ModelsError(f'unknown profile "{profile}" (profiles: {", ".join(PROFILES)})')
        if not isinstance(presets, dict):
            raise ModelsError(f'{profile}: profile is not a dictionary')
        for preset, entries in presets.items():
            if not isinstance(entries, dict):
                raise ModelsError(f'{profile}/{preset}: preset is not a dictionary')
            for agent, entry in entries.items():
                if agent == 'main':
                    raise ModelsError(f'{profile}/{preset}: unknown agent "main" '
                                      '(the main session stays opus and has no entry)')
                if agent not in agents:
                    raise ModelsError(f'{profile}/{preset}: unknown agent "{agent}"')
                _check_entry(f'{profile}/{preset}/{agent}', entry)
    return data


def _validate_codex(section, agents):
    if not isinstance(section, dict):
        raise ModelsError(f'{CODEX_KEY}: section is not a dictionary')
    for profile, presets in section.items():
        if profile not in PROFILES:
            raise ModelsError(f'{CODEX_KEY}: unknown profile "{profile}" (profiles: {", ".join(PROFILES)})')
        if not isinstance(presets, dict):
            raise ModelsError(f'{CODEX_KEY}/{profile}: profile is not a dictionary')
        for preset, entries in presets.items():
            if not isinstance(entries, dict):
                raise ModelsError(f'{CODEX_KEY}/{profile}/{preset}: preset is not a dictionary')
            for agent, entry in entries.items():
                if agent == 'main':
                    raise ModelsError(f'{CODEX_KEY}/{profile}/{preset}: unknown agent "main" '
                                      '(the main session has no entry)')
                if agent not in agents:
                    raise ModelsError(f'{CODEX_KEY}/{profile}/{preset}: unknown agent "{agent}"')
                _check_entry(f'{CODEX_KEY}/{profile}/{preset}/{agent}', entry, CODEX_MODELS)


def codex_section(data) -> dict:
    """The `codex` section of the loaded file ({} when there is none)."""
    return (data or {}).get(CODEX_KEY) or {}


def load(data_dir, agents=None):
    """(path, data) of `<data folder>/agent-models.json`; data is None for a missing, empty or `{}` file.
    Raises ModelsError for a file that cannot be used."""
    path = Path(data_dir) / FILE_NAME
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return path, None
    except (OSError, UnicodeDecodeError) as exc:
        raise ModelsError(f'cannot read {path}: {exc}')
    if not text.strip():
        return path, None
    try:
        data = json.loads(text)
    except ValueError as exc:
        where = f' (line {exc.lineno} column {exc.colno})' if isinstance(exc, json.JSONDecodeError) else ''
        raise ModelsError(f'invalid JSON in {path}: {getattr(exc, "msg", exc)}{where}')
    if data == {}:
        return path, None
    return path, validate(data, agents)


def preset_names(data, profile) -> list:
    """The presets of `profile`, `standard` first when present, else file order."""
    names = list(((data or {}).get(profile) or {}))
    return ([STANDARD] if STANDARD in names else []) + [n for n in names if n != STANDARD]


def merge(defs, entries) -> dict:
    """{agent: (model, effort)}: the definition values with a preset's entries laid over them."""
    out = {}
    for agent, d in defs.items():
        entry = (entries or {}).get(agent) or {}
        out[agent] = (entry.get('model', d['model']), entry.get('effort', d['effort']))
    return out


def diff(defs, values) -> dict:
    """{agent: [fields that differ from the definition]} (the `pass=` column), in `defs` order."""
    return {a: [k for k, v, d in (('model', values[a][0], defs[a]['model']), ('effort', values[a][1], defs[a]['effort']))
                if v != d] for a in defs}


def resolve(data, profile, preset, defs):
    """{agent: (model, effort)} for `profile/preset`. Raises ModelsError when the preset is not in the file;
    `standard` without such a preset (no file, no presets for the profile) is the definition values."""
    presets = (data or {}).get(profile) or {}
    if preset not in presets:
        if preset == STANDARD and not presets:
            return merge(defs, {})
        names = ', '.join(preset_names(data, profile)) or 'none'
        raise ModelsError(f'{profile} has no preset "{preset}" (presets: {names})')
    return merge(defs, presets[preset])


def summary(defs, values) -> str:
    """The popup line for one preset: the agents whose values differ from the definition ('' when none). When
    the five L2 agents end up equal (and differ from the definition) they are named `judges`."""
    changed = {a for a, f in diff(defs, values).items() if f}
    judges = [a for a, d in defs.items() if d['level'] == 'L2']
    parts = []
    if len(judges) == 5 and len({values[a] for a in judges}) == 1 and changed >= set(judges):
        parts.append('judges %s/%s' % values[judges[0]])
        changed -= set(judges)
    parts += ['%s %s/%s' % ((a,) + values[a]) for a in defs if a in changed]
    return ', '.join(parts)


def parse_plan(text, defs, codex=False) -> tuple:
    """(preset name, {agent: (model, effort)}) from the `## Models` section of a plan.md. A model or effort cell
    that is empty or `-` keeps the definition value, as does an agent missing from the table.
    Raises ModelsError when the section, the `Preset:` line or a value is not usable. `codex`: the model cells are
    Codex models (`defs` then holds the `-` no-argument values)."""
    lines = ma_schema.section_lines(text, 'Models')
    if lines is None:
        raise ModelsError('plan.md has no ## Models section')
    name = None
    entries = {}
    for line in lines:
        s = line.strip()
        m = re.match(r'Preset:\s*(\S+)', s)
        if m and name is None:
            name = m.group(1)
            continue
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 3 or cells[0].lower() == 'agent' or set(''.join(cells[:3])) <= set('-: '):
            continue
        agent, model, effort = cells[:3]
        if agent == 'main':
            raise ModelsError('plan.md ## Models: unknown agent "main" (the main session stays opus and has no entry)')
        if agent not in defs:
            raise ModelsError(f'plan.md ## Models: unknown agent "{agent}"')
        entry = {k: v for k, v in (('model', model), ('effort', effort)) if v not in ('', '-')}
        _check_entry(f'plan.md ## Models/{agent}', entry, CODEX_MODELS if codex else MODELS)
        entries[agent] = entry
    if name is None:
        raise ModelsError('plan.md ## Models has no "Preset:" line')
    return name, merge(defs, entries)

#!/usr/bin/env python3
"""Build the my-agent architecture page for GitHub Pages: docs/architecture.html (repository root).

usage: build-docs.py            write docs/architecture.html (and docs/.nojekyll)
       build-docs.py --check    exit 1 when docs/architecture.html is not what the sources give now (nothing written)

Everything on the page is read from the plugin's own files: plugin.json, the agent definitions, SKILL.md, the phase
and profile files, hooks.json, permissions.json, the L4 scripts and lib docstrings, `ma_schema` (formats),
scope-guard's `rules()` (read and write scopes) and, for what has no runtime form (the level table, L1's four
components, the 8-step table, the gate table), my-agent-architecture.md. ARTIFACTS, STEP_RULES and L1_SOURCES below
only say where to look; a heading that cannot be found stops the build, so a renamed heading shows up at once.
The page itself (tools/docs-template.html) is static: no server, no network.
"""
import argparse
import ast
import html
import importlib.util
import io
import json
import re
import sys
import tokenize
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / 'plugins' / 'my-agent'
L4 = PLUGIN / 'l4-tools-guards'
ARCH = PLUGIN / 'docs' / 'build-guide' / 'my-agent-architecture.md'
TEMPLATE = Path(__file__).resolve().parent / 'docs-template.html'
OUT = REPO / 'docs' / 'architecture.html'

sys.path.insert(0, str(L4 / 'lib'))
import ma_schema  # noqa: E402
import ma_usage  # noqa: E402

PROFILES = ('general', 'research', 'dev')
LOC, TASK = Path('/LOC'), Path('/LOC/docs/agent/TASK')   # stand-ins for scope-guard's rules()

# Task-folder files (architecture 4.7 tree) → steps, who writes, where the format is written down.
# A source is (file relative to the plugin, kind, key): kind 'h' = heading, 'b' = bold paragraph title,
# 'fence' = the fenced block holding `key`, 'item' = numbered list item under heading key[0] starting with key[1],
# 'doc' = a Python file's docstring.
ARTIFACTS = [
    ('.active', ['1'], 'L1', [('SKILL.md', 'h', '`.active` rules')]),
    ('.gitignore', ['1'], 'L1', [('SKILL.md', 'item', ('Intake (step 1, Router)', '5.'))]),
    ('intake.md', ['1'], 'L1 Router', [('SKILL.md', 'fence', 'Status: active')]),
    ('run-log.md', ['1', '2', '3', '4', '5', '6', '7', '8'], 'L1 Recorder · L4 hooks',
     [(ARCH, 'b', 'line format'), (ARCH, 'b', 'who records what')]),
    ('explore.md', ['2'], 'my-agent:explorer (L1 saves the report)',
     [('l3-workers/agents/explorer.md', 'h', 'Report format')]),
    ('scope.md', ['2'], 'L1', [('l1-orchestration/phases/define.md', 'item', ('2. Explore → Scope', '4.'))]),
    ('plan.md', ['3', 'G1b'], 'my-agent:architect · L1 (Approval, Prototype, Revisions lines)',
     [('l2-design-judge/agents/architect.md', 'h', '`plan.md` sections')]),
    ('plan-review.md', ['4'], 'my-agent:plan-reviewer',
     [('l2-design-judge/agents/plan-reviewer.md', 'h', '`plan-review.md` format')]),
    ('prototype/', ['G1b'], 'my-agent:writer', [('l3-workers/agents/writer.md', 'h', 'Rules per job')]),
    ('work/', ['5', '6'], 'my-agent:researcher · my-agent:writer',
     [('l3-workers/agents/researcher.md', 'h', 'Note format'), ('l3-workers/agents/writer.md', 'h', 'Rules per job')]),
    ('verify.md', ['7'], 'my-agent:verifier', [('l2-design-judge/agents/verifier.md', 'h', '`verify.md` format')]),
    ('review.md', ['8'], 'my-agent:reviewer', [('l2-design-judge/agents/reviewer.md', 'h', '`review.md` format')]),
    ('deliverable/', ['8'], 'L1', [(ARCH, 'b', 'Storing the deliverable after G3')]),
    ('gate-tally.md', ['R'], 'L4 gate-report.py tally', [('l2-design-judge/agents/gate-analyst.md', 'h', 'Input')]),
    ('gate-report.md', ['R'], 'my-agent:gate-analyst',
     [('l2-design-judge/agents/gate-analyst.md', 'h', '`gate-report.md` format')]),
    ('main-usage.json', ['R'], 'L4 usage-snapshot.py', [('l4-tools-guards/lib/ma_usage.py', 'doc', None)]),
    ('archive/', ['G1b', '5', 'R'], 'L1', [(ARCH, 'h', '4.8.1 Change requests during a task')]),
    ('.archived/<task-id>/', ['R'], 'the person (archive-tasks.py)',
     [('l4-tools-guards/scripts/archive-tasks.py', 'doc', None)]),
]

# The L1 procedure for each step, as the phase files write it.
STEP_RULES = {
    '1': [('SKILL.md', 'Intake (step 1, Router)')],
    '2': [('l1-orchestration/phases/define.md', '2. Explore → Scope')],
    '3': [('l1-orchestration/phases/plan.md', '3. Plan')],
    '4': [('l1-orchestration/phases/plan.md', '4. Plan Review'), ('l1-orchestration/phases/plan.md', 'G1b plan approval')],
    '5': [('l1-orchestration/phases/build.md', '5. Execute'), ('l1-orchestration/phases/build.md', 'Workflow rules')],
    '6': [('l1-orchestration/phases/build.md', '6. Merge')],
    '7': [('l1-orchestration/phases/accept.md', '7. Verify'), ('l1-orchestration/phases/accept.md', 'Back to Execute')],
    '8': [('l1-orchestration/phases/accept.md', '8. Review → Deliver'),
          ('l1-orchestration/phases/accept.md', 'G3 in the dev profile'),
          ('l1-orchestration/phases/accept.md', 'E escalation')],
    'R': [('l1-orchestration/phases/accept.md', 'Retrospective')],
}

# Where each L1 component's rules are written (besides the steps it leads in the 4.3 table).
L1_SOURCES = {
    'Router': [('SKILL.md', 'h', 'Arguments')],
    'Orchestrator': [('SKILL.md', 'h', 'Phase files'), ('SKILL.md', 'h', 'Change requests'),
                     ('SKILL.md', 'h', 'Data and instructions')],
    'Gatekeeper': [('SKILL.md', 'h', 'Question rules'), ('SKILL.md', 'h', 'Gates')],
    'Recorder': [(ARCH, 'b', 'who records what'), (ARCH, 'b', 'Popup records')],
}


class SourceError(Exception):
    pass


def read(path) -> str:
    p = path if isinstance(path, Path) else PLUGIN / path
    return p.read_text(encoding='utf-8')


def rel(path) -> str:
    p = path if isinstance(path, Path) else PLUGIN / path
    return str(p.relative_to(REPO))


# --- Markdown cutting -----------------------------------------------------------------------------------------

HEAD = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
BOLD_LINE = re.compile(r'^\*\*(.+?)\*\*(\s*\[[a-z ]+\])?\s*$')


def outline(lines):
    """(index, depth, title) of every Markdown heading outside fenced blocks."""
    fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith('```'):
            fence = not fence
            continue
        m = None if fence else HEAD.match(line)
        if m:
            yield i, len(m.group(1)), m.group(2)


def cut(text: str, title: str, where='') -> str:
    """Body of the first heading whose title starts with `title`, up to the next heading at its depth or above."""
    lines = text.splitlines()
    heads = list(outline(lines))
    for k, (i, depth, t) in enumerate(heads):
        if t.startswith(title):
            end = next((j for j, d, _ in heads[k + 1:] if d <= depth), len(lines))
            return '\n'.join(lines[i + 1:end]).strip('\n')
    raise SourceError(f'{where}: heading {title!r} not found')


def cut_bold(text: str, title: str, where='') -> str:
    """Body under a bold-only paragraph line `**<title…>**`, up to the next bold-only line or heading."""
    lines = text.splitlines()
    heads = {i for i, _, _ in outline(lines)}
    for i, line in enumerate(lines):
        m = BOLD_LINE.match(line)
        if m and m.group(1).startswith(title):
            end = next((j for j in range(i + 1, len(lines)) if j in heads or BOLD_LINE.match(lines[j])), len(lines))
            return '\n'.join(lines[i + 1:end]).strip('\n')
    raise SourceError(f'{where}: bold title {title!r} not found')


def fence_with(text: str, needle: str, where='') -> str:
    for m in re.finditer(r'```[a-z]*\n(.*?)\n\s*```', text, re.S):
        if needle in m.group(1):
            return '```text\n' + '\n'.join(l.strip() if not l.startswith('   ') else l[3:] for l in m.group(1).splitlines()) + '\n```'
    raise SourceError(f'{where}: no fenced block with {needle!r}')


def list_item(text: str, prefix: str, where='') -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(prefix + ' '):
            end = next((j for j in range(i + 1, len(lines)) if re.match(r'^(\d+\.\s|#)', lines[j])), len(lines))
            return '\n'.join(lines[i:end]).strip('\n')
    raise SourceError(f'{where}: list item {prefix!r} not found')


def split_row(line: str) -> list:
    """Cells of a pipe-table row; `|` inside backticks or written `\\|` stays in the cell."""
    cells, cur, tick = [], '', False
    s = line.strip()
    s = s[1:] if s.startswith('|') else s
    s = s[:-1] if s.endswith('|') and not s.endswith('\\|') else s
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '\\' and i + 1 < len(s) and s[i + 1] == '|':
            cur += '|'
            i += 2
            continue
        if ch == '`':
            tick = not tick
        if ch == '|' and not tick:
            cells.append(cur.strip())
            cur = ''
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def table(text: str, where='') -> list:
    """Rows (header first) of the first pipe table in `text`."""
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        if lines[i].lstrip().startswith('|') and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            rows = [split_row(lines[i])]
            for line in lines[i + 2:]:
                if not line.lstrip().startswith('|'):
                    break
                rows.append(split_row(line))
            return rows
    raise SourceError(f'{where}: no table')


def source(spec) -> dict:
    """{title, from, html} for one (file, kind, key) source."""
    path, kind, key = spec
    where = rel(path)
    if kind == 'doc':
        body = ast.get_docstring(ast.parse(read(path))) or ''
        return {'title': Path(path).name + ' (docstring)', 'from': where, 'html': md(body)}
    text = read(path)
    if kind == 'h':
        return {'title': key, 'from': where, 'html': md(cut(text, key, where))}
    if kind == 'b':
        return {'title': key, 'from': where, 'html': md(cut_bold(text, key, where))}
    if kind == 'fence':
        return {'title': 'template', 'from': where, 'html': md(fence_with(text, key, where))}
    if kind == 'item':
        head, prefix = key
        return {'title': f'{head} · item {prefix}', 'from': where,
                'html': md(re.sub(r'^\d+\.\s+', '', list_item(cut(text, head, where), prefix, where)))}
    raise ValueError(kind)


# --- Markdown → HTML (the subset the plugin files use) ---------------------------------------------------------

INLINE_CODE = re.compile(r'(``.+?``|`[^`]+`)')


def inline(s: str) -> str:
    out = []
    for part in INLINE_CODE.split(s):
        if part.startswith('``') and part.endswith('``') and len(part) > 4:
            out.append(f'<code>{html.escape(part[2:-2].strip())}</code>')
        elif part.startswith('`') and part.endswith('`') and len(part) > 1:
            out.append(f'<code>{html.escape(part[1:-1])}</code>')
        else:
            t = html.escape(part, quote=False)
            t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
            t = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', t)
            t = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'\1', t)
            t = t.replace('&lt;br/&gt;', '<br>').replace('&lt;br&gt;', '<br>')
            out.append(t)
    return ''.join(out)


LIST_ITEM = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)$')


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def is_table_start(lines, i) -> bool:
    return (i + 1 < len(lines) and lines[i].lstrip().startswith('|')
            and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]) is not None)


def dedent(lines) -> list:
    width = min((indent(l) for l in lines if l.strip()), default=0)
    return [l[width:] for l in lines]


def md(text: str) -> str:
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith('```'):
            lang = line.strip()[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith('```'):
                j += 1
            body = '\n'.join(dedent(lines[i + 1:j]))
            out.append(f'<pre class="code" data-lang="{html.escape(lang)}"><code>{html.escape(body)}</code></pre>')
            i = j + 1
            continue
        m = HEAD.match(line)
        if m:
            depth = min(len(m.group(1)) + 2, 6)
            out.append(f'<h{depth}>{inline(m.group(2))}</h{depth}>')
            i += 1
            continue
        if is_table_start(lines, i):
            rows = [split_row(lines[i])]
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith('|'):
                rows.append(split_row(lines[j]))
                j += 1
            head = ''.join(f'<th>{inline(c)}</th>' for c in rows[0])
            body = ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in rows[1:])
            out.append(f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            i = j
            continue
        lm = LIST_ITEM.match(line)
        if lm:
            base = indent(line)
            ordered = lm.group(2)[0].isdigit()
            items, j = [], i
            while j < len(lines):
                cur = lines[j]
                im = LIST_ITEM.match(cur)
                if im and indent(cur) == base and im.group(2)[0].isdigit() == ordered:
                    items.append([im.group(3), []])
                    j += 1
                    continue
                if cur.strip() and indent(cur) > base:
                    items[-1][1].append(cur)
                    j += 1
                    continue
                if not cur.strip() and j + 1 < len(lines) and lines[j + 1].strip() and indent(lines[j + 1]) > base:
                    items[-1][1].append('')
                    j += 1
                    continue
                break
            start = re.match(r'\d+', lm.group(2))
            tag = 'ol' if ordered else 'ul'
            attr = f' start="{start.group(0)}"' if ordered and start.group(0) != '1' else ''
            body = ''.join(f'<li>{inline(first)}{md(chr(10).join(dedent(rest))) if rest else ""}</li>'
                           for first, rest in items)
            out.append(f'<{tag}{attr}>{body}</{tag}>')
            i = j
            continue
        para = [line.strip()]
        j = i + 1
        while (j < len(lines) and lines[j].strip() and not lines[j].lstrip().startswith('```')
               and not HEAD.match(lines[j]) and not LIST_ITEM.match(lines[j]) and not is_table_start(lines, j)):
            para.append(lines[j].strip())
            j += 1
        out.append(f'<p>{inline(" ".join(para))}</p>')
        i = j
    return ''.join(out)


# --- extraction ------------------------------------------------------------------------------------------------

def frontmatter(text: str):
    m = re.match(r'---\n(.*?)\n---\n(.*)', text, re.S)
    if not m:
        raise SourceError('no frontmatter')
    fm = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(':')
        fm[key.strip()] = value.strip().strip('"\'')
    return fm, m.group(2)


def docstring(path: Path) -> str:
    """First paragraph of a Python file's docstring, on one line."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding='utf-8'))) or ''
    return ' '.join(doc.split('\n\n')[0].split())


def body_sections(body: str) -> tuple:
    """(role paragraph, [{title, html}]) of an agent definition body."""
    lines = body.splitlines()
    heads = [(i, d, t) for i, d, t in outline(lines)]
    top = next(i for i, d, _ in heads if d == 1)
    first2 = next((i for i, d, _ in heads if d == 2), len(lines))
    role = md('\n'.join(lines[top + 1:first2]))
    secs = []
    level2 = [(i, t) for i, d, t in heads if d == 2]
    for k, (i, t) in enumerate(level2):
        end = level2[k + 1][0] if k + 1 < len(level2) else len(lines)
        secs.append({'title': t, 'html': md('\n'.join(lines[i + 1:end]))})
    return role, secs


def scope_guard():
    spec = importlib.util.spec_from_file_location('scope_guard', L4 / 'hooks' / 'scope-guard.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def show_path(p: Path) -> str:
    s = str(p)
    s = s.replace(str(TASK), '<task folder>').replace(str(LOC), '<task location>')
    return s


def agent_scope(sg, role: str) -> dict:
    class Active:
        location, task_dir = LOC, TASK
    r = sg.rules(role, Active, LOC)
    uniq = lambda ps: list(dict.fromkeys(show_path(p) for p in ps))   # noqa: E731
    return {'read': uniq(r.read), 'write': uniq(r.write), 'denyWrite': uniq(r.deny_write),
            'bashWrites': r.bash_writes, 'web': r.web}


def agents(sg) -> list:
    manifest = json.loads(read('.claude-plugin/plugin.json'))
    out = []
    for path in manifest['agents']:
        fm, body = frontmatter(read(path.lstrip('./')))
        name = fm['name']
        role, secs = body_sections(body)
        out.append({
            'id': name, 'call': f'my-agent:{name}', 'level': fm.get('level'), 'model': fm.get('model'),
            'effort': fm.get('effort'), 'maxTurns': fm.get('maxTurns'), 'description': fm.get('description'),
            'tools': [t.strip() for t in fm.get('tools', '').split(',') if t.strip()],
            'file': rel(path.lstrip('./')), 'role': role, 'sections': secs, 'scope': agent_scope(sg, name),
            'beforeApproval': name in ma_schema.BEFORE_APPROVAL, 'unitAgent': name in ma_schema.UNIT_AGENTS,
        })
    return out


def mermaid_levels(arch_42: str) -> dict:
    """{L1: {title, comps: [(name, sub)]}} from the 4.2 flowchart."""
    block = re.search(r'```mermaid\n(.*?)```', arch_42, re.S).group(1)
    out, cur = {}, None
    for line in block.splitlines():
        sg = re.match(r'\s*subgraph (L\d)\["(.*)"\]', line)
        if sg:
            cur = sg.group(1)
            out[cur] = {'title': sg.group(2), 'comps': []}
            continue
        if line.strip() == 'end':
            cur = None
            continue
        if cur:
            for _, label in re.findall(r'(\w+)\["([^"]+)"\]', line):
                name, _, sub = label.partition('<br/>')
                sub = sub.strip()
                if sub.startswith('(') and sub.endswith(')'):
                    sub = sub[1:-1]
                out[cur]['comps'].append((name.strip(), sub))
    return out


def levels(arch: str, agent_list, steps) -> list:
    sec = cut(arch, '4.2 Structure: four levels', 'arch')
    graph = mermaid_levels(sec)
    rows = table(sec, 'arch 4.2')
    head = rows[0]
    out = []
    for row in rows[1:]:
        cells = dict(zip(head, row))
        lid = re.search(r'L\d', cells['Level']).group(0)
        title = graph[lid]['title']
        lv = {'id': lid, 'name': re.sub(r'\*\*|L\d\s*', '', cells['Level']).strip(),
              'title': title, 'runsIn': inline(cells['Runs in']), 'sees': inline(cells['Information it sees']),
              'output': inline(cells['Output']), 'cannot': inline(cells['What it cannot do']), 'comps': []}
        for name, sub in graph[lid]['comps']:
            cid = name.split()[0].lower() if lid != 'L4' else re.sub(r'[^a-z]+', '-', name.lower()).strip('-')
            lv['comps'].append({'id': cid, 'name': name, 'sub': sub})
        out.append(lv)
    notes = sec.split('**How it differs from Gemini 4-Level')[0]
    notes = notes[notes.rfind('|') + 1:]
    return out, md(notes)


def l1_details(steps) -> dict:
    out = {}
    for comp, specs in L1_SOURCES.items():
        out[comp.lower()] = {'leads': [s['n'] for s in steps if comp in s['level']],
                             'sources': [source(s) for s in specs]}
    return out


def l4_details(agent_list) -> dict:
    hooks = []
    spec = json.loads(read('l4-tools-guards/hooks/hooks.json'))
    for event, groups in spec['hooks'].items():
        for g in groups:
            for h in g['hooks']:
                script = re.search(r'hooks/([\w-]+\.py)(.*)$', h['command'])
                hooks.append({'script': script.group(1), 'arg': script.group(2).strip(), 'event': event,
                              'matcher': g.get('matcher', '(every tool)' if event in ('PreToolUse', 'PostToolUse') else '(all)'),
                              'where': 'plugin hook', 'onFailure': h.get('onFailure', '—'), 'timeout': h.get('timeout')})
    fm, _ = frontmatter_skill()
    for m in re.finditer(r'matcher: "([^"]+)"\n\s+hooks:\n\s+- type: command\n\s+command: ".*?hooks/([\w-]+\.py).*?"\n\s+timeout: (\d+)\n\s+onFailure: (\w+)', fm):
        hooks.append({'script': m.group(2), 'arg': '', 'event': 'PreToolUse', 'matcher': m.group(1),
                      'where': 'skill hook (SKILL.md frontmatter)', 'onFailure': m.group(4), 'timeout': int(m.group(3))})
    docs = {p.name: docstring(p) for p in sorted((L4 / 'hooks').glob('*.py'))}
    for h in hooks:
        h['doc'] = docs.get(h['script'], '')
    perms = json.loads(read('l4-tools-guards/permissions/permissions.json'))['permissions']
    scripts = [{'name': p.name, 'doc': docstring(p)} for p in sorted((L4 / 'scripts').glob('*.py'))]
    lib = [{'name': p.name, 'doc': docstring(p)} for p in sorted((L4 / 'lib').glob('*.py'))]
    tools = sorted({t for a in agent_list for t in a['tools']})
    arch = read(ARCH)
    return {'hooks': hooks, 'ask': perms['ask'], 'deny': perms['deny'], 'scripts': scripts, 'lib': lib,
            'tools': tools, 'g2': md(cut_bold(arch, 'actions G2 asks about', 'arch')),
            'hardGate': md(cut_bold(arch, 'G1b hard gate', 'arch'))}


def frontmatter_skill():
    m = re.match(r'---\n(.*?)\n---\n(.*)', read('SKILL.md'), re.S)
    return m.group(1), m.group(2)


def steps_and_gates(arch: str):
    sec = cut(arch, '4.3 Common steps and profiles', 'arch')
    flow = re.search(r'```text\n(.*?)```', sec, re.S).group(1).rstrip()
    rows = table(sec, 'arch 4.3')
    head = rows[0]
    steps, phase = [], None
    for row in rows[1:]:
        c = dict(zip(head, row))
        if c['phase'].strip():
            phase = re.sub(r'\*', '', c['phase']).strip()
        n = re.match(r'(\d)\.', c['Step']).group(1)
        steps.append({'n': n, 'phase': phase, 'name': inline(re.sub(r'^\d\.\s*', '', c['Step'])),
                      'level': c['Level in charge'], 'what': inline(c['What it does']),
                      'general': inline(c['General']), 'research': inline(c['Research · docs']), 'dev': inline(c['Dev']),
                      'rules': [{'title': h, 'from': rel(f), 'html': md(cut(read(f), h, rel(f)))} for f, h in STEP_RULES[n]]})
    skip = md(sec[sec.index('- **Rules for skipping'):sec.index('- **The dev profile and my-dev')])
    gsec = cut(arch, '4.4 HITL gates', 'arch')
    grows = table(gsec, 'arch 4.4')
    gates = [dict(zip(['gate', 'when', 'enforcement', 'sees', 'choices'], [inline(c) for c in r])) for r in grows[1:]]
    for g, r in zip(gates, grows[1:]):
        g['id'] = re.search(r'G1a|G1b|G2|G3|E', r[0]).group(0)
    retro = {'n': 'R', 'phase': '④ Accept', 'name': 'Retrospective', 'level': 'L1 Recorder · L2 gate-analyst · L4 scripts',
             'rules': [{'title': h, 'from': rel(f), 'html': md(cut(read(f), h, rel(f)))} for f, h in STEP_RULES['R']]}
    return flow, steps, retro, skip, gates


def profiles() -> dict:
    out = {}
    for p in PROFILES:
        f = f'l1-orchestration/profiles/{p}.md'
        text = read(f)
        title = next(t for _, d, t in outline(text.splitlines()) if d == 1)
        intro = text.split('\n## ')[0].split('\n', 1)[1]
        rules = table(cut(text, 'Rules per phase', f), f)
        used = table(cut(text, 'Agents used', f), f)
        out[p] = {'title': title, 'intro': md(intro), 'file': rel(f),
                  'rules': [[inline(a), inline(b)] for a, b in rules[1:]],
                  'agents': [[inline(c) for c in r] for r in used[1:]],
                  'used': {re.search(r'my-agent:([\w-]+)', r[0]).group(1): [inline(r[1]), inline(r[2])]
                           for r in used[1:]}}
    return out


def tree_files(arch: str) -> list:
    """(name, comment) of the task-folder entries in the 4.7 file layout."""
    block = re.search(r'```text\n(~/dev/my-plugins.*?)```', cut(arch, '4.7 File layout', 'arch'), re.S).group(1)
    lines = block.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('<task project>/docs/agent/'))
    out = []
    for line in lines[start + 1:]:
        if not line.strip():
            break
        body = re.sub(r'^[\s│├└─]+', '', line)
        names, _, comment = body.partition('#')
        for name in names.split():
            if name != '<task-id>/':
                out.append((name, comment.strip()))
    return out


def artifacts(arch: str) -> list:
    comments = dict(tree_files(arch))
    out = []
    for name, steps, writer, specs in ARTIFACTS:
        a = {'id': name, 'steps': steps, 'writer': writer, 'comment': inline(comments.get(name, '')),
             'sources': [source(s) for s in specs]}
        if name == 'main-usage.json':
            usage = {(0, 1): {'claude-opus-5-5': {k: 0 for k in ma_usage.KEYS}}}
            sample = ma_usage.to_json(['<session-id>'], usage, datetime(2026, 1, 1))
            a['sources'].append({'title': 'shape (ma_usage.to_json)', 'from': rel(L4 / 'lib' / 'ma_usage.py'),
                                 'html': md('```json\n' + json.dumps(sample, indent=1) + '\n```')})
        out.append(a)
    return out


def vocab() -> list:
    """Groups of ma_schema constants with their trailing comments, in file order."""
    path = L4 / 'lib' / 'ma_schema.py'
    src = path.read_text(encoding='utf-8')
    comments = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            comments[tok.start[0]] = (tok.start[1], tok.string.lstrip('#').strip())
    groups, cur = [], None
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)]
    for n in nodes:
        heading = max((ln for ln, (col, t) in comments.items() if col == 0 and t.startswith('---') and ln < n.lineno),
                      default=None)
        title = comments[heading][1].strip('- ').strip() if heading else 'other'
        if cur is None or cur['title'] != title:
            cur = {'title': title, 'items': []}
            groups.append(cur)
        name = next(t.id for t in n.targets if isinstance(t, ast.Name))
        value = getattr(ma_schema, name)
        if isinstance(value, re.Pattern):
            shown = value.pattern
        elif isinstance(value, dict):
            shown = ' · '.join(f'{k} {v}' for k, v in value.items())
        elif isinstance(value, tuple):
            shown = ' · '.join(map(str, value))
        else:
            shown = str(value)
        note = comments.get(n.end_lineno)
        cur['items'].append({'name': name, 'value': shown, 'note': note[1] if note and note[0] > 0 else ''})
    return groups


def principles(arch: str) -> str:
    return md(cut(arch, '4.1 Principles', 'arch'))


def build() -> str:
    arch = read(ARCH)
    sg = scope_guard()
    agent_list = agents(sg)
    flow, steps, retro, skip, gates = steps_and_gates(arch)
    lvls, level_notes = levels(arch, agent_list, steps)
    status = re.search(r'^- Status: design draft (v[\d.]+)', arch, re.M).group(1)
    manifest = json.loads(read('.claude-plugin/plugin.json'))
    data = {
        'version': manifest['version'], 'description': manifest['description'], 'design': status,
        'scopeDoc': md(ast.get_docstring(ast.parse(read('l4-tools-guards/hooks/scope-guard.py'))).split('\n\n')[0]),
        'principles': principles(arch), 'levels': lvls, 'levelNotes': level_notes,
        'delegation': md(cut_bold(arch, 'How it differs from Gemini 4-Level', 'arch')),
        'agents': agent_list, 'l1': l1_details(steps), 'l4': l4_details(agent_list),
        'flow': flow, 'steps': steps, 'retro': retro, 'skip': skip, 'gates': gates,
        'profiles': profiles(), 'artifacts': artifacts(arch), 'vocab': vocab(),
        'skillLevels': md(cut(read('SKILL.md'), 'Levels', 'SKILL.md')),
        'l1DoesNot': inline(next(r[3] for r in table(cut(read('SKILL.md'), 'Levels', 'SKILL.md'), 'SKILL.md') if r[0] == 'L1')),
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = TEMPLATE.read_text(encoding='utf-8')
    if '/*DATA*/null' not in page:
        raise SourceError(f'{TEMPLATE}: no /*DATA*/null placeholder')
    return page.replace('/*DATA*/null', payload).replace('{{VERSION}}', data['version'])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    try:
        page = build()
    except (SourceError, OSError, KeyError, StopIteration, AttributeError, ValueError) as exc:
        print(f'build-docs: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 3
    if args.check:
        current = OUT.read_text(encoding='utf-8') if OUT.exists() else ''
        if current != page:
            print(f'build-docs: {OUT.relative_to(REPO)} is out of date; run python3 tools/build-docs.py')
            return 1
        print(f'build-docs: {OUT.relative_to(REPO)} is up to date')
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding='utf-8')
    (OUT.parent / '.nojekyll').write_text('', encoding='utf-8')
    print(f'build-docs: wrote {OUT.relative_to(REPO)} ({len(page) // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

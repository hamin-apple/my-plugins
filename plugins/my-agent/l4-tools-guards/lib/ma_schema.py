"""One place for the words and shapes my-agent files share (architecture 4.7 "single source of formats").

The L4 hooks and scripts and the monitor (`monitor/monitor/`, which puts this folder on sys.path) read files with
these values; the agent definitions and L1 files write them. `test_schema` checks that each definition still
spells the words its parser looks for.
"""
import re
import shlex

# --- agents (plugin.json lists the same nine; frontmatter `level:` and the folder say the same level) ---

AGENTS = {
    'architect': 'L2', 'plan-reviewer': 'L2', 'verifier': 'L2', 'reviewer': 'L2', 'gate-analyst': 'L2',
    'explorer': 'L3', 'researcher': 'L3', 'writer': 'L3', 'coder': 'L3',
}
LEVEL_FOLDER = {'L2': 'l2-design-judge', 'L3': 'l3-workers'}
UNIT_AGENTS = ('researcher', 'writer', 'coder')           # agents that run a plan.md work unit (E: unit stops)
BEFORE_APPROVAL = ('explorer', 'architect', 'plan-reviewer')   # G1b allow list (4.4, Q6)

# --- verdicts: the first line of each judge's file and last message ---

VERIFY_PASS = 'Verdict: ALL PASS'
VERIFY_FAIL = 'Verdict: FAIL'
PLAN_READY = 'READY FOR APPROVAL'
PLAN_REVISE = 'REVISE'
PLAN_SKIPPED = 'SKIPPED'          # L1 writes `SKIPPED <reason>` when the profile skips Plan Review
REVIEW_PASS = 'BLOCKER 0'
REVIEW_PREFIX = 'BLOCKER '
WORKER_DONE = 'DONE'
WORKER_PARTIAL = 'PARTIAL'
APPLIED_AFTER_REVIEW = 'Applied after review'    # review.md section L1 adds after a fix that skips re-Verify


def verify_failed(first_line) -> bool:
    return isinstance(first_line, str) and first_line.startswith(VERIFY_FAIL)


def plan_review_skipped(first_line) -> bool:
    return isinstance(first_line, str) and (first_line == PLAN_SKIPPED or first_line.startswith(PLAN_SKIPPED + ' '))


# --- run-log kinds written by the L4 hooks ---

GUARD = 'guard'                                        # run-log kind of a guard deny (scope-guard, plan-approved-check)
GUARD_FIELDS = ('hook', 'agent', 'id', 'tool', 'decision', 'why', 'cwd')   # guard: field order; why = the reason as printed, cwd = the hook input's cwd (older lines end at why)

# --- status values ---

INTAKE_STATUS = ('active', 'done', 'aborted')          # intake.md `Status:` (first word)
UNIT_STATUS = ('pending', 'running', 'done', 'stale')  # plan.md work unit `Status:`
UNIT_FINISHED = ('done', 'stale')                      # every unit ends in one of these (check-run)
END = END_OK, END_PARTIAL, END_ERROR = ('ok', 'partial', 'error')   # stop: end=
INTERRUPTED = (END_PARTIAL, END_ERROR)                 # an end that counts as a worker stop (E)
GATES = ('G1a', 'G1b', 'G2', 'G3', 'E')
POPUP_TAGS = GATES + ('Q',)                            # Q: an L1 popup that is not a gate
PEOPLE_POPUPS = ('G1a', 'G1b', 'G3', 'E', 'Q')         # L1 popups (G2 is Claude Code's permission window)

# --- models ---

FAMILY = re.compile(r'(opus|sonnet|haiku|fable)')


def family(model):
    """`claude-sonnet-5-5` / `sonnet` / `opus[1m]` → the family, or None."""
    m = FAMILY.search(model or '')
    return m.group(1) if m else None


# --- run-log lines (4.7.2): `<YYYY-MM-DD HH:MM:SS> <kind>: <key=value ...>` ---

LINE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([a-z][a-z0-9-]*):(?:\s+(.*))?$')
DELEGATE_STATES = ('on', 'off')   # `delegate: state=` (delegated approval); the last such line is the current state
ANSWERED_BY_L1 = 'L1'             # `answer: ... by=L1` is an answer L1 gave under delegated approval
PLAN_EDIT_GATE = 'G1b'            # `fix: ... before=G1b` is an L1 edit of plan.md before plan approval
STAMPED = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ')   # looks like a record, readable or not


def split_line(text: str):
    """(stamp, kind, fields) of a run-log line, or None (headings, old-style or broken lines)."""
    m = LINE_RE.match(text.strip())
    if not m:
        return None
    try:
        tokens = shlex.split(m.group(3) or '')
    except ValueError:
        return None
    fields = {}
    for tok in tokens:
        key, sep, value = tok.partition('=')
        if sep:
            fields[key] = value
    return m.group(1), m.group(2), fields


def unreadable_lines(text: str) -> list:
    """1-based numbers of lines that start like a record but do not parse."""
    return [i for i, line in enumerate(text.splitlines(), 1)
            if STAMPED.match(line.strip()) and split_line(line) is None]


# --- Markdown sections: a line-start `## <name>`, optionally followed by ` (<note>)` ---

def heading_name(line: str):
    """`## Completion criteria (general)` → `Completion criteria`; None for a line that is not a `## ` heading."""
    if not line.startswith('## '):
        return None
    return line[3:].strip().split(' (')[0]


def section_lines(text: str, *names):
    """Lines under the first `## <name>` heading up to the next `## ` heading, or None when there is none."""
    out, inside = None, False
    for line in (text or '').splitlines():
        name = heading_name(line)
        if name is not None:
            if inside:
                break
            inside = name in names
            if inside:
                out = []
            continue
        if inside:
            out.append(line)
    return out


def section(text: str, *names) -> str:
    """Body of the first `## <name>` section, or ''."""
    lines = section_lines(text, *names)
    return '\n'.join(lines) if lines is not None else ''


def has_section(text: str, name: str) -> bool:
    return section_lines(text, name) is not None


# --- plan.md markers and work units ---

APPROVED = re.compile(r'Approved\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})')   # under ## Approval, L1 only
PROTOTYPE = re.compile(r'(?m)^\s*(?:-\s*)?Prototype:\s*requested\s*$')  # under ## Prototype, L1 only
UNIT_HEAD = re.compile(r'^###\s+(u\d+)\b\s*(.*)$')                     # `### u1 <name>` under ## Work units
UNIT_STATUS_LINE = re.compile(r'^\s*(?:-\s*)?Status:\s*([a-z]+)')
UNIT_MARK = re.compile(r'(?m)^Work unit:\s*(u\d+)\b')                   # first prompt line L1 gives a unit's worker
MOCKUP_KIND = re.compile(r'^Kind:\s*(.*)$')                            # first line of ## Mock-up
DELIVERED_COMMIT = 'commit:'                                           # `Delivered: commit:<sha>` / deliver path=


def approved_at(text: str):
    """`YYYY-MM-DD HH:MM` of the Approved line under ## Approval, or None."""
    m = APPROVED.search(section(text, 'Approval'))
    return m.group(1) if m else None


def prototype_requested_text(text: str) -> bool:
    return bool(PROTOTYPE.search(section(text, 'Prototype')))


def units(text: str) -> list:
    """[(id, name, status)] of the `### u<n>` work units under ## Work units; status None when missing."""
    out = []
    for line in section_lines(text, 'Work units') or []:
        head = UNIT_HEAD.match(line)
        if head:
            out.append([head.group(1), head.group(2).strip(), None])
            continue
        st = UNIT_STATUS_LINE.match(line)
        if st and out and out[-1][2] is None:
            out[-1][2] = st.group(1)
    return [tuple(u) for u in out]


def unit_of_prompt(prompt):
    """`u1` from a `Work unit: u1 …` line in a worker's prompt, or None."""
    m = UNIT_MARK.search(prompt or '')
    return m.group(1) if m else None


# --- report parsers (monitor Report tab; each returns None or [] for a missing or empty text) ---

CRITERION_LINE = re.compile(r'^\s*(\d+)\.\s+(.*\S)\s*$')
CHECK_TAG = re.compile(r'\s*\[check:\s*([^\]]*?)\s*\]\s*$')
VERIFY_ROW = re.compile(r'^\s*-\s*(\d+)\.\s+([A-Z]+)\b\s*(.*)$')
RUN_LINE = re.compile(r'(?m)^Run:\s*(\d+)\s*$')
REVIEW_BLOCKERS = re.compile(r'^BLOCKER\s+(\d+)\b')
SEVERITIES = ('BLOCKER', 'SHOULD-FIX', 'NITPICK')
FINDING_LINE = re.compile(r'^-\s*(BLOCKER|SHOULD-FIX|NITPICK)\s+(\S+)\s*(.*)$')
FINDING_MARK = re.compile(r'\s*\((new|carried)\)\s*$')
IMPROVEMENT_LINE = re.compile(r'^-\s*\[(L\d),\s*([a-z]+)\]\s*(.*\S)\s*$')
SUMMARY_ITEM = re.compile(r'^\s*\d+\.\s+(.*\S)\s*$')
UNIT_KEY = re.compile(r'^(?:-\s*)?([A-Z][A-Za-z ]*?):\s*(.*)$')
PATH_TOKEN = re.compile(r'[\w./\-]+\.\w+(?::\d+)?')
LINE_SUFFIX = re.compile(r':\d+$')


def criteria(text: str) -> list:
    """[(n, text without the `[check: …]` tag, tag or None)] from `## Completion criteria` (scope.md, or plan.md for the general profile)."""
    rows = []
    for line in section_lines(text, 'Completion criteria') or []:
        m = CRITERION_LINE.match(line)
        if m:
            rows.append([int(m.group(1)), m.group(2)])
        elif rows and line.strip() and line[:1].isspace():
            rows[-1][1] += ' ' + line.strip()
    out = []
    for n, body in rows:
        tag = CHECK_TAG.search(body)
        out.append((n, CHECK_TAG.sub('', body) if tag else body, tag.group(1) if tag else None))
    return out


def purpose(text: str):
    """The paragraph under `## Purpose and users` (scope.md) or `## Scope summary` (plan.md), or None."""
    joined = ' '.join(l.strip() for l in section_lines(text, 'Purpose and users', 'Scope summary') or [] if l.strip())
    return joined or None


def verify_rows(text: str) -> list:
    """[(n, verdict, evidence)] of the `- <n>. PASS|FAIL <evidence>` rows before the first `## ` heading of verify.md."""
    out = []
    for line in (text or '').splitlines():
        if heading_name(line) is not None:
            break
        m = VERIFY_ROW.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3).strip()))
    return out


def run_number(text: str):
    """The `Run: <n>` of a verify.md or plan-review.md, or None."""
    m = RUN_LINE.search(text or '')
    return int(m.group(1)) if m else None


def review_blockers(text: str):
    """The n of the `BLOCKER n` first line of review.md, or None."""
    for line in (text or '').splitlines():
        if line.strip():
            m = REVIEW_BLOCKERS.match(line.strip())
            return int(m.group(1)) if m else None
    return None


def review_findings(text: str) -> list:
    """[(severity, where, text, mark)] of the `## Findings` bullets of review.md; mark is `new`, `carried` or None."""
    out = []
    for line in section_lines(text, 'Findings') or []:
        m = FINDING_LINE.match(line.strip())
        if m:
            body = m.group(3).strip()
            mark = FINDING_MARK.search(body)
            out.append((m.group(1), m.group(2), FINDING_MARK.sub('', body) if mark else body, mark.group(1) if mark else None))
    return out


def review_applied(text: str) -> list:
    """The bullet lines (without the dash) under `## Applied after review` in review.md."""
    return [l.strip()[1:].strip() for l in section_lines(text, APPLIED_AFTER_REVIEW) or [] if l.strip().startswith('-')]


def finding_applied(where: str, applied_lines) -> bool:
    """A finding is applied when an `Applied after review` line names its `<file>:<line>` or its file path
    (a path in the line may be cut at the front)."""
    file = LINE_SUFFIX.sub('', where)
    for line in applied_lines:
        for tok in PATH_TOKEN.findall(line):
            if tok == where or where.endswith('/' + tok):
                return True
            if not LINE_SUFFIX.search(tok) and (file == tok or file.endswith('/' + tok)):
                return True
    return False


def plan_review(text: str):
    """{verdict, run, blockers, should_fix, nitpicks} of a plan-review.md, or None when the text is empty."""
    lines = [l for l in (text or '').splitlines() if l.strip()]
    if not lines:
        return None
    counts = {s: 0 for s in SEVERITIES}
    for line in section_lines(text, 'Findings') or []:
        m = FINDING_LINE.match(line.strip())
        if m:
            counts[m.group(1)] += 1
    return {'verdict': lines[0].strip(), 'run': run_number(text), 'blockers': counts['BLOCKER'],
            'should_fix': counts['SHOULD-FIX'], 'nitpicks': counts['NITPICK']}


def gate_report_summary(text: str) -> list:
    """The numbered items under `## Summary` of gate-report.md."""
    return [m.group(1) for m in map(SUMMARY_ITEM.match, section_lines(text, 'Summary') or []) if m]


def gate_report_improvements(text: str) -> list:
    """[(level, strength, text)] of the `- [L1, weak] …` bullets under `## Suggested improvements`."""
    lines = (l.strip() for l in section_lines(text, 'Suggested improvements') or [])
    return [m.groups() for m in map(IMPROVEMENT_LINE.match, lines) if m]


def criterion_numbers(line: str) -> list:
    """Criterion numbers of a plan unit's `Completion criteria:` value: the integers outside parentheses, sorted, once each."""
    out, depth = [], 0
    for ch in line or '':
        depth = depth + 1 if ch == '(' else max(0, depth - 1) if ch == ')' else depth
        out.append(' ' if depth or ch in '()' else ch)
    return sorted({int(n) for n in re.findall(r'(?<![\w.])\d+(?![\w.])', ''.join(out))})


def unit_details(text: str) -> list:
    """[{id, name, status, group, files, criteria}] of the `### u<n>` units under ## Work units
    (files: the backticked paths of `Files to change:`, on its line or in its nested bullets)."""
    units, in_files = [], False
    for line in section_lines(text, 'Work units') or []:
        head = UNIT_HEAD.match(line)
        if head:
            units.append({'id': head.group(1), 'name': head.group(2).strip(), 'status': None, 'group': None,
                          'files': [], 'criteria': []})
            in_files = False
            continue
        if not units:
            continue
        unit = units[-1]
        key = None if line[:1].isspace() else UNIT_KEY.match(line)
        if key:
            name, value = key.groups()
            in_files = name == 'Files to change'
            if name == 'Status' and unit['status'] is None and value.split():
                unit['status'] = value.split()[0]
            elif name == 'Parallel group':
                unit['group'] = value.strip() or None
            elif name == 'Completion criteria':
                unit['criteria'] = criterion_numbers(value)
            elif in_files:
                unit['files'] += re.findall(r'`([^`]+)`', value)
        elif in_files and re.match(r'\s+-\s', line):
            m = re.search(r'`([^`]+)`', line)
            if m:
                unit['files'].append(m.group(1))
    return units

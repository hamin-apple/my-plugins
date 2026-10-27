"""One place for the words and shapes my-agent files share (architecture 4.7 "형식의 단일 소스").

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
PLAN_SKIPPED = 'SKIPPED'          # L1 writes `SKIPPED <이유>` when the profile skips Plan Review
REVIEW_PASS = 'BLOCKER 0'
REVIEW_PREFIX = 'BLOCKER '
WORKER_DONE = 'DONE'
WORKER_PARTIAL = 'PARTIAL'
APPLIED_AFTER_REVIEW = 'Applied after review'    # review.md section L1 adds after a fix that skips re-Verify


def verify_failed(first_line) -> bool:
    return isinstance(first_line, str) and first_line.startswith(VERIFY_FAIL)


def plan_review_skipped(first_line) -> bool:
    return isinstance(first_line, str) and (first_line == PLAN_SKIPPED or first_line.startswith(PLAN_SKIPPED + ' '))


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
    """`## 완료 기준 (일반)` → `완료 기준`; None for a line that is not a `## ` heading."""
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
UNIT_HEAD = re.compile(r'^###\s+(u\d+)\b\s*(.*)$')                     # `### u1 <이름>` under ## 작업 단위
UNIT_STATUS_LINE = re.compile(r'^\s*(?:-\s*)?Status:\s*([a-z]+)')
UNIT_MARK = re.compile(r'(?m)^작업 단위:\s*(u\d+)\b')                  # first prompt line L1 gives a unit's worker
MOCKUP_KIND = re.compile(r'^Kind:\s*(.*)$')                            # first line of ## Mock-up
DELIVERED_COMMIT = 'commit:'                                           # `Delivered: commit:<sha>` / deliver path=


def approved_at(text: str):
    """`YYYY-MM-DD HH:MM` of the Approved line under ## Approval, or None."""
    m = APPROVED.search(section(text, 'Approval'))
    return m.group(1) if m else None


def prototype_requested_text(text: str) -> bool:
    return bool(PROTOTYPE.search(section(text, 'Prototype')))


def units(text: str) -> list:
    """[(id, name, status)] of the `### u<n>` work units under ## 작업 단위; status None when missing."""
    out = []
    for line in section_lines(text, '작업 단위') or []:
        head = UNIT_HEAD.match(line)
        if head:
            out.append([head.group(1), head.group(2).strip(), None])
            continue
        st = UNIT_STATUS_LINE.match(line)
        if st and out and out[-1][2] is None:
            out[-1][2] = st.group(1)
    return [tuple(u) for u in out]


def unit_of_prompt(prompt):
    """`u1` from a `작업 단위: u1 …` line in a worker's prompt, or None."""
    m = UNIT_MARK.search(prompt or '')
    return m.group(1) if m else None

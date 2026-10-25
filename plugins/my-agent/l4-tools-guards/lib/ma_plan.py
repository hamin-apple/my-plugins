"""Read the markers L1 writes into plan.md (architecture 4.4 G1b): the `Approved` line under `## Approval` and
the `Prototype: requested` line."""
import re
from pathlib import Path

APPROVED = re.compile(r'Approved\s+\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
PROTOTYPE = re.compile(r'(?m)^\s*(?:-\s*)?Prototype:\s*requested\s*$')


def read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def section(text: str, heading: str) -> str:
    """Body of `## <heading>` up to the next `## `, or ''."""
    m = re.search(rf'(?m)^## {re.escape(heading)}\s*$', text)
    if not m:
        return ''
    rest = text[m.end():]
    nxt = re.search(r'(?m)^## ', rest)
    return rest[:nxt.start()] if nxt else rest


def approved_text(text: str) -> bool:
    return bool(APPROVED.search(section(text, 'Approval')))


def prototype_text(text: str) -> bool:
    return bool(PROTOTYPE.search(text))


def approved(plan_md: Path) -> bool:
    return approved_text(read(plan_md))


def prototype_requested(plan_md: Path) -> bool:
    return prototype_text(read(plan_md))

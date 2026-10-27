"""Read the markers L1 writes into plan.md (architecture 4.4 G1b): the `Approved` line under `## Approval` and
the `Prototype: requested` line under `## Prototype`; and the `### u<n>` work units (4.8.2). Shapes: ma_schema."""
from pathlib import Path

import ma_schema


def read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def section(text: str, heading: str) -> str:
    """Body of `## <heading>` up to the next `## `, or ''."""
    return ma_schema.section(text, heading)


def approved_text(text: str) -> bool:
    return ma_schema.approved_at(text) is not None


def prototype_text(text: str) -> bool:
    return ma_schema.prototype_requested_text(text)


def approved(plan_md: Path) -> bool:
    return approved_text(read(plan_md))


def prototype_requested(plan_md: Path) -> bool:
    return prototype_text(read(plan_md))


def units(plan_md: Path) -> list:
    return ma_schema.units(read(plan_md))

"""Path comparison for the hooks. macOS volumes are case-insensitive by default, so `Docs/agent` is `docs/agent`:
every containment and equality check folds case (on a case-sensitive volume this only treats two spellings as one)."""
from pathlib import Path


def _fold(p) -> str:
    return str(p).casefold().rstrip('/') or '/'


def same(p: Path, q: Path) -> bool:
    return _fold(p) == _fold(q)


def under(p: Path, root: Path) -> bool:
    """`p` is `root` or inside it."""
    a, b = _fold(p), _fold(root)
    return a == b or a.startswith(b if b.endswith('/') else b + '/')

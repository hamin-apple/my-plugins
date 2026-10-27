"""Monitor data readers. File shapes (run-log lines, sections, verdict words) come from the plugin's L4
`ma_schema`, so the monitor reads what the hooks and scripts read (architecture 4.7, C1)."""
import sys
from pathlib import Path

_LIB = str(Path(__file__).resolve().parents[2] / 'l4-tools-guards' / 'lib')
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

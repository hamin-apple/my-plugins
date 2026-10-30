"""List prices (USD per 1M tokens, keyed by model-ID prefix; monitor design 5.4) shared by the monitor and
`usage-snapshot.py`, so both show the same cost.

The bundled table is the plugin's `monitor/prices.json`; `<data folder>/prices.json` overrides it when that file exists.
"""
import json
from pathlib import Path

import ma_data

RATES = (('input_tokens', 'input'), ('output_tokens', 'output'),
         ('cache_creation_input_tokens', 'cache_write'), ('cache_read_input_tokens', 'cache_read'))
BUNDLED = Path(__file__).resolve().parents[2] / 'monitor' / 'prices.json'


def prices_file(arg=None) -> Path:
    """`prices.json` in the data folder when it exists, else the bundled one (monitor design 6.1)."""
    override = ma_data.data_dir(arg) / 'prices.json'
    return override if override.is_file() else BUNDLED


def load_prices(path: Path) -> dict:
    """The `models` table; {} if the file is missing or broken."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8')).get('models', {})
    except (OSError, ValueError, AttributeError):
        return {}


def cost(prices: dict, model_id, usage: dict):
    """USD for one usage dict, by the longest matching prefix; None if no row matches."""
    if not model_id:
        return None
    keys = [k for k in prices if model_id.startswith(k)]
    if not keys:
        return None
    row = prices[max(keys, key=len)]
    return sum(usage.get(u, 0) * row.get(r, 0) for u, r in RATES) / 1_000_000

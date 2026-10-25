"""prices.json (USD per 1M tokens, keyed by model-ID prefix) → cost (spec 5.4)."""
import json
from pathlib import Path

RATES = (('input_tokens', 'input'), ('output_tokens', 'output'),
         ('cache_creation_input_tokens', 'cache_write'), ('cache_read_input_tokens', 'cache_read'))


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

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import monitor  # puts l4-tools-guards/lib on sys.path
import ma_prices
from ma_prices import cost, load_prices

ROOT = Path(__file__).resolve().parent.parent
P = {'claude-sonnet-5': {'input': 3, 'output': 15, 'cache_write': 3.75, 'cache_read': 0.3},
     'claude-opus-5': {'input': 5, 'output': 25, 'cache_write': 6.25, 'cache_read': 0.5},
     'claude-opus-5-5': {'input': 4, 'output': 20, 'cache_write': 5, 'cache_read': 0.2}}
U = {'input_tokens': 1_000_000, 'output_tokens': 1_000_000, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}


class PricesTest(unittest.TestCase):
    def test_prefix_match(self):
        self.assertEqual(cost(P, 'claude-sonnet-5-5-20260101', U), 18.0)

    def test_longest_prefix_wins(self):
        self.assertEqual(cost(P, 'claude-opus-5-5', U), 24.0)

    def test_unknown_model_none(self):
        self.assertIsNone(cost(P, 'gpt-5', U))
        self.assertIsNone(cost(P, None, U))

    def test_cost_formula(self):
        u = dict(U, cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000)
        self.assertAlmostEqual(cost(P, 'claude-sonnet-5', u), 18.0 + 3.75 + 0.3)

    def test_shipped_table_loads(self):
        p = load_prices(ma_prices.BUNDLED)
        for m in ['claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']:
            self.assertIsNotNone(cost(p, m, U), m)

    def test_missing_table_is_empty(self):
        self.assertEqual(load_prices(Path('/nonexistent/prices.json')), {})

    def test_monitor_uses_the_lib_module(self):
        from monitor import registry, taskview
        import ma_prices
        self.assertIs(taskview.cost, ma_prices.cost)
        self.assertIs(registry.load_prices, ma_prices.load_prices)
        self.assertFalse((ROOT / 'monitor' / 'prices.py').exists())
        self.assertEqual(ma_prices.BUNDLED, (ROOT.parent / 'l4-tools-guards' / 'lib' / 'prices.json').resolve())

    def test_bundled_table_lives_in_the_lib_folder(self):
        self.assertTrue(ma_prices.BUNDLED.is_file())
        self.assertEqual(ma_prices.BUNDLED, (ROOT.parent / 'l4-tools-guards' / 'lib' / 'prices.json').resolve())
        self.assertNotIn('monitor', ma_prices.BUNDLED.parts)
        self.assertFalse(ROOT.joinpath('prices.json').exists())

    def test_snapshot_uses_the_lib_module(self):
        import ma_prices
        import ma_usage
        self.assertIs(ma_usage.ma_prices, ma_prices)

    def test_prices_file_override(self):
        import ma_prices
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'MA_TASKS_DIR': d}):
            self.assertEqual(ma_prices.prices_file(), ma_prices.BUNDLED)
            Path(d, 'prices.json').write_text('{"models": {}}')
            self.assertEqual(ma_prices.prices_file(), Path(d, 'prices.json'))
        keep = {k: v for k, v in os.environ.items() if not k.startswith('MA_') and k != 'CLAUDE_PLUGIN_OPTION_DATA_DIR'}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, keep, clear=True):
            Path(d, 'prices.json').write_text('{"models": {}}')
            self.assertEqual(ma_prices.prices_file(d), Path(d, 'prices.json'))


if __name__ == '__main__':
    unittest.main()

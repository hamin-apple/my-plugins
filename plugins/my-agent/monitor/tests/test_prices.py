import unittest
from pathlib import Path

from monitor.prices import cost, load_prices

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
        p = load_prices(ROOT / 'prices.json')
        for m in ['claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']:
            self.assertIsNotNone(cost(p, m, U), m)

    def test_missing_table_is_empty(self):
        self.assertEqual(load_prices(Path('/nonexistent/prices.json')), {})


if __name__ == '__main__':
    unittest.main()

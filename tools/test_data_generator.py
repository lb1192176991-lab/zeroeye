import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_generator import DataGenerator


class DataGeneratorDeterminismTest(unittest.TestCase):
    def snapshot(self, seed: int):
        generator = DataGenerator(seed)
        users = generator.generate_users(8)
        orders = generator.generate_orders(12)
        trades = generator.generate_trades(12)
        ticks = generator.generate_ticks("BTC/USD", 12)
        candles = generator.generate_candles("BTC/USD", count=12)
        return users, orders, trades, ticks, candles

    def test_same_seed_generates_same_data(self):
        self.assertEqual(self.snapshot(1234), self.snapshot(1234))

    def test_different_seed_generates_different_data(self):
        self.assertNotEqual(self.snapshot(1234), self.snapshot(5678))


if __name__ == "__main__":
    unittest.main()

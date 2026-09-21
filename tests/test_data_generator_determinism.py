import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.data_generator import (
    BASE_TIMESTAMP_MS,
    DataGenerator,
    random_datetime,
    random_email,
    random_phone,
)

ROOT = Path(__file__).resolve().parents[1]


def generate_dataset(seed):
    generator = DataGenerator(seed)
    return {
        "users": generator.generate_users(5),
        "orders": generator.generate_orders(7),
        "trades": generator.generate_trades(9),
        "ticks": generator.generate_ticks("BTC/USD", 4),
        "candles": generator.generate_candles("BTC/USD", 15, 4),
    }


class DataGeneratorDeterminismTests(unittest.TestCase):
    def test_same_seed_produces_same_dataset(self):
        self.assertEqual(generate_dataset(42), generate_dataset(42))

    def test_different_seeds_produce_different_datasets(self):
        self.assertNotEqual(generate_dataset(42), generate_dataset(43))

    def test_seed_zero_is_deterministic(self):
        self.assertEqual(generate_dataset(0), generate_dataset(0))

    def test_global_random_state_does_not_change_generator_output(self):
        random.seed(1)
        first = generate_dataset(42)
        random.seed(999)
        second = generate_dataset(42)
        self.assertEqual(first, second)

    def test_market_timestamps_do_not_use_wall_clock(self):
        with patch("time.time", return_value=1):
            first = generate_dataset(42)
        with patch("time.time", return_value=2):
            second = generate_dataset(42)
        self.assertEqual(first["ticks"], second["ticks"])
        self.assertEqual(first["candles"], second["candles"])

    def test_market_timestamps_keep_their_intervals(self):
        generator = DataGenerator(42)
        ticks = generator.generate_ticks("BTC/USD", 4)
        candles = generator.generate_candles("BTC/USD", 15, 4)
        self.assertEqual([tick["timestamp"] for tick in ticks], [
            BASE_TIMESTAMP_MS - 4000,
            BASE_TIMESTAMP_MS - 3000,
            BASE_TIMESTAMP_MS - 2000,
            BASE_TIMESTAMP_MS - 1000,
        ])
        self.assertEqual([candle["time"] for candle in candles], [
            BASE_TIMESTAMP_MS - 4 * 15 * 60 * 1000,
            BASE_TIMESTAMP_MS - 3 * 15 * 60 * 1000,
            BASE_TIMESTAMP_MS - 2 * 15 * 60 * 1000,
            BASE_TIMESTAMP_MS - 15 * 60 * 1000,
        ])

    def test_helpers_remain_compatible_and_accept_seeded_rng(self):
        first = random.Random(42)
        second = random.Random(42)
        self.assertEqual(random_phone(first), random_phone(second))
        self.assertEqual(random_email("Alice", "Smith", first),
                         random_email("Alice", "Smith", second))
        self.assertEqual(random_datetime(rng=first), random_datetime(rng=second))
        self.assertIsInstance(random_phone(), str)

    def test_cli_json_is_identical_across_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            for output in (first, second):
                subprocess.run([
                    sys.executable,
                    str(ROOT / "tools" / "data_generator.py"),
                    "--seed", "42",
                    "--users", "3",
                    "--orders", "4",
                    "--trades", "5",
                    "--ticks", "2",
                    "--candles", "2",
                    "--format", "json",
                    "--output-dir", str(output),
                ], check=True, capture_output=True, text=True)
            first_files = {p.name: json.loads(p.read_text()) for p in first.iterdir()}
            second_files = {p.name: json.loads(p.read_text()) for p in second.iterdir()}
            self.assertEqual(first_files, second_files)


if __name__ == "__main__":
    unittest.main()

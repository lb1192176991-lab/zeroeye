#!/usr/bin/env python3
"""Regression tests for deterministic test data generation."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from data_generator import DEFAULT_SEED, DataGenerator  # noqa: E402


def generated_snapshot(seed: int):
    generator = DataGenerator(seed=seed)
    users = generator.generate_users(5)
    orders = generator.generate_orders(8)
    trades = generator.generate_trades(8)
    ticks = generator.generate_ticks("BTC/USD", 5)
    candles = generator.generate_candles("BTC/USD", 60, 5)
    return {
        "users": users,
        "orders": orders,
        "trades": trades,
        "ticks": ticks,
        "candles": candles,
    }


class DataGeneratorDeterminismTests(unittest.TestCase):
    def test_same_seed_produces_identical_data(self):
        self.assertEqual(generated_snapshot(123), generated_snapshot(123))

    def test_different_seed_changes_data(self):
        self.assertNotEqual(generated_snapshot(123)["users"], generated_snapshot(456)["users"])

    def test_default_seed_matches_explicit_42(self):
        self.assertEqual(DEFAULT_SEED, 42)
        self.assertEqual(generated_snapshot(DEFAULT_SEED), generated_snapshot(42))
        self.assertEqual(DataGenerator().seed, DEFAULT_SEED)

    def test_seed_zero_is_deterministic(self):
        self.assertEqual(generated_snapshot(0), generated_snapshot(0))
        self.assertNotEqual(generated_snapshot(0)["orders"], generated_snapshot(1)["orders"])

    def test_trades_snapshot_stable_for_fixed_seed(self):
        gen = DataGenerator(seed=99)
        first = gen.generate_trades(10)
        second = DataGenerator(seed=99).generate_trades(10)
        self.assertEqual(first, second)

    def test_cli_same_seed_writes_identical_json_files(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            command = [
                sys.executable,
                str(ROOT / "tools" / "data_generator.py"),
                "--seed",
                "777",
                "--users",
                "3",
                "--orders",
                "4",
                "--trades",
                "4",
                "--ticks",
                "3",
                "--candles",
                "3",
                "--format",
                "json",
            ]

            subprocess.run([*command, "--output-dir", first_dir], check=True, cwd=ROOT)
            subprocess.run([*command, "--output-dir", second_dir], check=True, cwd=ROOT)

            for name in [
                "users.json",
                "orders.json",
                "trades.json",
                "ticks.json",
                "candles.json",
                "instruments.json",
            ]:
                first = Path(first_dir, name).read_text()
                second = Path(second_dir, name).read_text()
                self.assertEqual(first, second, name)

            users = json.loads(Path(first_dir, "users.json").read_text())
            self.assertEqual(len(users), 3)


if __name__ == "__main__":
    unittest.main()

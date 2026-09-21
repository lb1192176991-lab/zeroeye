"""Regression tests for the standalone, standard-library data generator."""

import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.data_generator import (
    DataGenerator, gaussian_random, random_datetime, random_email, random_phone,
)


ROOT = Path(__file__).resolve().parents[1]
BASE_TIME_MS = 1704067200000  # 2024-01-01T00:00:00Z


def generate_dataset(generator):
    return {
        "users": generator.generate_users(5),
        "orders": generator.generate_orders(7),
        "trades": generator.generate_trades(9),
        "ticks": {
            instrument["symbol"]: generator.generate_ticks(instrument["symbol"], 4)
            for instrument in generator.instruments
        },
        "candles": {
            f"{instrument['symbol']}_{interval}": generator.generate_candles(
                instrument["symbol"], interval, 3
            )
            for instrument in generator.instruments
            for interval in (1, 5, 15, 60, 240, 1440)
        },
    }


class DataGeneratorDeterminismTests(unittest.TestCase):
    def test_helpers_accept_seeded_rng_and_preserve_legacy_calls(self):
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        helpers = (
            (random_phone, ()),
            (random_email, ("Alice", "Smith")),
            (random_datetime, ()),
            (random_datetime, (2024, 2024)),
            (gaussian_random, (0.0, 1.0)),
        )
        for helper, args in helpers:
            with self.subTest(helper=helper.__name__, args=args):
                self.assertEqual(
                    helper(*args, rng=random.Random(42)),
                    helper(*args, rng=random.Random(42)),
                )
                random.seed(42)
                legacy = helper(*args)
                self.assertEqual(legacy, helper(*args, rng=random.Random(42)))

    def test_same_seed_reproduces_every_dataset(self):
        for seed in (0, 42, -7):
            with self.subTest(seed=seed):
                first = generate_dataset(DataGenerator(seed))
                second = generate_dataset(DataGenerator(seed))
                self.assertEqual(first, second)

    def test_different_seeds_change_every_dataset(self):
        first = generate_dataset(DataGenerator(42))
        second = generate_dataset(DataGenerator(43))
        for name in first:
            with self.subTest(dataset=name):
                self.assertNotEqual(first[name], second[name])

    def test_generation_does_not_consume_global_random_state(self):
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        generate_dataset(DataGenerator(42))
        self.assertEqual(state, random.getstate())

    def test_other_generators_and_global_random_do_not_change_output(self):
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        first, second = DataGenerator(42), DataGenerator(42)
        self.assertEqual(first.generate_users(5), second.generate_users(5))
        generate_dataset(DataGenerator(99))
        random.seed(12345)
        for _ in range(100):
            random.random()
        self.assertEqual(generate_dataset(first), generate_dataset(second))

    def test_implicit_user_generation_is_deterministic(self):
        for method in ("generate_orders", "generate_trades"):
            with self.subTest(method=method):
                first, second = DataGenerator(42), DataGenerator(42)
                self.assertEqual(getattr(first, method)(5), getattr(second, method)(5))
                self.assertEqual(first.users, second.users)

    def test_market_timestamps_do_not_depend_on_wall_clock(self):
        for now in (1_700_000_000, 1_900_000_000):
            with self.subTest(now=now), patch("time.time", return_value=now):
                generator = DataGenerator(42)
                ticks = generator.generate_ticks("BTC/USD", 4)
                self.assertEqual(
                    [tick["timestamp"] for tick in ticks],
                    [BASE_TIME_MS - offset * 1000 for offset in (4, 3, 2, 1)],
                )
                for interval in (1, 5, 15, 60, 240, 1440):
                    candles = generator.generate_candles("BTC/USD", interval, 3)
                    self.assertEqual(
                        [candle["time"] for candle in candles],
                        [BASE_TIME_MS - offset * interval * 60_000 for offset in (3, 2, 1)],
                    )

    def test_cli_outputs_are_byte_identical_across_processes(self):
        for output_format in ("json", "csv"):
            with self.subTest(format=output_format), tempfile.TemporaryDirectory() as temp:
                snapshots = []
                for index, (hash_seed, zone) in enumerate(
                    (("1", "UTC"), ("987", "America/Los_Angeles"))
                ):
                    output_dir = Path(temp) / str(index)
                    subprocess.run(
                        [
                            sys.executable, str(ROOT / "tools" / "data_generator.py"),
                            "--seed", "42", "--users", "5", "--orders", "7",
                            "--trades", "9", "--ticks", "4", "--candles", "3",
                            "--format", output_format, "--output-dir", str(output_dir),
                        ],
                        cwd=ROOT,
                        env={**os.environ, "PYTHONHASHSEED": hash_seed, "TZ": zone},
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    )
                    snapshots.append({path.name: path.read_bytes() for path in output_dir.iterdir()})
                names = {"users", "orders", "trades"}
                if output_format == "json":
                    names |= {"ticks", "candles", "instruments"}
                self.assertEqual(set(snapshots[0]), {f"{name}.{output_format}" for name in names})
                self.assertEqual(snapshots[0], snapshots[1])
                if output_format == "json":
                    self.assertEqual(len(json.loads(snapshots[0]["users.json"])), 5)
                    self.assertEqual(len(json.loads(snapshots[0]["candles.json"])), 60)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.data_generator import DataGenerator  # noqa: E402


def generated_dataset(seed: int) -> dict:
    generator = DataGenerator(seed)
    return {
        "users": generator.generate_users(5),
        "orders": generator.generate_orders(8),
        "trades": generator.generate_trades(8),
        "ticks": generator.generate_ticks("BTC/USD", 8),
        "candles": generator.generate_candles("BTC/USD", 5, 8),
    }


class DataGeneratorDeterminismTests(unittest.TestCase):
    def test_same_seed_is_independent_of_global_random_state(self) -> None:
        random.seed(1)
        first = generated_dataset(42)
        random.seed(999_999)
        second = generated_dataset(42)

        self.assertEqual(first, second)

    def test_different_seed_changes_generated_data(self) -> None:
        self.assertNotEqual(generated_dataset(41), generated_dataset(42))

    def test_cli_json_output_is_byte_identical_for_same_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = root / "first"
            second_dir = root / "second"
            common_args = [
                sys.executable,
                str(REPO_ROOT / "tools" / "data_generator.py"),
                "--seed",
                "42",
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
            subprocess.run(
                [*common_args, "--output-dir", str(first_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [*common_args, "--output-dir", str(second_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            first_files = sorted(path.name for path in first_dir.glob("*.json"))
            second_files = sorted(path.name for path in second_dir.glob("*.json"))
            self.assertEqual(first_files, second_files)
            for name in first_files:
                self.assertEqual(
                    (first_dir / name).read_bytes(),
                    (second_dir / name).read_bytes(),
                    name,
                )

            json.loads((first_dir / "ticks.json").read_text(encoding="utf-8"))
            json.loads((first_dir / "candles.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

import filecmp
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from data_generator import BASE_TIMESTAMP_MS, DataGenerator  # noqa: E402


def generated_payload(seed: int) -> dict:
    generator = DataGenerator(seed)
    users = generator.generate_users(5)
    orders = generator.generate_orders(10)
    trades = generator.generate_trades(10)
    ticks = {
        instrument["symbol"]: generator.generate_ticks(instrument["symbol"], 5)
        for instrument in generator.instruments
    }
    candles = {
        f'{instrument["symbol"]}_60min': generator.generate_candles(instrument["symbol"], 60, 5)
        for instrument in generator.instruments
    }
    return {
        "users": users,
        "orders": orders,
        "trades": trades,
        "ticks": ticks,
        "candles": candles,
        "instruments": generator.instruments,
    }


class DataGeneratorDeterminismTests(unittest.TestCase):
    def test_same_seed_produces_identical_in_memory_output(self):
        self.assertEqual(generated_payload(42), generated_payload(42))

    def test_different_seeds_produce_different_in_memory_output(self):
        self.assertNotEqual(generated_payload(42), generated_payload(43))

    def test_tick_and_candle_timestamps_use_fixed_base(self):
        payload = generated_payload(42)
        ticks = payload["ticks"]["BTC/USD"]
        candles = payload["candles"]["BTC/USD_60min"]

        self.assertEqual(ticks[0]["timestamp"], BASE_TIMESTAMP_MS - 5 * 1000)
        self.assertEqual(ticks[-1]["timestamp"], BASE_TIMESTAMP_MS - 1000)
        self.assertEqual(candles[0]["time"], BASE_TIMESTAMP_MS - 5 * 60 * 60 * 1000)
        self.assertEqual(candles[-1]["time"], BASE_TIMESTAMP_MS - 60 * 60 * 1000)

    def test_cli_json_output_is_identical_for_same_seed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            command = [
                sys.executable,
                str(ROOT / "tools" / "data_generator.py"),
                "--seed", "123",
                "--users", "5",
                "--orders", "10",
                "--trades", "10",
                "--ticks", "5",
                "--candles", "5",
                "--format", "json",
            ]
            subprocess.run(command + ["--output-dir", str(first)], check=True, cwd=ROOT)
            subprocess.run(command + ["--output-dir", str(second)], check=True, cwd=ROOT)

            for filename in (
                "users.json",
                "orders.json",
                "trades.json",
                "ticks.json",
                "candles.json",
                "instruments.json",
            ):
                self.assertTrue(
                    filecmp.cmp(first / filename, second / filename, shallow=False),
                    f"{filename} differs between same-seed CLI runs",
                )

            ticks = json.loads((first / "ticks.json").read_text())
            candles = json.loads((first / "candles.json").read_text())
            self.assertEqual(ticks["BTC/USD"][0]["timestamp"], BASE_TIMESTAMP_MS - 5000)
            self.assertEqual(
                candles["BTC/USD_60min"][0]["time"],
                BASE_TIMESTAMP_MS - 5 * 60 * 60 * 1000,
            )


if __name__ == "__main__":
    unittest.main()

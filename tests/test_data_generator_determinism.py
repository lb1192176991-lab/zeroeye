"""
Regression tests for deterministic output in data_generator.py.

Verifies that:
1. Two generators with the same seed produce identical output (in-process)
2. Two generators with different seeds produce different output
3. CLI runs with the same seed produce byte-identical JSON files
4. tick/candle timestamps are fixed (no time.time() leakage)
5. user phone/email/datetime are deterministic (no global random leakage)
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

# Make sure the tools directory is on the path when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from data_generator import DataGenerator


class TestDeterminism(unittest.TestCase):

    def _full_dataset(self, seed: int) -> dict:
        """Generate a complete dataset with the given seed and return it as a dict."""
        gen = DataGenerator(seed=seed)
        users = gen.generate_users(10)
        orders = gen.generate_orders(20)
        trades = gen.generate_trades(30)
        ticks = gen.generate_ticks("BTC/USD", 50)
        candles = gen.generate_candles("ETH/USD", 60, 20)
        return {
            "users": users,
            "orders": orders,
            "trades": trades,
            "ticks": ticks,
            "candles": candles,
        }

    # ------------------------------------------------------------------
    # 1. Same seed → identical in-process output
    # ------------------------------------------------------------------
    def test_in_process_determinism(self):
        a = self._full_dataset(42)
        b = self._full_dataset(42)
        self.assertEqual(
            a, b,
            "Two DataGenerator instances with seed=42 must produce identical output.",
        )

    # ------------------------------------------------------------------
    # 2. Different seeds → different output
    # ------------------------------------------------------------------
    def test_different_seed_different_data(self):
        a = self._full_dataset(42)
        b = self._full_dataset(99)
        self.assertNotEqual(
            a["users"], b["users"],
            "Different seeds must produce different user data.",
        )
        self.assertNotEqual(
            a["ticks"], b["ticks"],
            "Different seeds must produce different tick data.",
        )

    # ------------------------------------------------------------------
    # 3. CLI JSON runs with same seed produce byte-identical files
    # ------------------------------------------------------------------
    def test_cli_json_determinism(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_generator.py")
        if not os.path.exists(script):
            # Fallback: look in ../tools/ relative to this test file
            script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "tools", "data_generator.py"
            )
        with tempfile.TemporaryDirectory() as dir_a, \
             tempfile.TemporaryDirectory() as dir_b:

            for out_dir in (dir_a, dir_b):
                result = subprocess.run(
                    [sys.executable, script,
                     "--seed", "42",
                     "--users", "10",
                     "--orders", "20",
                     "--trades", "30",
                     "--ticks", "50",
                     "--candles", "20",
                     "--format", "json",
                     "--output-dir", out_dir],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"CLI exited with non-zero code:\n{result.stderr}",
                )

            for filename in ("users.json", "orders.json", "trades.json",
                             "ticks.json", "candles.json"):
                path_a = os.path.join(dir_a, filename)
                path_b = os.path.join(dir_b, filename)
                with open(path_a) as fa, open(path_b) as fb:
                    content_a = fa.read()
                    content_b = fb.read()
                self.assertEqual(
                    content_a, content_b,
                    f"{filename}: CLI runs with the same seed must produce identical output.",
                )

    # ------------------------------------------------------------------
    # 4. Tick timestamps must not depend on wall-clock time
    # ------------------------------------------------------------------
    def test_tick_timestamps_are_fixed(self):
        import time
        gen1 = DataGenerator(seed=7)
        ticks1 = gen1.generate_ticks("BTC/USD", 10)

        time.sleep(0.05)  # small wall-clock delay

        gen2 = DataGenerator(seed=7)
        ticks2 = gen2.generate_ticks("BTC/USD", 10)

        timestamps1 = [t["timestamp"] for t in ticks1]
        timestamps2 = [t["timestamp"] for t in ticks2]
        self.assertEqual(
            timestamps1, timestamps2,
            "Tick timestamps must be fixed and must not use time.time().",
        )

    # ------------------------------------------------------------------
    # 5. Candle timestamps must not depend on wall-clock time
    # ------------------------------------------------------------------
    def test_candle_timestamps_are_fixed(self):
        import time
        gen1 = DataGenerator(seed=7)
        candles1 = gen1.generate_candles("ETH/USD", 60, 10)

        time.sleep(0.05)

        gen2 = DataGenerator(seed=7)
        candles2 = gen2.generate_candles("ETH/USD", 60, 10)

        times1 = [c["time"] for c in candles1]
        times2 = [c["time"] for c in candles2]
        self.assertEqual(
            times1, times2,
            "Candle timestamps must be fixed and must not use time.time().",
        )

    # ------------------------------------------------------------------
    # 6. User fields (phone, email, created_at) are deterministic
    # ------------------------------------------------------------------
    def test_user_fields_are_deterministic(self):
        gen1 = DataGenerator(seed=123)
        users1 = gen1.generate_users(5)

        gen2 = DataGenerator(seed=123)
        users2 = gen2.generate_users(5)

        for i, (u1, u2) in enumerate(zip(users1, users2)):
            self.assertEqual(u1["phone"], u2["phone"],
                             f"User {i} phone not deterministic")
            self.assertEqual(u1["email"], u2["email"],
                             f"User {i} email not deterministic")
            self.assertEqual(u1["created_at"], u2["created_at"],
                             f"User {i} created_at not deterministic")


if __name__ == "__main__":
    unittest.main()

import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import health_check


ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_main_returns_failure_for_degraded_result(self):
        with patch("tools.health_check.parse_args") as parse_args:
            parse_args.return_value.service = None
            parse_args.return_value.json = True
            parse_args.return_value.watch = False
            parse_args.return_value.output = None
            parse_args.return_value.retries = 0
            parse_args.return_value.retry_backoff = 0
            with patch(
                "tools.health_check.run_health_checks",
                return_value={"overall_status": "DEGRADED"},
            ):
                self.assertEqual(health_check.main(), 1)

    def test_script_propagates_main_exit_code(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        env = os.environ.copy()
        env.update(DB_HOST="127.0.0.1", DB_PORT=str(port))
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "health_check.py"),
                "--service",
                "postgresql",
                "--retries",
                "0",
                "--retry-backoff",
                "0",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn('"overall_status": "DEGRADED"', result.stdout)

    def test_cli_rejects_unknown_service(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "health_check.py"), "--service", "typo"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice: 'typo'", result.stderr)


if __name__ == "__main__":
    unittest.main()

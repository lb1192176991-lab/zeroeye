import unittest
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import health_check


class RetryCheckTests(unittest.TestCase):
    def test_http_service_retries_after_transient_failure(self):
        calls = []

        def fake_attempt():
            calls.append(None)
            if len(calls) == 1:
                return "CRITICAL", "temporary failure", 0
            return "OK", "HTTP 200", 200

        with mock.patch("tools.health_check.time.sleep") as sleep_mock:
            result = health_check.retry_check(fake_attempt, attempts=2, delay_seconds=0)

        self.assertEqual(result, ("OK", "HTTP 200", 200))
        self.assertEqual(len(calls), 2)
        sleep_mock.assert_called_once_with(0)

    def test_retry_check_returns_last_failure(self):
        calls = []

        def fake_attempt():
            calls.append(None)
            return "CRITICAL", "still failing", 0

        with mock.patch("tools.health_check.time.sleep") as sleep_mock:
            result = health_check.retry_check(fake_attempt, attempts=3, delay_seconds=0)

        self.assertEqual(result, ("CRITICAL", "still failing", 0))
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()

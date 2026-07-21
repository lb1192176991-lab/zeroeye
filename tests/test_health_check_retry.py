"""Tests for transient retry behaviour in tools/health_check.py."""

import unittest
from unittest.mock import patch

from tools.health_check import (
    TransientCheckError,
    check_http_service_with_retry,
    check_tcp_port_with_retry,
    retry_transient,
)


class RetryHelperTests(unittest.TestCase):
    def test_succeeds_on_first_attempt(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            return "ok"

        self.assertEqual(retry_transient(probe, max_retries=3), "ok")
        self.assertEqual(calls["n"], 1)

    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TransientCheckError("transient")
            return "ok"

        with patch("tools.health_check.time.sleep"):
            self.assertEqual(retry_transient(probe, max_retries=3, backoff_base=0.01), "ok")
        self.assertEqual(calls["n"], 3)

    def test_exhausts_retries(self):
        def probe():
            raise TransientCheckError("still failing")

        with patch("tools.health_check.time.sleep"):
            with self.assertRaises(TransientCheckError):
                retry_transient(probe, max_retries=2, backoff_base=0.01)


class HttpRetryTests(unittest.TestCase):
    @patch("tools.health_check.check_http_service")
    def test_http_success_after_retry(self, mock_check):
        mock_check.side_effect = [
            TransientCheckError("timeout"),
            ("OK", "HTTP 200", 200),
        ]
        with patch("tools.health_check.time.sleep"):
            status, detail, code = check_http_service_with_retry(
                "localhost", 8080, "/health", 5, max_retries=3, backoff_base=0.01
            )
        self.assertEqual(status, "OK")
        self.assertEqual(code, 200)
        self.assertEqual(mock_check.call_count, 2)

    @patch("tools.health_check.check_http_service")
    def test_http_persistent_failure(self, mock_check):
        mock_check.side_effect = TransientCheckError("HTTP 503: unavailable")
        with patch("tools.health_check.time.sleep"):
            status, detail, code = check_http_service_with_retry(
                "localhost", 8080, "/health", 5, max_retries=2, backoff_base=0.01
            )
        self.assertEqual(status, "CRITICAL")
        self.assertIn("503", detail)
        self.assertEqual(code, 0)


class TcpRetryTests(unittest.TestCase):
    @patch("tools.health_check.check_tcp_port")
    def test_tcp_success_after_retry(self, mock_check):
        mock_check.side_effect = [
            TransientCheckError("Connection refused"),
            ("OK", "Connected (1.2ms)", 1.2),
        ]
        with patch("tools.health_check.time.sleep"):
            status, detail, latency = check_tcp_port_with_retry(
                "localhost", 5432, 5, max_retries=3, backoff_base=0.01
            )
        self.assertEqual(status, "OK")
        self.assertAlmostEqual(latency, 1.2)
        self.assertEqual(mock_check.call_count, 2)


if __name__ == "__main__":
    unittest.main()

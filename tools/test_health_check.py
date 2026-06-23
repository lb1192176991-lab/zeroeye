#!/usr/bin/env python3
"""Unit tests for health_check.py: TokenBucket, CircuitBreaker, and timeout/retry logic."""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from health_check import (
    TokenBucket,
    CircuitBreaker,
    check_http_service,
    CIRCUIT_CLOSED,
    CIRCUIT_OPEN,
    CIRCUIT_HALF_OPEN,
)


class TestTokenBucket(unittest.TestCase):
    """Tests for the TokenBucket rate limiter."""

    def test_init_positive_rate(self):
        """TokenBucket initializes with a positive rate."""
        tb = TokenBucket(rate=5)
        self.assertEqual(tb.current_rate, 5)
        self.assertEqual(tb.throttled, 0)

    def test_init_zero_rate_raises(self):
        """TokenBucket raises ValueError for non-positive rate."""
        with self.assertRaises(ValueError):
            TokenBucket(rate=0)

    def test_init_negative_rate_raises(self):
        """TokenBucket raises ValueError for negative rate."""
        with self.assertRaises(ValueError):
            TokenBucket(rate=-1)

    def test_acquire_returns_true_when_tokens_available(self):
        """Acquire returns True when tokens are available."""
        tb = TokenBucket(rate=100, burst=10)
        self.assertTrue(tb.acquire(blocking=False))

    def test_acquire_returns_false_when_exhausted(self):
        """Acquire returns False when no tokens remain."""
        tb = TokenBucket(rate=0.001, burst=1)
        # Consume the only token
        self.assertTrue(tb.acquire(blocking=False))
        # Next should be throttled
        self.assertFalse(tb.acquire(blocking=False))

    def test_throttled_count(self):
        """Throttled count tracks blocked requests."""
        tb = TokenBucket(rate=0.001, burst=2)
        tb.acquire(blocking=False)  # allowed
        tb.acquire(blocking=False)  # allowed
        tb.acquire(blocking=False)  # throttled
        tb.acquire(blocking=False)  # throttled
        self.assertEqual(tb.throttled, 2)
        self.assertEqual(tb.total_requests, 4)

    def test_burst_allows_short_spike(self):
        """Burst allows consuming multiple tokens at once."""
        tb = TokenBucket(rate=0.1, burst=5)
        # Should be able to acquire 5 tokens immediately
        for _ in range(5):
            self.assertTrue(tb.acquire(blocking=False))
        # 6th should be throttled
        self.assertFalse(tb.acquire(blocking=False))

    def test_stats_returns_dict(self):
        """Stats returns expected keys."""
        tb = TokenBucket(rate=5)
        stats = tb.stats()
        self.assertIn("rate", stats)
        self.assertIn("burst", stats)
        self.assertIn("throttled", stats)
        self.assertIn("total_requests", stats)
        self.assertIn("current_tokens", stats)
        self.assertEqual(stats["rate"], 5)


class TestCircuitBreaker(unittest.TestCase):
    """Tests for the CircuitBreaker."""

    def test_initial_state_closed(self):
        """Initial state is CLOSED."""
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CIRCUIT_CLOSED)

    def test_allows_request_when_closed(self):
        """allow_request returns True when CLOSED."""
        cb = CircuitBreaker()
        self.assertTrue(cb.allow_request())

    def test_opens_after_failures(self):
        """Circuit opens after failure threshold is reached."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=9999)
        self.assertEqual(cb.state, CIRCUIT_CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, CIRCUIT_CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, CIRCUIT_OPEN)

    def test_blocks_when_open(self):
        """allow_request returns False when OPEN."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()
        self.assertFalse(cb.allow_request())

    def test_half_open_after_recovery_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        self.assertEqual(cb.state, CIRCUIT_OPEN)
        time.sleep(0.02)
        self.assertEqual(cb.state, CIRCUIT_HALF_OPEN)

    def test_closes_after_success_in_half_open(self):
        """HALF_OPEN transitions back to CLOSED on success."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        self.assertEqual(cb.state, CIRCUIT_HALF_OPEN)
        cb.record_success()
        self.assertEqual(cb.state, CIRCUIT_CLOSED)

    def test_stats_returns_dict(self):
        """Stats returns expected keys."""
        cb = CircuitBreaker()
        stats = cb.stats()
        self.assertIn("state", stats)
        self.assertEqual(stats["state"], CIRCUIT_CLOSED)


class TestCheckHTTPServiceTimeout(unittest.TestCase):
    """Tests for timeout and retry behavior in check_http_service."""

    @patch("health_check.http.client.HTTPConnection")
    def test_retries_on_server_error(self, mock_conn):
        """Retries on 5xx errors with backoff."""
        instance = MagicMock()
        instance.getresponse.return_value.status = 500
        instance.getresponse.return_value.read.return_value = b"error"
        mock_conn.return_value = instance

        status, detail, code = check_http_service(
            "localhost", 8080, "/health",
            timeout=5, retries=3, backoff_base=0.01,
        )
        self.assertEqual(status, "CRITICAL")
        self.assertEqual(code, 500)
        # Should have been called 3 times (retries=3)
        self.assertEqual(instance.request.call_count, 3)

    @patch("health_check.http.client.HTTPConnection")
    def test_does_not_retry_on_client_error(self, mock_conn):
        """Does not retry on 4xx client errors."""
        instance = MagicMock()
        instance.getresponse.return_value.status = 404
        instance.getresponse.return_value.read.return_value = b"not found"
        mock_conn.return_value = instance

        status, detail, code = check_http_service(
            "localhost", 8080, "/health",
            timeout=5, retries=3, backoff_base=0.01,
        )
        self.assertEqual(status, "WARNING")
        self.assertEqual(code, 404)
        # Should only be called once (no retry on 4xx)
        self.assertEqual(instance.request.call_count, 1)

    @patch("health_check.http.client.HTTPConnection")
    def test_success_no_retry(self, mock_conn):
        """Returns OK immediately on 200, no retries."""
        instance = MagicMock()
        instance.getresponse.return_value.status = 200
        instance.getresponse.return_value.read.return_value = b"ok"
        mock_conn.return_value = instance

        status, detail, code = check_http_service(
            "localhost", 8080, "/health",
            timeout=5, retries=3, backoff_base=0.01,
        )
        self.assertEqual(status, "OK")
        self.assertEqual(code, 200)
        self.assertEqual(instance.request.call_count, 1)

    @patch("health_check.http.client.HTTPConnection")
    def test_circuit_breaker_blocks_open(self, mock_conn):
        """Returns CRITICAL immediately when circuit breaker is OPEN."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()  # opens the circuit

        status, detail, code = check_http_service(
            "localhost", 8080, "/health",
            timeout=5, circuit_breaker=cb,
        )
        self.assertEqual(status, "CRITICAL")
        self.assertIn("Circuit breaker OPEN", detail)
        mock_conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()

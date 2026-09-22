import argparse
import http.client
import socket
import unittest
from unittest.mock import Mock, call, patch

from tools import health_check


class FakeResponse:
    def __init__(self, status, body=b""):
        self.status = status
        self.body = body

    def read(self):
        return self.body


class HttpRetryTests(unittest.TestCase):
    def connection(self, *outcomes):
        conn = Mock()
        conn.getresponse.side_effect = outcomes
        return conn

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_success_does_not_retry(self, sleep, http_connection):
        conn = self.connection(FakeResponse(200))
        http_connection.return_value = conn

        result = health_check.check_http_service("api", 80, "/health", 1)

        self.assertEqual(result, ("OK", "HTTP 200", 200))
        self.assertEqual(conn.request.call_count, 1)
        sleep.assert_not_called()
        conn.close.assert_called_once()

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_retries_server_error_then_recovers(self, sleep, http_connection):
        conn = self.connection(FakeResponse(503, b"busy"), FakeResponse(200))
        http_connection.return_value = conn

        result = health_check.check_http_service(
            "api", 80, "/health", 1, retries=2, retry_backoff=0.5
        )

        self.assertEqual(result, ("OK", "HTTP 200", 200))
        self.assertEqual(conn.request.call_count, 2)
        sleep.assert_called_once_with(0.5)
        self.assertEqual(conn.close.call_count, 2)

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_returns_last_server_error(self, sleep, http_connection):
        conn = self.connection(
            FakeResponse(500, b"one"),
            FakeResponse(502, b"two"),
            FakeResponse(503, b"three"),
        )
        http_connection.return_value = conn

        result = health_check.check_http_service(
            "api", 80, "/health", 1, retries=2, retry_backoff=0.25
        )

        self.assertEqual(result, ("CRITICAL", "HTTP 503: three", 503))
        self.assertEqual(sleep.call_args_list, [call(0.25), call(0.5)])

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_client_error_is_not_retried(self, sleep, http_connection):
        conn = self.connection(FakeResponse(404, b"missing"))
        http_connection.return_value = conn

        result = health_check.check_http_service("api", 80, "/health", 1)

        self.assertEqual(result, ("WARNING", "HTTP 404: missing", 404))
        self.assertEqual(conn.request.call_count, 1)
        sleep.assert_not_called()


    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_retries_rate_limit_response(self, sleep, http_connection):
        conn = self.connection(FakeResponse(429, b"slow down"), FakeResponse(200))
        http_connection.return_value = conn

        result = health_check.check_http_service(
            "api", 80, "/health", 1, retries=1, retry_backoff=0.25
        )

        self.assertEqual(result, ("OK", "HTTP 200", 200))
        sleep.assert_called_once_with(0.25)

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_zero_retries_means_one_attempt(self, sleep, http_connection):
        conn = self.connection(FakeResponse(503, b"busy"))
        http_connection.return_value = conn

        result = health_check.check_http_service(
            "api", 80, "/health", 1, retries=0, retry_backoff=0.25
        )

        self.assertEqual(result, ("CRITICAL", "HTTP 503: busy", 503))
        self.assertEqual(conn.request.call_count, 1)
        sleep.assert_not_called()

    @patch("http.client.HTTPConnection")
    @patch("tools.health_check.time.sleep")
    def test_retries_transport_error_and_closes_connection(self, sleep, http_connection):
        first = Mock()
        first.request.side_effect = socket.timeout("timed out")
        second = self.connection(FakeResponse(200))
        http_connection.side_effect = [first, second]

        result = health_check.check_http_service(
            "api", 80, "/health", 1, retries=1, retry_backoff=0
        )

        self.assertEqual(result, ("OK", "HTTP 200", 200))
        first.close.assert_called_once()
        second.close.assert_called_once()
        sleep.assert_called_once_with(0)


    @patch("http.client.HTTPConnection")
    def test_close_error_does_not_hide_http_result(self, http_connection):
        conn = self.connection(FakeResponse(200))
        conn.close.side_effect = OSError("close failed")
        http_connection.return_value = conn

        result = health_check.check_http_service("api", 80, "/health", 1)

        self.assertEqual(result, ("OK", "HTTP 200", 200))

    @patch("http.client.HTTPConnection")
    def test_persistent_http_exception_keeps_last_error(self, http_connection):
        conn = Mock()
        conn.request.side_effect = http.client.RemoteDisconnected("peer closed")
        http_connection.return_value = conn

        with patch("tools.health_check.time.sleep"):
            result = health_check.check_http_service(
                "api", 80, "/health", 1, retries=1, retry_backoff=0
            )

        self.assertEqual(result, ("CRITICAL", "peer closed", 0))
        self.assertEqual(conn.request.call_count, 2)


class TcpRetryTests(unittest.TestCase):
    @patch("tools.health_check.socket.create_connection")
    @patch("tools.health_check.time.sleep")
    @patch("tools.health_check.time.monotonic", side_effect=[1.0, 2.0, 2.012])
    def test_retries_refused_connection_then_recovers(self, monotonic, sleep, connect):
        sock = Mock()
        connect.side_effect = [ConnectionRefusedError(), sock]

        result = health_check.check_tcp_port(
            "db", 5432, 1, retries=2, retry_backoff=0.1
        )

        self.assertEqual(result[:2], ("OK", "Connected (12.0ms)"))
        self.assertAlmostEqual(result[2], 12.0)
        sleep.assert_called_once_with(0.1)
        sock.close.assert_called_once()


    @patch("tools.health_check.socket.create_connection")
    def test_close_error_does_not_hide_success(self, connect):
        sock = Mock()
        sock.close.side_effect = OSError("close failed")
        connect.return_value = sock

        with patch("tools.health_check.time.monotonic", side_effect=[1.0, 1.001]):
            result = health_check.check_tcp_port("db", 5432, 1)

        self.assertEqual(result[:2], ("OK", "Connected (1.0ms)"))

    @patch("tools.health_check.socket.create_connection")
    @patch("tools.health_check.time.sleep")
    def test_returns_timeout_after_all_attempts(self, sleep, connect):
        connect.side_effect = socket.timeout()

        result = health_check.check_tcp_port(
            "db", 5432, 3, retries=2, retry_backoff=0.2
        )

        self.assertEqual(result, ("CRITICAL", "Connection timeout (3s)", 0))
        self.assertEqual(connect.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(0.2), call(0.4)])


class RetryConfigurationTests(unittest.TestCase):
    def test_rejects_bad_values_in_python_api(self):
        for retries, backoff in [(-1, 0), (0, -1), (0, float("inf")), (0, float("nan"))]:
            with self.subTest(retries=retries, backoff=backoff):
                with self.assertRaises(ValueError):
                    health_check.check_tcp_port(
                        "db", 5432, 1, retries=retries, retry_backoff=backoff
                    )


    def test_unknown_service_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown service: typo"):
            health_check.run_health_checks("typo")

    def test_cli_value_parsers(self):
        self.assertEqual(health_check.non_negative_int("0"), 0)
        self.assertEqual(health_check.non_negative_float("0.5"), 0.5)
        for parser, value in [
            (health_check.non_negative_int, "-1"),
            (health_check.non_negative_float, "-0.1"),
            (health_check.non_negative_float, "nan"),
        ]:
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    parser(value)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest
from unittest.mock import Mock, patch

from tools import health_check


SAMPLE = """GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID
tent-consumers orders 0 40 50 10 c1 /127.0.0.1 client
tent-consumers orders 1 70 100 30 c2 /127.0.0.1 client
"""


class KafkaLagTests(unittest.TestCase):
    def test_parse_consumer_lag_sums_partitions(self):
        self.assertEqual(health_check.parse_consumer_lag(SAMPLE), (40, 2))

    def test_parse_consumer_lag_rejects_empty_output(self):
        with self.assertRaises(ValueError):
            health_check.parse_consumer_lag("GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG")

    @patch("tools.health_check.subprocess.run")
    def test_ok_below_warning_threshold(self, run):
        run.return_value = Mock(returncode=0, stdout=SAMPLE, stderr="")
        status, detail, lag = health_check.check_kafka_consumer_lag("kafka", 9092, "workers")
        self.assertEqual((status, lag), ("OK", 40))
        self.assertIn("2 partitions", detail)
        self.assertEqual(run.call_args.args[0][2:4], ["kafka:9092", "--group"])
        self.assertEqual(run.call_args.args[0][4], "workers")

    @patch("tools.health_check.subprocess.run")
    def test_warning_at_warning_threshold(self, run):
        output = SAMPLE.replace(" 10 c1", " 1000 c1").replace(" 30 c2", " 0 c2")
        run.return_value = Mock(returncode=0, stdout=output, stderr="")
        self.assertEqual(health_check.check_kafka_consumer_lag("k", 1, "g")[0], "WARNING")

    @patch("tools.health_check.subprocess.run")
    def test_critical_at_critical_threshold(self, run):
        output = SAMPLE.replace(" 10 c1", " 10000 c1").replace(" 30 c2", " 0 c2")
        run.return_value = Mock(returncode=0, stdout=output, stderr="")
        self.assertEqual(health_check.check_kafka_consumer_lag("k", 1, "g")[0], "CRITICAL")

    @patch("tools.health_check.subprocess.run")
    def test_command_failure_is_warning(self, run):
        run.return_value = Mock(returncode=1, stdout="", stderr="broker unavailable")
        status, detail, lag = health_check.check_kafka_consumer_lag("k", 1, "g")
        self.assertEqual((status, lag), ("WARNING", 0))
        self.assertEqual(detail, "broker unavailable")

    @patch("tools.health_check.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_kafka_tool_is_warning(self, _run):
        status, detail, lag = health_check.check_kafka_consumer_lag("k", 1, "g")
        self.assertEqual((status, lag), ("WARNING", 0))
        self.assertIn("not found", detail)

    @patch("tools.health_check.subprocess.run", side_effect=subprocess.TimeoutExpired("kafka", 15))
    def test_timeout_is_warning(self, _run):
        self.assertEqual(health_check.check_kafka_consumer_lag("k", 1, "g")[0], "WARNING")

    @patch("tools.health_check.check_load_average", return_value=("OK", "fine", 0))
    @patch("tools.health_check.check_memory_usage", return_value=("OK", "fine", 0))
    @patch("tools.health_check.check_disk_usage", return_value=("OK", "fine", 0))
    @patch("tools.health_check.check_kafka_consumer_lag", return_value=("CRITICAL", "12000 messages", 12000))
    @patch("tools.health_check.check_tcp_port", return_value=("OK", "connected", 1))
    def test_critical_lag_degrades_kafka_health(self, _tcp, _lag, _disk, _memory, _load):
        result = health_check.run_health_checks("kafka")
        lag = result["infrastructure"]["kafka"]["consumer_lag"]
        self.assertEqual(lag["messages"], 12000)
        self.assertEqual(lag["group"], "tent-consumers")
        self.assertEqual(result["overall_status"], "DEGRADED")


if __name__ == "__main__":
    unittest.main()

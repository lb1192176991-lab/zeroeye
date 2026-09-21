import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.log_aggregator import LogAggregator

ROOT = Path(__file__).resolve().parents[1]


class LogAggregatorJsonlTests(unittest.TestCase):
    def setUp(self):
        self.aggregator = LogAggregator()
        self.aggregator.entries = [
            {
                "timestamp": 1700000000,
                "level": "info",
                "service": "api",
                "message": "started",
                "fields": {"request_id": "abc", "attempt": 1},
                "format": "json",
            },
            {
                "timestamp": 1700000001,
                "level": "error",
                "service": "worker",
                "message": "处理失败",
                "fields": {"retryable": False},
                "format": "json",
            },
        ]

    def export(self, max_entries=10000):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "logs.jsonl"
        self.aggregator.export_jsonl(str(output), max_entries=max_entries)
        return output

    def test_each_line_is_a_complete_json_record(self):
        lines = self.export().read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line) for line in lines], self.aggregator.entries)

    def test_nested_fields_are_preserved(self):
        record = json.loads(self.export().read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["fields"], {"request_id": "abc", "attempt": 1})

    def test_unicode_round_trips(self):
        text = self.export().read_text(encoding="utf-8")
        self.assertIn("处理失败", text)
        self.assertEqual(json.loads(text.splitlines()[1])["message"], "处理失败")

    def test_max_entries_limits_output(self):
        lines = self.export(max_entries=1).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), self.aggregator.entries[0])

    def test_empty_aggregator_writes_empty_file(self):
        self.aggregator.entries = []
        self.assertEqual(self.export().read_text(encoding="utf-8"), "")

    def test_non_json_values_use_string_fallback(self):
        value = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.aggregator.entries = [{"timestamp": value}]
        record = json.loads(self.export().read_text(encoding="utf-8"))
        self.assertEqual(record["timestamp"], str(value))

    def test_existing_json_export_is_unchanged(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output = Path(temp_dir.name) / "report.json"
        self.aggregator.export_json(str(output))
        report = json.loads(output.read_text())
        self.assertEqual(report["entries"], self.aggregator.entries)
        self.assertIn("summary", report)

    def test_cli_writes_jsonl_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.log"
            output = Path(temp_dir) / "output.jsonl"
            source.write_text(
                '{"timestamp": 1700000000, "level": "info", "message": "one"}\n'
                '{"timestamp": 1700000001, "level": "error", "message": "two"}\n',
                encoding="utf-8",
            )
            subprocess.run([
                sys.executable,
                str(ROOT / "tools" / "log_aggregator.py"),
                "--input", str(source),
                "--format", "jsonl",
                "--output", str(output),
            ], check=True, capture_output=True, text=True)
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([record["message"] for record in records], ["one", "two"])
            self.assertTrue(all("fields" in record for record in records))


if __name__ == "__main__":
    unittest.main()

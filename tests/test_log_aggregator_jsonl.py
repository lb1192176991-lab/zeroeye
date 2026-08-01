#!/usr/bin/env python3
"""
Tests for the JSONL output mode added in tools/log_aggregator.py.

These tests cover the public surface required by issue #3
(lb1192176991-lab/zeroeye): a JSON Lines export from ``LogAggregator``
that is one self-contained JSON object per line, with stable field
ordering and a default to file output (with an opt-in stdout mode).
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest

# Make ``tools`` importable when running the file directly.
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from log_aggregator import JSONLogParser, LogAggregator  # noqa: E402


def _make_aggregator() -> LogAggregator:
    """Build an aggregator with three representative entries."""
    parser = JSONLogParser()
    lines = [
        json.dumps({"timestamp": "2024-01-15T10:00:00", "level": "info",
                    "service": "api", "message": "started"}),
        json.dumps({"timestamp": "2024-01-15T10:00:01", "level": "error",
                    "service": "api", "message": "boom"}),
        json.dumps({"timestamp": "2024-01-15T10:00:02", "level": "warn",
                    "service": "worker", "message": "retry"}),
    ]
    aggregator = LogAggregator()
    for line in lines:
        parsed = parser.parse(line)
        assert parsed is not None, f"parser rejected valid JSON line: {line}"
        aggregator.entries.append(parsed)
    return aggregator


class LogAggregatorJsonlTests(unittest.TestCase):
    def test_export_jsonl_writes_one_object_per_line(self):
        aggregator = _make_aggregator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "out.jsonl")
            count = aggregator.export_jsonl(out_path)
            self.assertEqual(count, 3)
            with open(out_path, "r", encoding="utf-8") as f:
                raw = f.read()
        # Trailing newline only.
        self.assertTrue(raw.endswith("\n"))
        self.assertFalse(raw.endswith("\n\n"))
        lines = raw.split("\n")
        # 3 entries + 1 trailing empty after final newline.
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[-1], "")
        for body in lines[:-1]:
            obj = json.loads(body)
            self.assertIsInstance(obj, dict)

    def test_export_jsonl_field_order_is_stable(self):
        aggregator = _make_aggregator()
        buf = io.StringIO()
        aggregator.export_jsonl(stream=buf)
        for line in buf.getvalue().splitlines():
            obj = json.loads(line)
            self.assertEqual(
                list(obj.keys()),
                ["timestamp", "level", "service", "message", "format"],
            )

    def test_export_jsonl_streaming_to_stdout(self):
        aggregator = _make_aggregator()
        buf = io.StringIO()
        returned = aggregator.export_jsonl(stream=buf)
        self.assertEqual(returned, 3)
        self.assertFalse(buf.closed)  # caller owns lifetime when stream is passed
        lines = [line for line in buf.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 3)
        services = [json.loads(body)["service"] for body in lines]
        self.assertEqual(services, ["api", "api", "worker"])
        for body in lines:
            self.assertIn(json.loads(body)["service"], {"api", "worker"})

    def test_export_jsonl_respects_max_entries(self):
        aggregator = _make_aggregator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "out.jsonl")
            count = aggregator.export_jsonl(out_path, max_entries=2)
            self.assertEqual(count, 2)
            with open(out_path, "r", encoding="utf-8") as f:
                raw = f.read()
        lines = [line for line in raw.splitlines() if line]
        self.assertEqual(len(lines), 2)

    def test_export_jsonl_handles_empty_aggregator(self):
        aggregator = LogAggregator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "out.jsonl")
            count = aggregator.export_jsonl(out_path)
            self.assertEqual(count, 0)
            with open(out_path, "r", encoding="utf-8") as f:
                raw = f.read()
        self.assertEqual(raw, "")

    def test_export_jsonl_rejects_path_and_stream_together(self):
        aggregator = _make_aggregator()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "out.jsonl")
            with self.assertRaises(ValueError):
                aggregator.export_jsonl(output_path=out_path, stream=io.StringIO())

    def test_export_jsonl_preserves_non_ascii_message(self):
        parser = JSONLogParser()
        aggregator = LogAggregator()
        aggregator.entries.append(parser.parse(json.dumps({
            "timestamp": "2024-01-15T10:00:00",
            "level": "info",
            "service": "api",
            "message": "服务启动 OK",
        })))
        buf = io.StringIO()
        aggregator.export_jsonl(stream=buf)
        body = buf.getvalue().strip()
        self.assertIn("服务启动 OK", body)
        obj = json.loads(body)
        self.assertEqual(obj["message"], "服务启动 OK")

    def test_export_jsonl_does_not_close_caller_stream(self):
        aggregator = _make_aggregator()
        buf = io.StringIO()
        aggregator.export_jsonl(stream=buf)
        self.assertFalse(buf.closed)
        buf.close()


class LogAggregatorJsonlCliTests(unittest.TestCase):
    def test_main_accepts_jsonl_format_choice(self):
        # We only verify argparse accepts the new choice; end-to-end
        # execution is covered by the unit tests above and run manually.
        from log_aggregator import parse_args
        saved = sys.argv
        try:
            sys.argv = ["log_aggregator.py", "--format", "jsonl",
                        "--input", "app.log"]
            args = parse_args()
        finally:
            sys.argv = saved
        self.assertEqual(args.format, "jsonl")


if __name__ == "__main__":
    unittest.main()
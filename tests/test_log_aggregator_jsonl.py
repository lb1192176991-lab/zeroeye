#!/usr/bin/env python3
"""Tests for the JSONL export functionality in log_aggregator.py."""

import json
import os
import sys
import tempfile
import unittest

# Add parent dir so we can import tools.log_aggregator
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Direct import via sys.path manipulation
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from log_aggregator import LogAggregator  # noqa: E402


class TestLogAggregatorJsonlExport(unittest.TestCase):
    """Test suite for JSONL export format."""

    def setUp(self):
        self.aggregator = LogAggregator()
        # Manually add some test entries
        self.aggregator.entries = [
            {
                'timestamp': 1700000000,
                'level': 'error',
                'service': 'backend',
                'message': 'Connection refused',
                'format': 'text',
                'fields': {'raw': 'ERROR [backend] Connection refused'},
            },
            {
                'timestamp': 1700000001,
                'level': 'info',
                'service': 'frontend',
                'message': 'Request completed',
                'format': 'json',
                'fields': {'status': 200},
            },
            {
                'timestamp': 1700000002,
                'level': 'warn',
                'service': 'market',
                'message': 'Rate limit approaching',
                'format': 'nginx',
                'fields': {'status': 429},
            },
        ]

    def test_export_jsonl_creates_file(self):
        """export_jsonl should create the output file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            self.aggregator.export_jsonl(output_path)
            self.assertTrue(os.path.exists(output_path))
            with open(output_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 3)
        finally:
            os.unlink(output_path)

    def test_export_jsonl_each_line_is_valid_json(self):
        """Each line in the output file should be valid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            self.aggregator.export_jsonl(output_path)
            with open(output_path) as f:
                for i, line in enumerate(f):
                    obj = json.loads(line)
                    self.assertIsInstance(obj, dict)
                    self.assertIn('timestamp', obj)
                    self.assertIn('level', obj)
                    self.assertIn('service', obj)
                    self.assertIn('message', obj)
                    self.assertIn('format', obj)
        finally:
            os.unlink(output_path)

    def test_export_jsonl_content_correctness(self):
        """Verify exported JSONL content matches input entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            self.aggregator.export_jsonl(output_path)
            with open(output_path) as f:
                lines = f.readlines()

            # First entry: error level
            obj1 = json.loads(lines[0])
            self.assertEqual(obj1['level'], 'error')
            self.assertEqual(obj1['service'], 'backend')
            self.assertEqual(obj1['message'], 'Connection refused')

            # Second entry: info level
            obj2 = json.loads(lines[1])
            self.assertEqual(obj2['level'], 'info')
            self.assertEqual(obj2['service'], 'frontend')

            # Third entry: warn level
            obj3 = json.loads(lines[2])
            self.assertEqual(obj3['level'], 'warn')
            self.assertEqual(obj3['service'], 'market')
        finally:
            os.unlink(output_path)

    def test_export_jsonl_respects_max_entries(self):
        """export_jsonl should respect the max_entries limit."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            self.aggregator.export_jsonl(output_path, max_entries=2)
            with open(output_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)
        finally:
            os.unlink(output_path)

    def test_export_jsonl_empty_entries(self):
        """export_jsonl should handle empty entries gracefully."""
        empty_agg = LogAggregator()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            empty_agg.export_jsonl(output_path)
            with open(output_path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 0)
        finally:
            os.unlink(output_path)

    def test_export_jsonl_does_not_include_bulky_fields(self):
        """The bulky 'fields' dict should not appear in JSONL output."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name

        try:
            self.aggregator.export_jsonl(output_path)
            with open(output_path) as f:
                line = f.readline()
            obj = json.loads(line)
            self.assertNotIn('fields', obj)
        finally:
            os.unlink(output_path)

    def test_jsonl_format_via_main(self):
        """Test that --format jsonl is accepted by the argument parser."""
        from log_aggregator import parse_args
        import sys
        old_argv = sys.argv
        sys.argv = ['log_aggregator.py', '--input', 'test.log', '--format', 'jsonl', '--output', 'test.jsonl']
        try:
            args = parse_args()
            self.assertEqual(args.format, 'jsonl')
        finally:
            sys.argv = old_argv


if __name__ == '__main__':
    unittest.main()

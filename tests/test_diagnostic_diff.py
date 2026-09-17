"""Tests for tools/diagnostic_diff.py (Kickama #307)."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import diagnostic_diff


class DiagnosticDiffTests(unittest.TestCase):
    def setUp(self):
        self.report_a = {
            "commit": "aaaaaaaa",
            "passed": 2,
            "failed": 1,
            "modules": [
                {"name": "backend", "status": "PASS", "elapsed_seconds": 1.2, "artifact": "backend/target/debug/backend"},
                {"name": "frontend", "status": "PASS", "elapsed_seconds": 3.5, "artifact": "frontend/dist"},
                {"name": "frailbox", "status": "FAIL", "elapsed_seconds": 0.5, "artifact": None},
            ],
        }

        self.report_b = {
            "commit": "bbbbbbbb",
            "passed": 2,
            "failed": 1,
            "modules": [
                {"name": "backend", "status": "PASS", "elapsed_seconds": 2.8, "artifact": "backend/target/debug/backend"},
                {"name": "frontend", "status": "FAIL", "elapsed_seconds": 3.6, "artifact": None},
                {"name": "frailbox", "status": "PASS", "elapsed_seconds": 0.4, "artifact": "frailbox/frailbox"},
            ],
        }

    def test_diff_reports_identifies_regression_and_fix(self):
        diff = diagnostic_diff.diff_reports(self.report_a, self.report_b)
        self.assertEqual(diff["commit_before"], "aaaaaaaa")
        self.assertEqual(diff["commit_after"], "bbbbbbbb")
        self.assertEqual(diff["regressions"], ["frontend"])
        self.assertEqual(diff["fixes"], ["frailbox"])
        self.assertTrue(diff["has_regressions"])

    def test_elapsed_threshold_alerts(self):
        diff = diagnostic_diff.diff_reports(self.report_a, self.report_b, elapsed_threshold=1.0)
        self.assertIn("backend", diff["slowdowns"])
        backend_diff = next(m for m in diff["module_diffs"] if m["name"] == "backend")
        self.assertTrue(backend_diff["elapsed_alert"])
        self.assertEqual(backend_diff["elapsed_delta"], 1.6)

    def test_format_text_output(self):
        diff = diagnostic_diff.diff_reports(self.report_a, self.report_b)
        out = diagnostic_diff.format_text(diff)
        self.assertIn("Diagnostic Diff: aaaaaaaa -> bbbbbbbb", out)
        self.assertIn("frontend", out)
        self.assertIn("[REGRESSION]", out)
        self.assertIn("[FIXED]", out)

    def test_format_markdown_output(self):
        diff = diagnostic_diff.diff_reports(self.report_a, self.report_b)
        md = diagnostic_diff.format_markdown(diff)
        self.assertIn("## 📊 Diagnostic Diff", md)
        self.assertIn("| **`frontend`** |", md)
        self.assertIn("⚠️ **REGRESSION**", md)
        self.assertIn("🎉 **FIXED**", md)

    def test_cli_exit_code_on_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            p_a = Path(tmp) / "a.json"
            p_b = Path(tmp) / "b.json"
            p_a.write_text(json.dumps(self.report_a), encoding="utf-8")
            p_b.write_text(json.dumps(self.report_b), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = diagnostic_diff.main([str(p_a), str(p_b), "--format", "json"])
            self.assertEqual(code, 1)

            data = json.loads(buf.getvalue())
            self.assertTrue(data["has_regressions"])
            self.assertEqual(data["regressions"], ["frontend"])

    def test_cli_no_fail_on_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            p_a = Path(tmp) / "a.json"
            p_b = Path(tmp) / "b.json"
            p_a.write_text(json.dumps(self.report_a), encoding="utf-8")
            p_b.write_text(json.dumps(self.report_b), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = diagnostic_diff.main([str(p_a), str(p_b), "--no-fail-on-regression"])
            self.assertEqual(code, 0)

    def test_missing_file_handling(self):
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            code = diagnostic_diff.main(["non_existent_1.json", "non_existent_2.json"])
        self.assertEqual(code, 2)
        self.assertIn("Diagnostic report not found", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()

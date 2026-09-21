import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import diagnostic_diff


class DiagnosticDiffTests(unittest.TestCase):
    def setUp(self):
        self.before = {
            "commit": "old",
            "modules": [
                {"name": "api", "status": "PASS", "elapsed_seconds": 1.0, "artifact": "api-a"},
                {"name": "web", "status": "FAIL", "elapsed_seconds": 2.0},
            ],
        }
        self.after = {
            "commit": "new",
            "modules": [
                {"name": "api", "status": "FAIL", "elapsed_seconds": 2.5, "artifact": "api-b"},
                {"name": "worker", "status": "PASS", "elapsed_seconds": 0.5},
            ],
        }

    def write(self, folder, name, report):
        path = Path(folder) / name
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_reports_regressions_and_added_removed_modules(self):
        diff = diagnostic_diff.compare(self.before, self.after)
        self.assertEqual(diff["regressions"], ["api"])
        modules = {item["name"]: item for item in diff["modules"]}
        self.assertEqual(modules["web"]["after"], None)
        self.assertEqual(modules["worker"]["before"], None)

    def test_reports_time_and_artifact_changes(self):
        item = diagnostic_diff.compare(self.before, self.after)["modules"][0]
        self.assertEqual(item["elapsed_delta"], 1.5)
        self.assertTrue(item["artifact_changed"])

    def test_threshold_marks_slowdowns(self):
        diff = diagnostic_diff.compare(self.before, self.after, 1.0)
        self.assertEqual(diff["slowdowns"], ["api"])

    def test_markdown_contains_all_modules_and_notes(self):
        output = diagnostic_diff.markdown(diagnostic_diff.compare(self.before, self.after, 1.0))
        self.assertIn("| api | PASS → FAIL | +1.500s | regression, slowdown, artifact changed |", output)
        self.assertIn("| worker | missing → PASS | - | - |", output)

    def test_load_report_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "bad.json", [])
            with self.assertRaises(ValueError):
                diagnostic_diff.load_report(path)

    def test_cli_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            before = self.write(folder, "before.json", self.before)
            after = self.write(folder, "after.json", self.after)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = diagnostic_diff.main([str(before), str(after), "--format", "json"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(stdout.getvalue())["commit_after"], "new")

    def test_cli_returns_zero_without_regressions(self):
        clean = {"commit": "new", "modules": [{"name": "api", "status": "PASS"}]}
        with tempfile.TemporaryDirectory() as folder:
            before = self.write(folder, "before.json", clean)
            after = self.write(folder, "after.json", clean)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(diagnostic_diff.main([str(before), str(after)]), 0)

    def test_cli_file_error_exits_two(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                diagnostic_diff.main(["missing-a.json", "missing-b.json"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import diagnostic_diff


class DiagnosticDiffTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, payload: dict) -> Path:
        path = directory / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_compare_metadata_reports_added_removed_changed_fields(self):
        before = {
            "commit": "old",
            "removed_field": True,
            "modules": [{"name": "api", "status": "PASS", "elapsed_seconds": 1.0}],
        }
        after = {
            "commit": "new",
            "added_field": "present",
            "modules": [{"name": "api", "status": "PASS", "elapsed_seconds": 1.4}],
        }

        result = diagnostic_diff.compare_metadata(before, after)

        self.assertEqual(result["added"]["added_field"], "present")
        self.assertEqual(result["removed"]["removed_field"], True)
        self.assertEqual(result["changed"]["commit"], {"from": "old", "to": "new"})
        self.assertEqual(
            result["module_elapsed_changes"],
            [{"name": "api", "from": 1.0, "to": 1.4, "delta_seconds": 0.4}],
        )

    def test_load_metadata_rejects_empty_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text("", encoding="utf-8")

            with self.assertRaises(ValueError):
                diagnostic_diff.load_metadata(empty)

    def test_main_exits_nonzero_for_pass_to_fail_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            before = self.write_json(
                tmp_path,
                "before.json",
                {"modules": [{"name": "backend", "status": "PASS", "elapsed_seconds": 2.0}]},
            )
            after = self.write_json(
                tmp_path,
                "after.json",
                {"modules": [{"name": "backend", "status": "FAIL", "elapsed_seconds": 2.5}]},
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = diagnostic_diff.main([str(before), str(after)])

            self.assertEqual(exit_code, 1)
            output = json.loads(stdout.getvalue())
            self.assertTrue(output["has_regressions"])
            self.assertEqual(output["regressions"][0]["name"], "backend")


if __name__ == "__main__":
    unittest.main()

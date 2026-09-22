import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_script", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class DiagnosticArtifactTests(unittest.TestCase):
    def test_reports_created_files_without_running_git(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "build.json"
            second = Path(temp_dir) / "build.logd"
            first.write_text("{}")
            second.write_bytes(b"diagnostic")

            with patch.object(build, "ROOT", Path(temp_dir)):
                with patch.object(build, "run_text_process") as run:
                    with patch("builtins.print") as output:
                        result = build.report_diagnostic_artifacts([first, second])

            self.assertTrue(result)
            run.assert_not_called()
            text = "\n".join(" ".join(map(str, call.args)) for call in output.call_args_list)
            self.assertIn("build.json", text)
            self.assertIn("build.logd", text)
            self.assertIn("Add these files to your PR", text)

    def test_missing_artifacts_return_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.logd"
            with patch.object(build, "ROOT", Path(temp_dir)):
                self.assertFalse(build.report_diagnostic_artifacts([missing]))

    def test_generate_logd_does_not_run_git(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            diagnostic = root / "diagnostic"
            diagnostic.mkdir()
            metadata = diagnostic / "build-deadbeef.json"
            logd = diagnostic / "build-deadbeef.logd"

            with patch.object(build, "ROOT", root), patch.object(
                build, "DIAGNOSTIC_DIR", diagnostic
            ), patch.object(
                build, "diagnostic_paths_for_commit",
                return_value=(logd, metadata, "deadbeef"),
            ), patch.object(
                build, "get_encryptly_bin", return_value=None
            ), patch.object(
                build, "run_text_process"
            ) as run:
                result = build.generate_logd([])

            self.assertFalse(result)
            self.assertTrue(metadata.exists())
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

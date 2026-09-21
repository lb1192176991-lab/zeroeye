import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_script", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildCommandErrorTests(unittest.TestCase):
    def module(self, name="market"):
        return build.Module(
            name=name,
            language="test",
            dir=ROOT,
            build_cmd=["compiler", "build"],
            clean_cmd=["compiler", "clean"],
        )

    @patch.object(build, "run_text_process", side_effect=PermissionError(13, "Permission denied", "compiler"))
    def test_permission_error_becomes_module_failure(self, run):
        success, elapsed, output = build.build_module(self.module())

        self.assertFalse(success)
        self.assertGreaterEqual(elapsed, 0)
        self.assertIn("Could not run compiler", output)
        self.assertIn("Permission denied", output)

    @patch.object(build, "run_text_process", side_effect=OSError(8, "Exec format error", "compiler"))
    def test_other_os_error_becomes_module_failure(self, run):
        success, elapsed, output = build.build_module(self.module())

        self.assertFalse(success)
        self.assertGreaterEqual(elapsed, 0)
        self.assertIn("Exec format error", output)

    @patch.object(build, "run_text_process", side_effect=FileNotFoundError(2, "No such file", "compiler"))
    def test_missing_command_keeps_specific_message(self, run):
        success, elapsed, output = build.build_module(self.module())

        self.assertFalse(success)
        self.assertGreaterEqual(elapsed, 0)
        self.assertIn("Command not found", output)

    @patch.object(build, "run_text_process")
    def test_failed_process_still_returns_process_output(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["compiler", "build"], 1, stdout="stdout text", stderr="stderr text"
        )

        success, _, output = build.build_module(self.module())

        self.assertFalse(success)
        self.assertEqual(output, "stdout text\nstderr text")

    @patch.object(build, "run_text_process", side_effect=PermissionError(13, "Permission denied", "npm"))
    def test_frontend_install_permission_error_is_reported(self, run):
        module = self.module("frontend")
        module.dir = ROOT / "frontend"

        with patch.object(Path, "exists", return_value=False):
            success, _, output = build.build_module(module)

        self.assertFalse(success)
        self.assertIn("Could not run npm", output)


if __name__ == "__main__":
    unittest.main()

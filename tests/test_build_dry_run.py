"""Tests for build.py --dry-run planning mode."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build


class BuildDryRunTests(unittest.TestCase):
    def test_planned_build_commands_backend_debug(self):
        backend = next(m for m in build.MODULES if m.name == "backend")
        commands = build.planned_build_commands(backend, release=False)
        self.assertEqual(commands, [["cargo", "build"]])

    def test_planned_build_commands_backend_release(self):
        backend = next(m for m in build.MODULES if m.name == "backend")
        commands = build.planned_build_commands(backend, release=True)
        self.assertEqual(commands, [["cargo", "build", "--release"]])

    def test_planned_build_commands_engine_debug(self):
        engine = next(m for m in build.MODULES if m.name == "engine")
        commands = build.planned_build_commands(engine, release=False)
        self.assertEqual(
            commands,
            [
                ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Debug"],
                ["cmake", "--build", "build"],
            ],
        )

    def test_planned_build_commands_engine_release(self):
        engine = next(m for m in build.MODULES if m.name == "engine")
        commands = build.planned_build_commands(engine, release=True)
        self.assertEqual(commands[-1], ["cmake", "--build", "build", "--config", "Release"])

    def test_build_dry_run_plan_structure(self):
        selected = [m for m in build.MODULES if m.name in ("backend", "frontend")]
        plan = build.build_dry_run_plan(selected, release=False, clean=False)
        self.assertEqual(plan["action"], "build")
        self.assertFalse(plan["release"])
        self.assertEqual(plan["module_count"], 2)
        self.assertEqual(len(plan["modules"]), 2)
        self.assertIn("commit", plan)
        self.assertIn("diagnostic_metadata", plan)

    def test_build_dry_run_plan_clean_mode(self):
        backend = next(m for m in build.MODULES if m.name == "backend")
        plan = build.build_dry_run_plan([backend], release=False, clean=True)
        self.assertEqual(plan["action"], "clean")
        self.assertEqual(plan["modules"][0]["commands"], [backend.clean_cmd])

    @mock.patch("build.check_prerequisites", return_value=[])
    @mock.patch("build.current_commit_id", return_value="deadbeef")
    def test_main_dry_run_json_output(self, _commit, _prereq):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = build.main(["-m", "backend", "--dry-run", "--dry-run-format", "json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["action"], "build")
        self.assertEqual(payload["commit"], "deadbeef")
        self.assertEqual(payload["modules"][0]["name"], "backend")

    @mock.patch("build.check_prerequisites", return_value=[])
    @mock.patch("build.current_commit_id", return_value="cafebabe")
    def test_main_dry_run_text_mentions_no_side_effects(self, _commit, _prereq):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = build.main(["-m", "backend", "--dry-run"])
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Dry run", output)
        self.assertIn("No files changed", output)
        self.assertIn("cargo build", output)

    @mock.patch("build.check_prerequisites", return_value=[])
    @mock.patch("build.build_module")
    def test_dry_run_skips_build(self, mock_build, _prereq):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = build.main(["-m", "backend", "--dry-run"])
        self.assertEqual(exit_code, 0)
        mock_build.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Tests for build.py --dry-run planning mode (Kickama #306)."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

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
        self.assertEqual(
            commands,
            [
                ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"],
                ["cmake", "--build", "build", "--config", "Release"],
            ],
        )

    def test_build_dry_run_plan_structure(self):
        selected = [m for m in build.MODULES if m.name in ("backend", "frontend")]
        plan = build.build_dry_run_plan(selected, release=False, clean=False)
        self.assertEqual(plan["action"], "build")
        self.assertFalse(plan["release"])
        self.assertEqual(plan["module_count"], 2)
        self.assertEqual(len(plan["modules"]), 2)
        self.assertIn("commit", plan)
        self.assertIn("diagnostic_metadata", plan)
        self.assertTrue(plan["encryptly_preflight"])
        self.assertFalse(plan["side_effects"])

    def test_build_dry_run_plan_clean_mode(self):
        backend = next(m for m in build.MODULES if m.name == "backend")
        plan = build.build_dry_run_plan([backend], release=False, clean=True)
        self.assertEqual(plan["action"], "clean")
        self.assertTrue(plan["diagnostic_cleanup"])
        self.assertEqual(plan["modules"][0]["commands"], [backend.clean_cmd])

    def test_dry_run_json_output_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = build.main(["-m", "backend", "--dry-run", "--dry-run-format", "json"])
        self.assertEqual(ret, 0)
        output = buf.getvalue().strip()
        data = json.loads(output)
        self.assertEqual(data["action"], "build")
        self.assertEqual(len(data["modules"]), 1)
        self.assertEqual(data["modules"][0]["name"], "backend")
        self.assertEqual(data["modules"][0]["commands"], [["cargo", "build"]])

    def test_dry_run_text_output_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = build.main(["-m", "backend", "--dry-run"])
        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("Dry run: build plan", output)
        self.assertIn("backend:", output)
        self.assertIn("Dry run complete. No files changed.", output)

    def test_dry_run_no_side_effects(self):
        # Snapshot diagnostic directory before dry-run
        diag_dir = ROOT / "diagnostic"
        files_before = set(diag_dir.iterdir()) if diag_dir.exists() else set()

        buf = io.StringIO()
        with redirect_stdout(buf):
            build.main(["--dry-run", "--dry-run-format", "json"])
            build.main(["--clean", "--dry-run"])

        files_after = set(diag_dir.iterdir()) if diag_dir.exists() else set()
        self.assertEqual(files_before, files_after)


if __name__ == "__main__":
    unittest.main()

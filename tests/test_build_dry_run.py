import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build


class BuildDryRunTests(unittest.TestCase):
    def module(self, name):
        return next(module for module in build.MODULES if module.name == name)

    def test_frontend_plan_includes_conditional_install_and_environment(self):
        steps = build.build_steps(self.module("frontend"))
        self.assertEqual(steps[0]["command"], ["npm", "install"])
        self.assertEqual(steps[0]["when"], "node_modules is missing")
        self.assertEqual(steps[1]["environment"], {"NODE_ENV": "production"})

    def test_engine_release_plan_matches_real_two_step_build(self):
        steps = build.build_steps(self.module("engine"), release=True)
        self.assertEqual(steps[0]["command"][-1], "-DCMAKE_BUILD_TYPE=Release")
        self.assertEqual(steps[1]["command"], ["cmake", "--build", "build", "--config", "Release"])

    def test_backend_release_flag_is_reported(self):
        steps = build.build_steps(self.module("backend"), release=True)
        self.assertEqual(steps[0]["command"], ["cargo", "build", "--release"])

    @mock.patch("build.current_commit_id", return_value="deadbeef")
    def test_build_plan_reports_preflight_and_output_paths(self, _commit):
        plan = build.dry_run_plan([self.module("backend")], False, False)
        self.assertEqual(plan["before_build"], ["check prerequisites", "verify encryptly can create an archive"])
        self.assertIn("write diagnostic/build-deadbeef.json", plan["after_build"])
        self.assertFalse(plan["side_effects"])

    def test_clean_plan_reports_module_and_diagnostic_cleanup(self):
        plan = build.dry_run_plan([self.module("backend")], False, True)
        self.assertEqual(plan["modules"][0]["steps"][0]["command"], ["cargo", "clean"])
        self.assertIn("diagnostic/build-*.json", plan["also_removes"])
        self.assertNotIn("before_build", plan)

    @mock.patch("build.check_prerequisites")
    @mock.patch("build.diagnostic_paths_for_commit")
    @mock.patch("build.build_module")
    @mock.patch("build.clean_module")
    @mock.patch("build.check_encryptly_runs")
    def test_json_dry_run_has_no_mutating_or_preflight_calls(self, encryptly, clean, build_module, paths, prerequisites):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = build.main(["-m", "backend", "--dry-run", "--dry-run-format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["modules"][0]["name"], "backend")
        for call in (encryptly, clean, build_module, paths, prerequisites):
            call.assert_not_called()

    def test_unknown_module_still_fails_in_dry_run(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(["-m", "missing", "--dry-run"]), 1)

    def test_text_output_shows_conditions_and_no_side_effects(self):
        plan = build.dry_run_plan([self.module("frontend")], False, False)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            build.print_dry_run(plan, False)
        output = stdout.getvalue()
        self.assertIn("npm install [node_modules is missing]", output)
        self.assertIn("NODE_ENV=production", output)
        self.assertIn("No commands were run and no files were changed.", output)


if __name__ == "__main__":
    unittest.main()

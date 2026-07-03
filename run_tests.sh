#!/usr/bin/env bash
# Run build dry-run tests — Kickama bounty #4
set -euo pipefail
cd "$(dirname "$0")"
python -m unittest tests.test_build_dry_run -v
echo "OK: all dry-run tests passed"

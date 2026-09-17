#!/usr/bin/env bash
# Run diagnostic diff tool tests — Kickama bounty #5
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest tests.test_diagnostic_diff -v
echo "OK: all diagnostic diff tests passed"

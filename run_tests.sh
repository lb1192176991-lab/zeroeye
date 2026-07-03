#!/usr/bin/env bash
# Run deterministic seed tests — Kickama bounty #2 (PR #13)
set -euo pipefail
cd "$(dirname "$0")"
python -m unittest tests.test_data_generator_determinism -v
echo "OK: deterministic seed tests passed"

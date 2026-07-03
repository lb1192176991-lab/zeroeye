#!/usr/bin/env bash
# Run deterministic seed tests — Kickama bounty #2 (PR #13)
set -euo pipefail
cd "$(dirname "$0")"
python -m unittest discover -s tests -p "test_*.py" -v
echo "OK: deterministic seed tests passed"

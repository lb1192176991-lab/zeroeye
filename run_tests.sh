#!/usr/bin/env bash
# Run JSONL export tests — Kickama bounty #3 (PR #14)
set -euo pipefail
cd "$(dirname "$0")"
python -m unittest tests.test_log_aggregator_jsonl -v
echo "OK: JSONL export tests passed"

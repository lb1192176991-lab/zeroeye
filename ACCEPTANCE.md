# Acceptance checklist — Bounty #2 ($50)

- [x] `data_generator.py` — seeded RNG (`--seed`, default 42)
- [x] Same seed → identical JSON output across runs
- [x] Different seed → different data
- [x] CLI integration test (temp dir, byte-identical files)
- [x] Default seed constant (42) asserted in tests
- [x] Tests: `bash run_tests.sh` or `powershell -File run_tests.ps1` (6 cases)
- [x] Seed 0 + trades snapshot regression coverage

/claim #2 — PR ready for merge.

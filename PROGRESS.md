# PROGRESS.md — zeroeye

> 墨子 Harness · 自动生成于 2026-07-06

---

## ✅ 已完成

- Initialized墨子 Harness for https://github.com/lb1192176991-lab/zeroeye/issues/2.
- Identified non-deterministic helper functions in `tools/data_generator.py` that used the global `random` module instead of the seeded generator RNG.
- Routed email, phone, and datetime generation through the seeded RNG.
- Anchored tick and candle timestamps to a seeded base timestamp instead of wall-clock time.
- Added deterministic seed regression tests for users, orders, trades, ticks, and candles.
- Fixed `--format both` export handling so JSON and CSV outputs are both emitted.
- Harness commands passed:
  - `python3 -m py_compile tools/data_generator.py tools/test_data_generator.py`
  - `python3 -m unittest tools/test_data_generator.py`
  - `python3 -m py_compile tools/data_generator.py tools/test_data_generator.py`
  - `python3 build.py --module v2-market-stream`

---

## 🔄 进行中

- Preparing commit, push, and PR.

---

## 📋 待办

- Create fork branch and PR.

---

## ⚠️ 已知问题

- Initial `git clone` attempts timed out; source was downloaded via GitHub tarball, so git remote setup still needs recovery before PR creation.
- The broader `python3 build.py --module v2-market-stream,openapi-tools` gate failed because `luac` is not installed locally; the project README permits module-specific builds, so the active Harness build gate uses `v2-market-stream`.

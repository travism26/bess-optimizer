---
name: determinism-tests-exclude-wallclock-fields
description: Byte-identical determinism tests/output must exclude wall-clock fields like solve_time_seconds, per JSON writer
type: lesson
source_adw_ids: [27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-07-30
---

BacktestResult metrics (and any other result written to JSON) include `solve_time_seconds`, a wall-clock measurement that is never reproducible run to run. AC-style determinism tests (asserting two consecutive runs produce identical JSON) must exclude this field. Every place solve_time_seconds is embedded in a JSON file needs its own docstring/comment note near the write path stating it is the intentionally non-deterministic field: `bess backtest` got this note in M2b (closing an M1c review issue), but M2b's own `sweep()`/`_scalar_metrics` (src/bess/analytics/sweep.py) embeds solve_time_seconds again and was flagged missing the same note in review. Documenting it once on one command does not cover other commands/writers; check each new JSON-writing entry point individually when adding one.

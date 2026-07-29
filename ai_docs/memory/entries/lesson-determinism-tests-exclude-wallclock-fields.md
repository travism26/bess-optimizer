---
name: determinism-tests-exclude-wallclock-fields
description: Byte-identical determinism tests/output must exclude wall-clock fields like solve_time_seconds
type: lesson
source_adw_ids: [27b2b22d]
date: 2026-07-29
---

BacktestResult's metrics include `solve_time_seconds`, a wall-clock measurement that is never reproducible run to run. AC-4-style determinism tests (asserting two consecutive runs produce identical JSON) must exclude this field from the comparison; tests/test_backtest_integration.py does this correctly. However the on-disk metrics JSON written by `bess backtest` still embeds solve_time_seconds, so the literal files are NOT byte-identical, only the deterministic subset of fields is (flagged in M1c review as undocumented tech debt, not yet fixed). When adding any future timed/wall-clock field to a result written to disk, document near the write path (docstring or comment) that determinism applies to all fields except that one, so the gap between 'test-verified determinism' and 'byte-identical files on disk' doesn't get lost again.

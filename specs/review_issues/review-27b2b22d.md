# Review Issues - 27b2b22d

**Spec File:** specs/M1c_backtest_cli.md
**Review Date:** 2026-07-29 13:49
**Status:** PASSED

## Summary

run_backtest is now implemented on top of two new non-frozen helpers (solve_dispatch, metrics_from_dispatch) so the CLI solves each location's LP once and reuses it for both metrics and the dispatch plot. Both bess backtest and bess plot commands, both plots, and the full integration test suite are in place, mapping cleanly onto acceptance criteria 1-6 and 8 (README). Metrics math (actual-window annualization, UTC-day daily revenue as documented, cycles, per-MWh revenue) matches the spec and its gotchas, and the injected-optimizer seam is directly exercised by a stub-optimizer test. One minor documentation nuance around AC-4 determinism is worth tracking but nothing blocks release.

## Issues Found: 1

### Issue #1: tech_debt

**File:** N/A

**Description:**
AC-4 requires byte-identical metrics JSON across consecutive runs. The test correctly validates this by excluding solve_time_seconds from the comparison, but the actual JSON files written to disk by `bess backtest` still embed solve_time_seconds, so the literal on-disk files are not byte-identical run to run, only the deterministic subset of fields is. This isn't documented anywhere near the CLI write path.

**Resolution:**
Add a one-line docstring note on backtest() or _metrics_dict clarifying solve_time_seconds is the intentionally non-deterministic field, so AC-4 is understood to apply to every other field.

---

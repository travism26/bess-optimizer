# Review Issues - 325296bb

**Spec File:** specs/M2b_benchmarks.md
**Review Date:** 2026-07-30 16:55
**Status:** PASSED

## Summary

M2b's benchmark and sweep analytics are implemented per specs/M2b_benchmarks.md: pure TBk/capture-rate functions, pure sweep functions reusing M2a's day-slicing helpers, and Typer commands that own all JSON/plot I/O. All 10 acceptance criteria are covered by targeted tests (golden TB, DST TB, sanity-corridor capture rates, sweep monotonicity, determinism, missing-metrics graceful skip). Re-ran `bess backtest`/`benchmark`/`sweep` against the July 2023 fixture directly and every number in the README's M2 section matches the live output exactly. One skippable documentation gap found; no blockers.

## Issues Found: 1

### Issue #1: skippable

**File:** N/A

**Description:**
Spec item 6 asks for a docstring note, where metrics JSON is written, documenting solve_time_seconds as the sole non-deterministic field. That note exists on the backtest() command but sweep.json also embeds solve_time_seconds per variant (via sweep.py::_scalar_metrics), and neither sweep()'s docstring nor _scalar_metrics's docstring mentions it.

**Resolution:**
Add a one-line note to sweep()'s docstring (or _scalar_metrics's) stating solve_time_seconds is the intentionally non-deterministic field, mirroring backtest()'s note.

---

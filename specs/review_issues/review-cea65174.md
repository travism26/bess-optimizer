# Review Issues - cea65174

**Spec File:** specs/M2a_rolling_horizon.md
**Review Date:** 2026-07-30 13:17
**Status:** PASSED

## Summary

M2a rolling-horizon dispatch is fully implemented per specs/M2a_rolling_horizon.md: RollingConfig, run_backtest_rolling, and solve_rolling_dispatch match the master spec's frozen signatures and rolling mechanics exactly, with local-market-day windowing, persistence/perfect forecasting by local hour-of-day, SoC carry, and end-of-range truncation. All 10 acceptance criteria have direct passing tests (two-day foresight golden, equivalence golden, SoC continuity, dominance, committed-series integrity, DST windows, runtime budget, CLI, and determinism), and prior build/validate/test phases report ruff, mypy, and pytest all green with no M1 frozen interface touched. No blocking issues; two test-coverage gaps and one pre-existing infra-file note are flagged for follow-up.

## Issues Found: 3

### Issue #1: tech_debt

**File:** N/A

**Description:**
RollingConfig.lookahead_days > 1 combined with forecast="persistence" is implemented (each lookahead day reuses the commit day's own prices, not chained) but has zero test coverage; the master spec's mechanics text is also ambiguous for this combination.

**Resolution:**
Not required by the 10 stated acceptance criteria and not the config.toml default; add a golden or property test pinning multi-day persistence behavior before it is relied on in production.

---

### Issue #2: skippable

**File:** N/A

**Description:**
_persistence_forecast's handling of a DST-transition day as the source (commit) day is reachable via the spring-forward test's middle window, but that test uses a stub optimizer that ignores window contents, so the keep="first" dedup and ffill/bfill fallback branches are never asserted on actual price values.

**Resolution:**
Coverage gap only; the acceptance-criteria DST goldens both use a normal 24h day as the persistence source, which is what the spec requires. Consider a value-level assertion for a DST-day-as-source window later.

---

### Issue #3: skippable

**File:** N/A

**Description:**
The ADW worktree port-allocation file was modified on this branch during the research phase, unrelated to M2a scope, mirroring a note from a prior M1 slice review (review-3c648beb.md).

**Resolution:**
Not a code issue; flagging in case the document/ship phase is expected to untrack this file before merge.

---

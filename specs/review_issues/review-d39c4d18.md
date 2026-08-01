# Review Issues - d39c4d18

**Spec File:** specs/M3c_as_backtest_cli.md
**Review Date:** 2026-08-01 12:41
**Status:** PASSED

## Summary

M3c is fully implemented and matches specs/M3c_as_backtest_cli.md: run_backtest_as, the --ancillary CLI flag, the bess benchmark uplift/mix leg, the pure analytics helpers, and the README M3 section are all present and wired correctly. I manually re-ran the CLI against the committed July 2023 fixture and reproduced the exact README numbers (2.7705x uplift, $970,937.15 energy-only vs $2,689,961.68 co-optimized, per-product mix), plus the gap-raise, pre-launch-ECRS-mask, and rolling+ancillary-guard paths, all working as specified. Two minor non-blocking issues found (a redundant cache read and an unguarded division), documented in specs/review_issues/review-d39c4d18.md.

## Issues Found: 2

### Issue #1: tech_debt

**File:** N/A

**Description:**
When --ancillary is active, the backtest command re-fetches prices_df via fetch_da_prices a second time per location purely for run_backtest_as, even though _run_location already loaded the identical cached parquet a few lines earlier. Correct but redundant I/O.

**Resolution:**
Thread the already-loaded prices_df through instead of re-fetching. Not required for this milestone; worth cleaning up if --ancillary usage grows.

---

### Issue #2: skippable

**File:** N/A

**Description:**
revenue_mix divides by sum(revenue_by_product.values()) with no zero-guard. A backtest window with exactly $0 total AS revenue across all products (a plausible LP-degeneracy edge case the spec itself calls out) would raise ZeroDivisionError inside bess benchmark instead of skipping cleanly. Not reachable on the current committed fixtures.

**Resolution:**
Guard the zero-total case to return an all-zero/NaN mix, or explicitly document why this scenario should raise rather than skip.

---

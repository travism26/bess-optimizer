# Review Issues - 3c648beb

**Spec File:** specs/M1a_data_layer.md
**Review Date:** 2026-07-29 11:23
**Status:** PASSED

## Summary

The M1a data layer is fully implemented: fetch_da_prices, canonicalization, hard validation, parquet caching, and the bess fetch CLI all match specs/M1a_data_layer.md. All 8 acceptance criteria have direct, passing tests, including committed DST fixtures for both 2023 transitions, gap detection, dedup/sort, negative-price passthrough, gridstatus import confinement, and cache round-tripping. Prior build/validate/test phases confirm ruff, mypy, and pytest are green (11 passed, 1 manual deselected), and the manual live-fetch test against the real ERCOT API also passed during build. No blocking issues; a few tech_debt/skippable items are noted for cleanup.

## Issues Found: 4

### Issue #1: tech_debt

**File:** N/A

**Description:**
_fetch_raw downloads and parses the full yearly ERCOT DAM archive (all hubs) per call; since fetch_da_prices is invoked once per location, a bess fetch run over the default 3-location config re-downloads and re-parses the same yearly zip files 3 times instead of once.

**Resolution:**
Not required for M1a acceptance; all criteria pass. Consider sharing/caching the per-year raw fetch across locations in a later milestone if network cost becomes a concern.

---

### Issue #2: tech_debt

**File:** N/A

**Description:**
No automated test exercises the Typer `fetch` command itself (e.g. via CliRunner); only bess.data.prices internals are tested. A regression in config parsing or flag/config precedence would not be caught by CI.

**Resolution:**
Not blocking: spec's Implements list only names tests/test_data.py, and the command was manually verified against the live API during build. Consider a CliRunner test in a later milestone.

---

### Issue #3: skippable

**File:** N/A

**Description:**
Stale scaffold TODO comments remain directly above the tests that now implement them, reading as outstanding work even though each is fully covered.

**Resolution:**
Cosmetic only; delete the stale TODO comments in a follow-up cleanup pass.

---

### Issue #4: skippable

**File:** N/A

**Description:**
ADW worktree port-allocation file was committed to this branch during the research phase; unrelated to M1a scope. Other worktrees show a later pipeline step untracking this file before finalizing, which hasn't happened here yet.

**Resolution:**
Not a code issue; flagging in case the document/ship phase is expected to untrack it before merge.

---

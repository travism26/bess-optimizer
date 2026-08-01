# AS Clearing-Price Data Layer

**ADW ID:** 6f498150
**Date:** 2026-08-01
**Specification:** specs/M3a_as_data_layer.md

## Overview

Adds `src/bess/data/as_prices.py`, which fetches, canonicalizes, validates, and
parquet-caches ERCOT day-ahead ancillary-service clearing prices (MCPCs) for
REG_UP, REG_DOWN, RRS, ECRS, and NONSPIN, with the same UTC-first, fail-loud
rigor as the M1a energy price layer. `bess fetch` now pulls both energy and AS
prices in one invocation.

## What Was Built

- `fetch_as_prices(start, end, cache_dir) -> pd.DataFrame`: the public entry
  point, serving from a parquet cache when present and fetching via
  gridstatus otherwise.
- Canonical long-format AS schema (one row per interval per product, no
  location column since MCPCs are system-wide).
- Per-product gap validation with an ECRS launch-date carve-out (2023-06-10):
  absence before launch is structural, not a gap.
- Explicit, exhaustive mapping from gridstatus's raw MIS column names (e.g.
  `REGUP`, `REGDN`, `NSPIN`) to canonical product names, raising on any
  unrecognized column instead of passing it through.
- `bess fetch` extended to also pull the AS window once per invocation
  (not once per hub, since MCPCs are system-wide).
- Fixtures: `tests/fixtures/as_mcpc_2023_07.parquet` (full July 2023, all
  five products), plus raw DST-transition samples for 2023-03-12 (23-hour
  day, pre-ECRS) and 2023-11-05 (25-hour day, all five products).
- `tests/test_as_data.py` covering all 8 acceptance criteria from the spec.
- The gridstatus import-confinement guard in `tests/test_data.py` extended
  to allow `data/as_prices.py` alongside `data/prices.py`.

## Technical Implementation

### Files Modified

- `src/bess/data/as_prices.py`: new module; fetch, canonicalize, validate,
  and cache AS MCPCs.
- `src/bess/cli.py`: `bess fetch` now also calls `fetch_as_prices` once per
  invocation and reports the row count.
- `tests/test_as_data.py`: new test suite for the AS data layer.
- `tests/test_data.py`: import-confinement guard now allows two modules
  instead of one.
- `tests/test_smoke.py`: added `bess.data.as_prices` to the import smoke
  test.
- `tests/fixtures/as_mcpc_2023_07.parquet`,
  `tests/fixtures/as_2023_03_12_raw.parquet`,
  `tests/fixtures/as_2023_11_05_raw.parquet`: committed fixtures generated
  from a single real fetch during the build.

### Key Changes

- **Report choice deviates from the spec's two named methods.** The spec
  called out `Ercot.get_as_prices` (primary) and `get_mcpc_dam` (fallback) as
  candidates. Research during the build found both read MIS report 12329,
  whose live document list retains only about a month of history and cannot
  serve the 2023-2024 window this project targets. `as_prices.py` instead
  pulls yearly zips from MIS report 13091 ("Historical DAM Ancillary Service
  MCPCs", `HISTORICAL_DAM_AS_MCPC_RTID = 13091`) via the same
  `Ercot._get_document` plumbing `get_dam_spp(year)` uses for energy prices.
  This mirrors the M1a lesson that `get_spp` was unreliable for historical
  energy prices, one level deeper for AS.
- **Structural absence vs. genuine gap.** `_canonicalize` drops NaN prices
  (which is what makes ECRS rows disappear entirely before its launch);
  `_validate` then only expects each product from the later of the requested
  start and that product's launch date (`_PRODUCT_LAUNCH`), so a pre-launch
  absence never raises, but a genuine missing hour for a live product does,
  listing every missing `(product, interval)` pair.
  ECRS_LAUNCH remains a named constant.
- **Deterministic dedup.** Rows are sorted by
  `(interval_start_utc, product)` with `kind="stable"` before
  `drop_duplicates(..., keep="first")`, so if a duplicate `(product,
  interval)` pair ever appears, which copy survives is determined by
  original input order, not sort instability.
- **Explicit product mapping.** `_PRODUCT_MAP` translates gridstatus's raw
  column names (`REGDN`, `REGUP`, `RRS`, `NSPIN`, `ECRS`, post whitespace
  strip) to canonical names; any other column raises `ValueError` rather
  than being silently included or dropped.
- **Fetch once, not per hub.** Unlike `fetch_da_prices`, which is called
  once per configured location, `fetch_as_prices` is called once per `bess
  fetch` invocation because MCPCs are system-wide.

## Usage

```bash
uv run bess fetch --config config.toml      # pulls DA hub prices AND AS MCPCs (network, manual only)
uv run bess backtest --config config.toml   # metrics JSON + plots from cache (no network)
uv run bess plot                            # re-render PNGs from a backtest output
```

```python
from datetime import date
from pathlib import Path
from bess.data.as_prices import fetch_as_prices

df = fetch_as_prices(date(2023, 7, 1), date(2023, 7, 31), Path("data/cache"))
# columns: interval_start_utc, interval_end_utc, iso, market, product, price
```

## Configuration

No new configuration surface. `fetch_as_prices` reuses the same
`--start` / `--end` / `--cache-dir` options as `bess fetch` for energy
prices; there is no per-location option since AS MCPCs are system-wide.

## Testing

```bash
uv run pytest                          # full suite, fixtures only, no network
uv run pytest tests/test_as_data.py    # AS data layer tests only
uv run pytest -m manual tests/test_as_data.py  # live gridstatus fetch, manual only
```

## Notes

- Out of scope for this milestone: the AS co-optimization LP (M3b), backtest
  and CLI integration beyond `bess fetch` (M3c), AS demand curves,
  deployment factors, and real-time MCPCs.
- `.ports.env` in this branch's diff is unrelated worktree leakage flagged in
  `specs/review_issues/review-6f498150.md`; it should be restored to
  `origin/main` before merging and is not part of this feature.

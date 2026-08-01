# ADW Feature Spec: M3a, AS Clearing-Price Data Layer

- **Repo:** bess-optimizer
- **Master spec:** specs/M3_ancillary_services.md (schema and launch rules live there; on any conflict the master wins)
- **Depends on:** M2 merged. Independent of M3b.
- **Implements:** src/bess/data/as_prices.py, the AS leg of `bess fetch`, tests/test_as_data.py, fixtures

## Objective

Ingest ERCOT DAM ancillary-service clearing prices (MCPCs) for REG_UP,
REG_DOWN, RRS, ECRS, and NONSPIN into the canonical AS schema with the same
rigor as the M1a energy layer: UTC-first, validated, cached, fail-loud, and
frozen into fixtures so everything downstream runs offline.

## In scope

1. `src/bess/data/as_prices.py` with `fetch_as_prices(start, end,
   cache_dir) -> pd.DataFrame`, canonical AS schema exactly per the master.
   All gridstatus calls confined to this module (extend the AST-based
   import-confinement guard to cover it; memory:
   ast-based-import-confinement-guard).
2. Validation: per product, strictly increasing interval_start_utc, no
   duplicates, no gaps within the product's validation window; the window
   starts at the later of the requested start and the product's launch
   (ECRS: 2023-06-10, a named constant). Failures list the missing
   (product, interval) pairs.
3. Parquet cache under cache_dir, one file per (start, end) window,
   filename pattern consistent with the energy cache.
4. `bess fetch` extended to also pull AS prices for the configured window
   (system-wide, once, not per hub). Network stays exclusively behind
   `bess fetch` and pytest.mark.manual tests (memory:
   network-test-marker-convention).
5. Fixtures, generated once via a real fetch during the build (same
   procedure as M1a, network for that single step only):
   - `tests/fixtures/as_mcpc_2023_07.parquet`: full July 2023, all five
     products live.
   - Raw DST samples for 2023-03-12 (23-hour day, pre-ECRS: four products)
     and 2023-11-05 (25-hour day, five products), matching the M1a raw
     sample convention.
6. `tests/test_as_data.py` covering the acceptance criteria below.

## Out of scope

The co-optimization LP (M3b), backtest and CLI integration beyond the fetch
command (M3c), AS demand curves, deployment factors, real-time MCPCs,
any change to the energy data layer.

## Acceptance criteria

1. **Schema round trip:** the July fixture loads with exactly the canonical
   AS columns and dtypes (UTC microsecond timestamps, float64 price), five
   products, each sorted, deduplicated, strictly increasing.
2. **Row counts:** July 2023 has 744 hourly intervals; the fixture has
   744 x 5 rows, and per-product counts are all 744.
3. **DST days:** from the raw samples, 2023-03-12 yields 23 rows per
   available product and 2023-11-05 yields 25 per product, after UTC
   conversion. Never 24.
4. **ECRS launch rule:** requesting a window starting 2023-01-01 validates
   ECRS only from 2023-06-10; the 2023-03-12 sample contains no ECRS rows
   and validation still passes. A genuinely missing mid-window hour for any
   live product raises listing the exact (product, interval) pairs.
5. **No silent fill:** gap handling never interpolates or fabricates rows;
   the error path is tested with a doctored frame.
6. **Cache behavior:** a second `fetch_as_prices` call over the same window
   is served from parquet with no gridstatus call (assert via the same
   technique the M1a cache test uses).
7. **Negative and zero MCPCs:** zero prices are common and pass through
   untouched; no clipping, no sign filtering (same philosophy as energy
   gotcha 3).
8. **No network in CI:** everything above runs from fixtures; live-fetch
   tests carry pytest.mark.manual and are excluded by default.

## Gotchas

1. `Ercot.get_as_prices(date, end)` is the primary call in the pinned
   gridstatus 0.36.0, `get_mcpc_dam` the fallback. Verify during research
   which one serves 2023-2024 history reliably; the M1a experience
   (get_spp unreliable, get_dam_spp(year) required) says do not trust the
   obvious method name. Watch per-location redownload behavior too
   (memory: fetch-da-prices-per-location-redownload does not apply here,
   MCPCs are system-wide, fetch once).
2. gridstatus product naming differs from our canonical names (for example
   "Regulation Up" or "REGUP" vs "REG_UP"); map explicitly, fail on
   unknown products rather than passing them through.
3. ERCOT publishes in prevailing Central Time: convert to UTC immediately,
   same as M1a, and reuse its helpers rather than duplicating them.

## Definition of done

All 8 criteria green in CI, ruff and mypy clean, fixtures committed and
small (the July file should be well under 100 KB), the import-confinement
guard covers as_prices.py, no change to any frozen interface.

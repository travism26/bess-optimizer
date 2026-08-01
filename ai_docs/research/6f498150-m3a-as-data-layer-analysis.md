# Research: M3a AS Clearing-Price Data Layer (ERCOT DAM MCPC ingestion)

## Metadata

adw_id: `6f498150`
prompt: `specs/M3a_as_data_layer.md`
date: `2026-08-01`

## Executive Summary

M3a is an additive slice with the same shape as M1a: one new module
(`src/bess/data/as_prices.py`), one new test file, three new fixtures, a small
extension to `bess fetch`, and one edit to an existing test (the AST
import-confinement guard, which today allows gridstatus in `data/prices.py`
only). No frozen interface changes, no touch to the energy data layer.

The decisive finding is in gridstatus, not in this repo, and it repeats the M1a
lesson one step further. **Both** methods the spec names, `Ercot.get_as_prices`
and `Ercot.get_mcpc_dam`, read ERCOT MIS report 12329 (NP4-188-CD), whose
document list was verified live during this research to retain only about 31
days (62 documents, 2026-07-01 through 2026-07-31, csv + xml per day). Neither
can serve 2023-2024, and gridstatus 0.36.0 ships **no** yearly-archive method for
AS prices (the `get_dam_spp(year)` analog does not exist). The working path,
found and verified end to end during this research, is **MIS report type
13091, "Historical DAM Ancillary Service MCPCs"**: yearly zips
(`DAMASMCPC_2023.zip`, `DAMASMCPC_2024.zip`, back to 2010), reachable with the
same `Ercot._get_document(report_type_id=..., constructed_name_contains=f"{year}.zip")`
plumbing `get_dam_spp` uses. Every M3a acceptance criterion was checked against
the real 2023 file: July has 744 hours x 5 products, 2023-03-12 gives 23 rows
per product across 4 products (no ECRS), 2023-11-05 gives 25 per product across
5, ECRS starts exactly 2023-06-10 00:00 CT, and a canonical July parquet weighs
32 KB.

The third finding is a small trap that will silently break dtype and row-count
assertions: the archive is **wide, not long** (one row per hour, one column per
product), its `REGUP ` header **carries a trailing space in both 2023 and
2024**, and product codes are `REGDN/REGUP/RRS/NSPIN/ECRS`, none of which match
the canonical `REG_DOWN/REG_UP/RRS/NONSPIN/ECRS`.

## Existing Architecture

### Relevant Documentation Found

| Document | What it contributes to M3a |
| -------- | -------------------------- |
| `specs/M3_ancillary_services.md` | Master. Frozen `fetch_as_prices` signature, canonical AS schema (long format, no location column, market `DAM_AS`), the ECRS-launch validation rule, gotcha 1 (verify the gridstatus AS call), gotcha 5 (DST applies to AS too). Wins on conflict. |
| `specs/M3a_as_data_layer.md` | The task spec: 6 in-scope items, 8 acceptance criteria, 3 gotchas, definition of done (July fixture "well under 100 KB", guard extended). |
| `specs/M3b_as_cooptimizer.md`, `specs/M3c_as_backtest_cli.md` | Downstream consumers of the fixtures this slice commits. M3b property tests run on `tests/fixtures/as_mcpc_2023_07.parquet`; M3c builds the wide (P, T) matrices from the long frame. |
| `specs/M1a_data_layer.md` + `ai_docs/research/3c648beb-m1a-data-layer-analysis.md` | The template this slice mirrors: four-piece module structure, raw DST samples, cache test technique, manual live-fetch test. |
| `specs/TASKS.md` | T6, depends on M2 merged only, independent of T7. Explicitly instructs verifying `get_as_prices` vs `get_mcpc_dam` during research. |
| `CLAUDE.md` | Frozen interfaces, canonical schema, gotchas (DST 23/25 hours, negative prices are data), no network in tests, no em-dashes, no AI-attribution trailer. |
| `ai_docs/memory/MEMORY.md` + `entries/` | 13 entries; 5 bear directly on this slice (see "Existing Patterns"). |
| `app_docs/feature-3c648beb-data-layer.md` | The per-feature doc pattern the document phase will follow for M3a. |
| `README.md` | Sections: Scope note, Quick start, Architecture, Results, M2 results, License. M3a itself adds no README section (M3c owns the M3 section), but the Quick start's `bess fetch` line now also pulls AS. |

No architecture diagrams exist; the component maps in the research docs are the
closest thing.

### Component Map

```
config.toml (locations, start, end, cache_dir)
      │
      ▼
src/bess/cli.py :: fetch()                      <- M3a extends
      ├─ per location ─► bess.data.prices.fetch_da_prices   (unchanged)
      └─ ONCE, system-wide ─► bess.data.as_prices.fetch_as_prices   <- M3a adds
                                    │
                                    ├─ _fetch_raw(year)  MIS 13091 yearly zip  <- only gridstatus call
                                    ├─ _canonicalize()   wide -> long, CT -> UTC, rename products
                                    ├─ _validate()       per product: dtypes, sorted, unique, gap-free
                                    │                    within max(start, launch) .. end
                                    └─ parquet cache     cache_dir/<pattern>_{start}_{end}.parquet
                                    │
                                    ▼
                        canonical long AS DataFrame
                                    │
      ┌─────────────────────────────┴──────────────────────────────┐
      ▼                                                            ▼
tests/fixtures/as_mcpc_2023_07.parquet                  (M3c) run_backtest_as
tests/fixtures/as_2023_03_12_raw.parquet                  builds (P, T) matrices
tests/fixtures/as_2023_11_05_raw.parquet                  ▼
                                                        (M3b) optimize_dispatch_as
```

Nothing downstream exists yet: `optimize_dispatch_as` (T7) and
`run_backtest_as` (T8) are unwritten. M3a's only outward contract is the
canonical frame plus the three fixture files.

### Key Files and Modules

| File | State | Relevance |
| ---- | ----- | --------- |
| `src/bess/data/prices.py` | Complete, 181 lines. `_fetch_raw` / `_canonicalize` / `_validate` / `_cache_path` / `fetch_da_prices`. | The structural template. `_CENTRAL_TZ = "US/Central"`, `_ISO = "ERCOT"`, `CANONICAL_COLUMNS`. Untouched by M3a. |
| `src/bess/data/as_prices.py` | **Does not exist.** | The whole slice. |
| `src/bess/cli.py` | Complete, 449 lines, 5 commands. `fetch()` loops `settings["locations"]`. | Gains the AS leg in `fetch()`. |
| `tests/test_data.py` | Complete, 239 lines, includes `_imports_gridstatus` AST guard and the cache-hit test. | `test_gridstatus_import_confined_to_prices_module` must learn about `as_prices.py`. |
| `tests/test_as_data.py` | **Does not exist.** | New, mirrors `test_data.py`. |
| `tests/conftest.py` | Autouse `block_network`, marker-aware (`manual` exempt). | Works unchanged for the new tests. |
| `tests/fixtures/` | `hb_north_2023_07.parquet`, plus two raw DST samples. | Three AS files join them. |
| `config.toml` | `start = 2023-01-01`, `end = 2024-12-31`, no `[ancillary]` table yet. | The master's `[ancillary]` table belongs to M3b/M3c; M3a needs no config change. |
| `pyproject.toml` | `gridstatus==0.36.0`, `manual` marker registered, `addopts = "-q -m 'not manual'"`, mypy strict-ish, ruff line-length 100. | No change needed. |
| `src/bess/backtest/rolling.py` | `_MARKET_TZ = "America/Chicago"`, `_local_market_day`, `_local_hour_of_day`, `_day_blocks`. | Master gotcha 5 points here for M3c day slicing, not M3a. Note the tz string differs from `prices.py`'s `US/Central` (same zone, two spellings). |
| `.gitignore` | `*.parquet` ignored with `!tests/fixtures/*.parquet`. | New fixtures commit with no gitignore edit. |

## Affected Areas

### Files That Will Need Changes

| File | Change | Driven by |
| ---- | ------ | --------- |
| `src/bess/data/as_prices.py` | New. `AS_CANONICAL_COLUMNS`, `ECRS_LAUNCH = date(2023, 6, 10)`, `_PRODUCT_MAP`, `_fetch_raw`, `_canonicalize`, `_validate`, `_cache_path`, `fetch_as_prices`. | Spec items 1-3 |
| `src/bess/cli.py` | `fetch()` calls `fetch_as_prices(start, end, cache_dir)` once after the location loop and echoes a row count. Docstring updated (it currently says the command fetches "DA hub prices"). | Spec item 4 |
| `tests/test_data.py` | Extend `test_gridstatus_import_confined_to_prices_module` to an allowlist of two modules (rename it accordingly), keeping the AST walk. | Spec item 1, memory: ast-based-import-confinement-guard |
| `tests/test_as_data.py` | New. AC 1-8. | Spec item 6 |
| `tests/fixtures/as_mcpc_2023_07.parquet` | New, ~32 KB measured. | Spec item 5, AC 1-2 |
| `tests/fixtures/as_2023_03_12_raw.parquet` | New, ~5.6 KB measured (23 rows, wide, 4 live products). | Spec item 5, AC 3-4 |
| `tests/fixtures/as_2023_11_05_raw.parquet` | New, ~5.7 KB measured (25 rows, wide, includes the `Repeated Hour Flag = Y` row). | Spec item 5, AC 3 |
| `README.md` | Optional one-line note that `bess fetch` now also pulls AS MCPCs. The M3 section itself is M3c's. | - |

### Dependencies

**`as_prices.py` will depend on:** `gridstatus==0.36.0` (`Ercot._get_document`,
`Ercot.parse_doc`, `gridstatus.utils.get_zip_file`), `pandas`, `pyarrow`,
stdlib `datetime`/`pathlib`/`logging`. Nothing from `bess.*` is strictly
required; sharing `prices.py`'s tz constant is a judgment call (see
Recommendations).

**What will depend on `as_prices.py`:** `cli.py::fetch` (this slice), then
`run_backtest_as` and `bess backtest --ancillary` in M3c. `tests/test_smoke.py`
imports every module by name and should gain `bess.data.as_prices`.

**Fixture consumers:** M3b property tests and M3c CLI tests both name
`tests/fixtures/as_mcpc_2023_07.parquet`. Its column names, product spellings,
and row ordering are a cross-task contract; changing them later is a
three-slice change.

### Integration Points

1. **MIS 13091 raw columns -> canonical.** Verified against the real file:
   `Delivery Date` (MM/DD/YYYY), `Hour Ending` (`01:00` .. `24:00`),
   `Repeated Hour Flag` (Y/N), then wide float columns `REGDN`, `REGUP `
   (trailing space), `RRS`, `NSPIN`, `ECRS`. After
   `Ercot.parse_doc(raw)` the frame is `Time`, `Interval Start`,
   `Interval End` (tz-aware `US/Central`) plus the product columns; melt to
   long, drop NaN (pre-launch ECRS only), map product names, `tz_convert("UTC")`,
   cast to `datetime64[us, UTC]`.
2. **`parse_doc` does the DST work already.** It renames
   `Repeated Hour Flag -> DSTFlag`, derives `ambiguous` from it
   (`ambiguous_based_on_dstflag`: `Y` means standard time), computes
   `Interval Start = Delivery Date + (HourEnding - 1)`, localizes to Central,
   and falls back an hour on `NonExistentTimeError`. Spring forward needs no
   special case here because the file simply omits HE 03:00 on 2023-03-12.
3. **Cache <-> tests.** AC-6 reuses M1a's technique: copy the fixture to
   `_cache_path(tmp_path, start, end)`, call twice, let the autouse socket
   guard prove no network. So `_cache_path` must be importable and
   deterministic, exactly like `prices._cache_path`.
4. **`bess fetch` -> both layers.** Energy is per location; AS is system-wide
   and must be fetched once per invocation, not once per hub.

## Impact Analysis

### Scope of Change

Small, additive, low risk: one ~200-line module, one ~250-line test file, three
committed fixtures, roughly ten lines in `cli.py`, and a one-line allowlist
change in an existing test. No existing behavior changes. The only shared file
with in-flight work is `tests/test_data.py`, and only in the guard test. T7
(M3b) touches disjoint files.

### Risks and Considerations

1. **The spec's two named methods both fail for 2023-2024 (verified live).**
   `Ercot.get_as_prices` (ercot.py:2048) calls `_get_document(report_type_id=DAM_CLEARING_PRICES_FOR_CAPACITY_RTID=12329)`
   for `date - 1 day`; `Ercot.get_mcpc_dam` (ercot.py:2095) calls `_get_documents`
   on the same report with a publish-date range. A live query of
   `https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=12329`
   returned 62 documents spanning 2026-07-01 to 2026-07-31 only. `get_as_prices`
   would raise `ValueError` from `max()` on an empty list; `get_mcpc_dam` raises
   `NoDataFoundException` in `_handle_mcpc_dam_df`. Loud, but useless for the
   target window. **Do not build on either.**
2. **`ErcotAPI` is a dead end for this repo.** `gridstatus.ercot_api.ErcotAPI`
   does serve the same product with real history
   (`AS_PRICES_ENDPOINT = "/np4-188-cd/dam_clear_price_for_cap"`), but its
   constructor raises unless `ERCOT_API_USERNAME`, `ERCOT_API_PASSWORD`, and a
   subscription key are set. That conflicts with "never commit secrets" and with
   a fixture step any contributor can rerun. `https://data.ercot.com/data-product-archive/NP4-188-CD`
   also 302s to a login. Rejected.
3. **Use MIS report 13091 (the verified path).** Yearly zips named
   `DAMASMCPC_{year}.zip`, 17 of them (2010-2026), 2023 = 90 KB zipped, 2024 =
   82 KB. Each contains a single CSV, so
   `pd.read_csv(gridstatus.utils.get_zip_file(doc_info.url))` works directly
   (unlike `get_dam_spp`, which reads a multi-sheet workbook). The call is
   `Ercot()._get_document(report_type_id=13091, constructed_name_contains=f"{year}.zip")`.
   Define the RTID as a named module constant; gridstatus 0.36.0 has no name for
   it. **Caveat:** `_get_document` is a private helper, so this is a slightly
   deeper reach into gridstatus than `get_dam_spp(year)` was. Keeping it inside
   `_fetch_raw` preserves the "one-function fix" property, and the
   `pytest.mark.manual` live test is what will catch an upstream break.
4. **`REGUP ` has a trailing space, in both 2023 and 2024.** `parse_doc` does
   not strip column names (only `_finalize_as_price_df` does, and that path is
   not in play). Strip all column names immediately after `read_csv`, before
   anything else, or the melt silently drops REG_UP and the row count comes out
   744 x 4.
5. **Wide, not long.** One row per hour with five product columns. The melt is
   ours to write. `dropna` on the value column is what implements the
   "structural absence" rule: pre-launch ECRS is NaN (3839 NaN hours in 2023 =
   160 days x 24 - 1 for spring forward). A genuine mid-window hole in a live
   product would also be dropped by `dropna`, which is fine and intended:
   `_validate` then re-detects it as a missing `(product, interval)` pair and
   raises. Say this in a comment; it looks like a silent-fill bug otherwise.
6. **Product name mapping is not one-to-one with any gridstatus constant.**
   Archive codes are `REGDN, REGUP, RRS, NSPIN, ECRS`; canonical names are
   `REG_DOWN, REG_UP, RRS, NONSPIN, ECRS`. gridstatus's own long-format path
   uses yet another spelling ("Regulation Up", "Non-Spinning Reserves"). Map
   explicitly from a dict and **raise on any unmapped column**, per spec gotcha
   2; do not pass unknown columns through.
7. **Central-day windowing must be done by date arithmetic, not `Timedelta`.**
   `pd.Timestamp(end + timedelta(days=1), tz="US/Central")` (what `prices.py`
   already does) is correct. `pd.Timestamp(day, tz=...) + pd.Timedelta(days=1)`
   adds 24 absolute hours and lands an hour off on both DST days: during this
   research that mistake turned 23/25-row days into 24/24, exactly the failure
   AC-3 exists to catch. Reuse M1a's idiom verbatim.
8. **Per-product gap validation with a per-product lower bound.** Build the
   expected hourly index in UTC (never in Central; same reasoning as M1a), from
   `max(requested_start_utc, launch_start_utc)` to the window end, and diff it
   per product group. `ECRS_LAUNCH = date(2023, 6, 10)` maps to
   `2023-06-10 00:00 CT = 05:00 UTC`; ECRS's first archive row is exactly that
   timestamp (verified). Decide and document what happens when a window ends
   before a product's launch: zero rows for that product should pass, not fail.
9. **Zero MCPCs exist; negatives do not (in 2023-2024).** 9 zero REGUP hours in
   2023, 31 in 2024, no negatives in either year. July 2023 has **no** zeros
   (mins: REGDN 0.01, REGUP 0.80, RRS 1.00, NSPIN 0.25, ECRS 0.08), so AC-7's
   zero/negative pass-through test must use a synthetic or doctored frame, not
   the July fixture. That matches how M1a tested negative energy prices.
10. **Microsecond timestamp precision.** Same trap as M1a: cast both timestamp
    columns to `datetime64[us, UTC]` before writing parquet, or the dtype
    assertion fails after the round trip. `parse_doc` returns `ns`-precision
    Central timestamps.
11. **Fixture sizes are comfortable.** A canonical July frame (3720 rows,
    6 columns) wrote to 32,414 bytes; the raw DST samples to 5,607 and 5,742
    bytes. All well under the 100 KB ceiling.
12. **Row-ordering decision.** The master requires "per product, strictly
    increasing interval_start_utc", which both `sort_values(["interval_start_utc", "product"])`
    and `sort_values(["product", "interval_start_utc"])` satisfy. Pick one, state
    it in the docstring, and keep it stable: M3b and M3c fixtures are byte-compared
    in determinism tests, and the pivot to a (P, T) matrix should not depend on it.
13. **Whole-year download per call.** `_fetch_raw` will pull one ~90 KB zip per
    year in the window, so the default 2023-2024 config is two small downloads,
    once (not per hub). This is the good side of memory:
    fetch-da-prices-per-location-redownload, and it should be stated in the
    docstring so nobody later "optimizes" it into the per-location loop.
14. **mypy `warn_return_any`.** gridstatus is under `ignore_missing_imports`, so
    `_get_document(...).url`, `parse_doc(...)`, and `get_zip_file(...)` are all
    `Any`. Annotate helper returns as `pd.DataFrame` / `str` and cast at the
    boundary, as `prices.py` does.
15. **One networked build step, scripted.** Same as T1: generate the three
    fixtures with a real fetch during the build, then never again. The raw DST
    samples must be captured pre-canonicalization (post-`read_csv`, post-strip),
    filtered to `Delivery Date == '03/12/2023'` and `'11/05/2023'`, so AC-3 and
    AC-4 run offline.

### Existing Patterns to Follow

- **Four-piece module** (`_fetch_raw` / `_canonicalize` / `_validate` /
  `fetch_*`), with only `_fetch_raw` touching the network, so every test runs
  from a committed raw sample.
- **Validate on every return path**, cache hit included, so a hand-edited
  parquet fails loudly (`prices.py:179`).
- **Module docstring restates the gotchas it defends against**, citing them by
  number; function docstrings name the acceptance criteria they cover.
- **AST-based import confinement**, never a substring grep
  (memory: ast-based-import-confinement-guard). Widen the existing test to an
  allowlist `{prices.py, as_prices.py}` rather than adding a second test.
- **`pytest.mark.manual` for the live fetch**, registered and deselected by
  default; the conftest guard is already marker-aware
  (memory: network-test-marker-convention).
- **Synthetic frames for error paths** (gaps, doctored data, zero prices), real
  fixtures for schema and DST.
- `from __future__ import annotations` in every module; ruff line-length 100;
  no em-dashes; no AI-attribution trailer in commits.
- **Housekeeping** (memory: adw-worktree-port-file-cleanup): `.ports.env` is
  already modified in this worktree and has leaked into three prior runs. Check
  `git status` before finalizing and restore it.

## Recommendations

1. **Build `_fetch_raw` on MIS report 13091**, not on `get_as_prices` or
   `get_mcpc_dam`. Sketch:

   ```python
   HISTORICAL_DAM_AS_MCPC_RTID = 13091  # "Historical DAM AS MCPCs", yearly zips

   def _fetch_raw(start: date, end: date) -> pd.DataFrame:
       import gridstatus
       from gridstatus import utils
       ercot = gridstatus.Ercot()
       frames = []
       for year in range(start.year, end.year + 1):
           doc = ercot._get_document(
               report_type_id=HISTORICAL_DAM_AS_MCPC_RTID,
               constructed_name_contains=f"{year}.zip",
           )
           df = pd.read_csv(utils.get_zip_file(doc.url))
           df.columns = [c.strip() for c in df.columns]   # 'REGUP ' has a trailing space
           frames.append(df)
       raw = pd.concat(frames, ignore_index=True)
       if raw.empty:
           raise ValueError(...)
       return raw
   ```

   Mirror `prices.py`'s empty-result guard so a silent upstream change surfaces
   as a clear error rather than "744 missing intervals".

2. **Let `Ercot.parse_doc` own the DST math** in `_canonicalize`, then melt,
   map, convert, cast: `parse_doc(raw)` -> melt on the five product columns ->
   `dropna(subset=["price"])` -> map codes to canonical names (raise on
   unmapped) -> `tz_convert("UTC")` -> `astype("datetime64[us, UTC]")` -> slice
   to the Central-day window built with `date` arithmetic -> sort ->
   `drop_duplicates(subset=["product", "interval_start_utc"], keep="first")`
   with `kind="stable"`, exactly as `prices.py` does.

3. **Write `_validate` as a per-product loop** over `groupby("product")`:
   columns and dtypes once, then per group check uniqueness, strict
   monotonicity, and the UTC expected index from
   `max(window_start_utc, launch_start_utc(product))`. Accumulate every missing
   `(product, interval)` pair and raise once with the full list, so a
   multi-product hole is diagnosed in one run.

4. **Name the launch rule explicitly:** `ECRS_LAUNCH = date(2023, 6, 10)` plus a
   `_PRODUCT_LAUNCH: dict[str, date]` mapping so future products (or a corrected
   date) are a one-line change. Document that pre-launch absence is structural
   and is represented by absent rows, never by fabricated zeros.

5. **Cache filename:** follow the energy pattern minus the location, e.g.
   `cache_dir / f"AS_MCPC_{start.isoformat()}_{end.isoformat()}.parquet"`. It
   cannot collide with a hub file (`HB_NORTH_...`), and the fixture keeps its
   spec-mandated name `as_mcpc_2023_07.parquet` because the cache test copies
   the fixture onto `_cache_path(...)` anyway.

6. **`bess fetch`:** call `fetch_as_prices` once, after the per-location loop,
   and echo `f"AS MCPC: {len(df)} rows for [{start}, {end}] cached under {cache_dir}"`.
   Unconditional is simplest and matches spec item 4; if a flag is wanted later,
   `--no-ancillary` is the additive shape. Update the command docstring, which
   currently promises only hub prices.

7. **Generate all three fixtures in the single networked build step**, from one
   download of the 2023 archive: the canonical July slice, and the two raw
   per-day slices taken after the column strip but before canonicalization.
   Record the exact command or script in the PR body for provenance.

8. **Test list for `tests/test_as_data.py`** (one per AC, mirroring
   `test_data.py`'s naming and TODO-comment style): schema round trip on the
   July fixture; 744 x 5 row counts with per-product counts; 23-per-product from
   the March raw sample plus "no ECRS rows present"; 25-per-product from the
   November raw sample; validation passes for a 2023-01-01 start despite ECRS
   absence; validation raises listing exact `(product, interval)` pairs on a
   doctored frame; zero and negative MCPCs pass through unclipped (synthetic
   frame); cache served twice from parquet under the network guard; the widened
   AST confinement guard; and a `pytest.mark.manual` live fetch.

9. **Run the gates before opening the PR** (`uv run ruff check .`,
   `uv run mypy`, `uv run pytest -q`). Note this worktree has no `.venv` yet, so
   `uv sync` comes first.

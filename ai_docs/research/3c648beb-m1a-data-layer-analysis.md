# Research: M1a Data Layer (ERCOT DA price ingestion, canonicalization, parquet cache)

## Metadata

adw_id: `3c648beb`
prompt: `specs/M1a_data_layer.md`
date: `2026-07-29`

## Executive Summary

The repo is a pure scaffold: every `src/bess/` function is a documented stub that
raises `NotImplementedError`, and `tests/test_data.py` is a list of TODO comments.
M1a is therefore an additive build with essentially zero refactoring risk, touching
`src/bess/data/prices.py`, the `fetch` command in `src/bess/cli.py`, `tests/test_data.py`,
`tests/fixtures/`, and small config additions in `pyproject.toml` (a `manual` pytest
marker) and possibly `config.toml` (a `cache_dir` key).

The two highest-value findings are in the pinned dependency, not in this repo.
First, `gridstatus==0.36.0`'s `Ercot.get_spp(..., market=DAY_AHEAD_HOURLY)` queries
ERCOT's MIS document list, which only retains recent documents, and it returns an
**empty DataFrame rather than raising** when no documents match, so the July 2023
fixture fetch may silently produce zero rows; the historical path is a different
method, `Ercot.get_dam_spp(year=2023)`. Second, for a date range the DAM branch of
`get_spp` filters on *publish* date, which is one day before the delivery day, so a
naive `[start, end]` request is off by one day.

## Existing Architecture

### Relevant Documentation Found

| Document | Contents relevant to M1a |
| -------- | ------------------------ |
| `specs/M1_python_core.md` | Master spec. Frozen `fetch_da_prices` signature, the canonical price schema table, gotchas 1 (DST), 3 (negative prices), 4 (pin and isolate gridstatus), acceptance criterion 9 (no network in CI). Wins on any conflict. |
| `specs/M1a_data_layer.md` | The task spec. 6 in-scope items, 8 acceptance criteria, 2 gotchas. |
| `specs/M1c_backtest_cli.md` | Downstream consumer. Confirms the fixture contract: "the frozen HB_NORTH July 2023 fixture" drives every backtest test. AC-2 there (5 to 60 equivalent full cycles for the month) is an indirect sanity check on M1a's price data being real. |
| `specs/TASKS.md` | T1 is this task; notes explicitly that "the build agent needs network for that single step" (fixture generation) and that tests and CI stay offline. |
| `CLAUDE.md` | Repo rules: frozen interfaces, canonical schema restated, no em-dashes, no network in tests, no data files committed except `tests/fixtures/`. |
| `ai_docs/project_context.md` | Why the project exists; GridStatus.io named as the ISO data source. No M1a-specific constraints. |
| `README.md` | Quick start already advertises `uv run bess fetch --config config.toml` (network) vs `bess backtest` (no network). Architecture and Results sections are TODO and belong to M1c, not M1a. |

No architecture diagrams exist yet. `ai_docs/research/` did not exist before this
document.

### Component Map

```
config.toml ──┐
              ▼
        src/bess/cli.py :: fetch()          <- M1a in scope
              │  (locations, start, end, cache_dir)
              ▼
   src/bess/data/prices.py                  <- M1a in scope, ONLY module
     ├─ fetch_da_prices()  (frozen signature)   allowed to import gridstatus
     ├─ cache read/write   (parquet, cache_dir)
     ├─ canonicalize()     (raw gridstatus frame -> CANONICAL_COLUMNS)
     └─ validate()         (sorted, unique, gap-free, dtypes)
              │
              │ returns canonical pd.DataFrame
              ▼
  ┌───────────┴────────────────────────────┐
  │                                        │
src/bess/backtest/runner.py       tests/fixtures/hb_north_2023_07.parquet
  run_backtest(prices_df, ...)      (frozen, committed, drives M1b/M1c tests)
              │
              ▼
src/bess/optimizer/lp.py :: optimize_dispatch(np.ndarray, ...)
              ▼
src/bess/viz/plots.py
```

Everything downstream of `prices.py` is out of scope for M1a (M1b and M1c), but the
fixture is the shared artifact all three tasks depend on.

### Key Files and Modules

| File | Current state | Purpose |
| ---- | ------------- | ------- |
| `src/bess/data/prices.py` | Stub. Defines `CANONICAL_COLUMNS` tuple (already correct and ordered) and `fetch_da_prices` raising `NotImplementedError`. Does not yet import gridstatus. | The whole data layer. |
| `src/bess/cli.py` | Typer app with `fetch`, `backtest`, `plot`, all raising `NotImplementedError`. Only a `--config` option exists (`ConfigOption = Annotated[Path, typer.Option("--config", ...)]`). | CLI surface. |
| `src/bess/models.py` | Complete. `BatterySpec`, `DispatchResult`, `BacktestResult` frozen dataclasses. | Not touched by M1a. |
| `tests/conftest.py` | Complete. Autouse `block_network` fixture that monkeypatches `socket.socket.connect` to raise. | Enforces AC-7 automatically for every test. |
| `tests/test_data.py` | Five TODO comments, no code. Tagged `TODO(schema)`, `TODO(gaps)`, `TODO(gotcha-1, DST)`, `TODO(gotcha-3)`, `TODO(AC-9)`. | The test file to build. |
| `tests/test_smoke.py` | Complete and passing. `test_imports_resolve` already imports `bess.data.prices`. | Keeps CI green today. |
| `pyproject.toml` | `gridstatus==0.36.0` already pinned (AC-6 half-satisfied). mypy strict-ish, ruff `E,W,F,I,B,UP,SIM,RUF` at line-length 100. `[tool.pytest.ini_options]` has `testpaths = ["tests"]`, `addopts = "-q"`, and **no markers section**. | Tooling. |
| `config.toml` | Spec-frozen keys only: battery params, `locations`, `start = 2023-01-01`, `end = 2024-12-31`. **No `cache_dir` key.** TOML dates parse to `datetime.date` via stdlib `tomllib`. | CLI defaults. |
| `.gitignore` | `*.parquet` ignored, with `!tests/fixtures/*.parquet` and `!tests/fixtures/**/*.parquet` negations. `data/*.parquet` also ignored. | Fixture will commit; cache will not. |
| `adw_gates.json` / `.github/workflows/ci.yml` | Identical three gates: `uv run ruff check .`, `uv run mypy`, `uv run pytest -q` / `uv run pytest`. | Definition of done. |

## Affected Areas

### Files That Will Need Changes

| File | Change | Driven by |
| ---- | ------ | --------- |
| `src/bess/data/prices.py` | Implement `fetch_da_prices` plus separable helpers: a thin gridstatus fetch, a pure `canonicalize(raw_df) -> DataFrame`, and a pure `validate(df, start, end)`. | Spec items 1-3, gotcha 2 ("keep the canonicalization logic separate from the fetch call so an upstream change is a one-function fix") |
| `src/bess/cli.py` | Implement `fetch()`; add `--locations`, `--start`, `--end`, `--cache-dir` overrides on top of `--config`; load config via `tomllib`. | Spec item 4 |
| `tests/test_data.py` | Replace the five TODOs with real tests, plus a `@pytest.mark.manual` live-fetch test. | Spec item 6, AC 1-5, AC-7 |
| `tests/fixtures/hb_north_2023_07.parquet` | New, generated once from a real fetch, committed. Must be < 100 KB. | Spec item 5, AC-8 |
| `tests/fixtures/` (raw-format DST samples) | New. AC-2 requires testing 2023-03-12 (23 h) and 2023-11-05 (25 h) "from a small committed raw-format sample, not the network", so raw pre-canonicalization frames for those two days must also be committed. | AC-2 |
| `pyproject.toml` | Register the `manual` marker and exclude it by default, e.g. `markers = ["manual: ..."]` and `addopts = "-q -m 'not manual'"`. Without this, an unregistered marker plus a network-touching test breaks CI. | AC-7 |
| `config.toml` (decision, see Risks) | Possibly add `cache_dir = "data"`. | Spec item 4 |
| `README.md` | Optional. The Quick start already documents `bess fetch`; the Architecture/Results TODOs belong to M1c. | - |

### Dependencies

**What `prices.py` will depend on:** `gridstatus==0.36.0` (exclusively here),
`pandas>=2.2`, `pyarrow>=17` (parquet engine), stdlib `datetime`/`pathlib`/`logging`.

**What depends on `prices.py`:**

- `src/bess/cli.py` (`fetch`, and later `backtest`/`plot` read the same cache).
- `src/bess/backtest/runner.py` consumes the canonical DataFrame shape (M1c).
- `tests/test_smoke.py::test_imports_resolve` imports the module today; adding a
  top-level `import gridstatus` makes gridstatus import cost part of every test run
  (it pulls plotly, pdfplumber, lxml, cryptography). Not a correctness issue, but a
  measurable collection-time cost.
- Every M1b/M1c test depends on the committed fixture, not on the function.

**AC-6 enforcement:** nothing else in `src/` imports gridstatus today, so the
constraint holds by construction. A cheap guard test (grep `src/` for `gridstatus`,
excluding `data/prices.py`) makes it durable.

### Integration Points

1. **gridstatus → canonical schema.** `Ercot()._finalize_spp_df` returns exactly
   these columns for both DAM paths: `Time`, `Interval Start`, `Interval End`,
   `Location`, `Location Type`, `Market`, `SPP`, sorted by `Interval Start` and
   index-reset. Mapping to canonical: drop `Time`; `Interval Start`/`Interval End`
   → `interval_start_utc`/`interval_end_utc` (tz-convert from `US/Central`);
   `Location` → `location`; `Location Type` → `location_type` (value is the module
   constant `LOCATION_TYPE_HUB = "Trading Hub"`, matching the spec); `Market` →
   `market` (`Markets.DAY_AHEAD_HOURLY.value == "DAY_AHEAD_HOURLY"`); `SPP` →
   `price`; `iso` is synthesized as `"ERCOT"`.
2. **Parquet cache ↔ tests.** AC-9/`TODO(AC-9)` requires a test that a second call
   is served from cache with the network guard active. The cache filename scheme
   must therefore be deterministic and documented so a test can pre-seed
   `tmp_path`.
3. **config.toml → CLI.** `tomllib.load` yields `datetime.date` for `start`/`end`
   directly, which matches the frozen `fetch_da_prices(start: date, end: date)`
   signature with no parsing needed.
4. **Fixture → M1b/M1c.** `tests/fixtures/hb_north_2023_07.parquet` is a
   cross-task contract; its exact filename is named in both M1a and M1c specs.

## Impact Analysis

### Scope of Change

Small and additive. Two source files (one of them a single function body), one test
file, two or three new fixture artifacts, and a pytest config stanza. No existing
behavior changes; no frozen interface changes. The only file shared with other
in-flight tasks is `pyproject.toml`, and only in the `[tool.pytest.ini_options]`
block. Realistic size: 150 to 250 LOC of source plus 150 to 250 LOC of tests.

### Risks and Considerations

1. **`get_spp` may return an empty frame for historical dates, silently.**
   `Ercot.read_docs` returns the caller-supplied `empty_df` when zero documents
   match (`ercot.py:5871`), and `get_spp`'s DAM branch passes a 7-column empty
   frame. ERCOT's MIS document list backing `_get_documents` retains only recent
   postings. For July 2023 the intended method is
   `Ercot.get_dam_spp(year=2023)` (`ercot.py:1476`), which pulls the historical
   yearly Excel archive of hub and load-zone DAM SPPs and runs it through the same
   `_finalize_spp_df`, giving an identical column set. It takes no location filter,
   so filter to `HB_NORTH` afterwards. **Recommendation:** the fetch helper should
   raise loudly on an empty gridstatus result rather than letting it flow into gap
   validation as a confusing "744 missing intervals" error, and fixture generation
   should use (or fall back to) `get_dam_spp`.
2. **DAM date-range semantics are publish-date based, off by one day.** In
   `get_spp`, when `end` is not None and market is `DAY_AHEAD_HOURLY`, the code sets
   `published_after=date, published_before=end` (`ercot.py:1904-1906`), and
   `_get_documents` filters on the document's Publish Date. DAM results are
   published the day before delivery, so a `[start, end]` request maps to delivery
   days roughly `[start+1, end+1]`. Pad the request by a day on each side and then
   slice to the requested window on `interval_start_utc`.
3. **Microsecond timestamp precision.** The schema says
   `timestamp[us, tz=UTC]`. pandas produces nanosecond tz-aware timestamps by
   default and pyarrow will write `timestamp[ns]` to parquet, so an AC-1 dtype
   assertion fails unless the columns are explicitly cast, e.g.
   `.astype("datetime64[us, UTC]")` (supported on pandas >= 2.2). Do the cast
   before writing and re-assert after the parquet round trip.
4. **`Location Type` comes back as `category` dtype** and `Location` as pandas
   `string` dtype (`_handle_settlement_point_name_and_type`). A `category` column
   round-trips through parquet as dictionary-encoded and reloads as `category`,
   which will not equal a plain string dtype assertion. Cast both explicitly during
   canonicalization and pick one string dtype (`str`/object or `string`) for the
   whole schema; assert it in the test.
5. **DST is mostly handled upstream, but verify.** `Ercot.parse_doc` uses the
   ERCOT `DSTFlag`/`Repeated Hour Flag` column to disambiguate the fall-back
   repeated hour (`ambiguous_based_on_dstflag`, `ercot.py:5886`) and shifts by an
   hour on `NonExistentTimeError` for spring-forward. So the raw frame should
   already be correctly localized; the job here is to `tz_convert("UTC")`
   immediately and never group by calendar day assuming 24 rows. AC-2 wants this
   proven from committed raw samples, which means capturing the raw frame (pre-
   canonicalization) for 2023-03-12 and 2023-11-05 during the one networked step.
6. **Gap validation across DST.** After UTC conversion, hours are strictly hourly
   with no gaps across both transitions, so gap detection should be a simple
   `pd.date_range(start_utc, end_utc, freq="h")` difference. Building the expected
   index in Central time would reintroduce the DST bug the spec warns about; build
   it in UTC.
7. **Window boundary definition.** `start` and `end` are `datetime.date`. Decide
   and document whether the window is Central-local calendar days (natural for a
   day-ahead market) or UTC days, and whether `end` is inclusive. This choice
   directly determines both the expected row count and gap detection; the spec does
   not settle it. Central-local inclusive is the defensible default: July 2023 then
   means 744 rows, matching the spec's stated fixture size.
8. **`cache_dir` is not in `config.toml`.** The master spec's "Default config"
   section is an exact key list and omits it, but M1a item 4 says the cache dir
   comes "from config.toml defaults, overridable by flags". Least-conflict
   resolution: default to `Path("data")` in code, read an optional `cache_dir` key
   if present, and always allow `--cache-dir`. Adding the optional key to
   `config.toml` is a minor deviation worth calling out in the PR.
9. **The `manual` marker must actually be excluded.** `addopts` is currently just
   `-q`, so a `@pytest.mark.manual` live test would run in CI, hit the autouse
   socket guard, and fail. Both the marker registration and the default deselection
   are required for AC-7.
10. **mypy strictness friction.** `disallow_untyped_defs`, `warn_return_any`, and
    `strict_equality` are on, with `pandas-stubs` installed. gridstatus is covered
    by `ignore_missing_imports`, so its calls return `Any`: any function returning a
    gridstatus result directly will trip `warn_return_any`. Annotate the fetch
    helper's return as `pd.DataFrame` and cast at the boundary.
11. **Fixture size.** 744 rows x 7 columns with dictionary-encoded constant string
    columns is on the order of 10 KB, comfortably under the 100 KB AC-8 ceiling.
    Snappy or zstd compression both work; keep it deterministic.
12. **Network is needed exactly once.** Per `specs/TASKS.md` the build agent needs
    network for fixture generation only. That step should be a scripted, repeatable
    command (e.g. `uv run bess fetch --locations HB_NORTH --start 2023-07-01 --end
    2023-07-31 --cache-dir tests/fixtures`) so the provenance is recorded, and the
    fixture is then never regenerated by CI.

### Existing Patterns to Follow

- **Docstrings carry the spec trace.** Every stub docstring names the acceptance
  criteria it covers ("Covered by acceptance criteria: 9 ..."). Keep that when
  replacing stub bodies.
- **Module docstrings restate the gotchas** they defend against, citing the gotcha
  number. `prices.py`'s existing module docstring already does this for gotchas 1,
  3, and 4; leave it intact.
- **`from __future__ import annotations`** at the top of every module.
- **`CANONICAL_COLUMNS`** is already defined, correctly ordered, and commented with
  the dtype of each column. Build the output frame from it rather than restating the
  column list.
- **Tests are prose-documented** with an AC reference in the module docstring, and
  the TODO tags in `tests/test_data.py` map one-to-one onto tests to write.
- **No em-dashes** anywhere (CLAUDE.md). Ruff line-length 100.
- **Typer options via `Annotated`**, following the existing `ConfigOption` alias.
- Commit messages: no AI co-author trailer (CLAUDE.md and global rules).

## Recommendations

1. **Structure `prices.py` in four separable pieces**, per gotcha 2:
   - `_fetch_raw(location, start, end) -> pd.DataFrame` (the only gridstatus call;
     the "one-function fix" when the upstream API moves)
   - `_canonicalize(raw: pd.DataFrame, location: str) -> pd.DataFrame` (pure: rename,
     tz-convert to UTC, add `iso`, cast dtypes, reorder to `CANONICAL_COLUMNS`,
     sort, drop duplicates)
   - `_validate(df, start, end) -> None` (dtype/column check, strict monotonicity,
     no duplicates, gap detection listing missing intervals in the exception message)
   - `fetch_da_prices(...)` (cache lookup, orchestration, cache write, validate on
     *every* return path including the cache-hit path)
   Only `_fetch_raw` needs the network, which is what makes AC-2 and the gap and DST
   tests testable from committed raw samples.
2. **Prefer `get_dam_spp(year)` for the historical fixture**, with `get_spp` for
   recent windows, and raise a clear error if either returns zero rows. Verify empty
   handling before assuming the fetch worked.
3. **Do the UTC conversion in the first three lines of `_canonicalize`** and never
   touch Central time again. Build the expected hourly index in UTC for gap
   detection.
4. **Capture three fixtures during the single networked step**, not one: the July
   2023 canonical parquet, plus small raw-format samples for 2023-03-12 and
   2023-11-05 (AC-2 explicitly forbids getting those from the network at test time).
   Raw samples as CSV keep them readable and side-step the parquet gitignore rules;
   as parquet they are covered by the `!tests/fixtures/*.parquet` negation either way.
5. **Write the negative-price and gap tests synthetically**, from hand-built frames,
   rather than hunting for a negative print inside July 2023. AC-4 and AC-5 say
   "synthetic input" and "pass through unmodified"; synthetic frames make the
   assertions exact and keep the fixture small.
6. **Add the pytest marker config in the same commit** as the manual live-fetch
   test, and verify locally that `uv run pytest -q` collects zero manual tests.
7. **Add a guard test for AC-6** that greps `src/` for `gridstatus` imports outside
   `data/prices.py`, so the isolation constraint survives M1b and M1c.
8. **Run all three gates before opening the PR:** `uv run ruff check .`,
   `uv run mypy`, `uv run pytest -q`. Note that `.venv` is not yet created in this
   worktree, so `uv sync` is the first step.

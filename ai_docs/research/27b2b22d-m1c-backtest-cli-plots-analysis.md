# Research: M1c Backtest Runner, CLI, and Plots

## Metadata

adw_id: `27b2b22d`
prompt: `specs/M1c_backtest_cli.md`
date: `2026-07-29`

## Executive Summary

M1c is the integration task that closes M1: it wires the merged M1a data layer
and M1b optimizer together behind `run_backtest`, fills in the two plot
functions, implements the `bess backtest` and `bess plot` CLI commands, and
writes the real README results section. Five stubs currently raise
`NotImplementedError` and one test file is entirely TODO comments; nothing
already implemented needs to change, and no dependency changes are needed
(matplotlib 3.11.1 and typer 0.27.0 are already installed). Baseline gates are
green today: ruff clean, mypy clean on 17 files, 33 tests passing.

I prototyped the full backtest against the frozen HB_NORTH July 2023 fixture
with the default config. It solves in **0.014 s**, status optimal, and lands
comfortably inside the spec's sanity corridor: total revenue **$970,937.15**,
equivalent full cycles **33.18** (corridor is 5 to 60), 6,635.40 MWh
discharged, $146.33 per MWh discharged, $114,320 per MW-year annualized from
the 744-hour window. The four findings that will actually cost the build phase
time are: (1) **AC-4 determinism directly contradicts the required
`solve_time_seconds` field** unless the comparison excludes it; (2) the fixture
window is Central-day aligned, so UTC-day grouping produces 32 days with a
19-hour and a 5-hour partial edge while Central-day grouping produces 31 clean
days, which decides gotcha 2 for you; (3) `bess plot` needs the dispatch
arrays, which the frozen `BacktestResult` does not carry, so `bess backtest`
has to persist a dispatch artifact or the two commands have to share a solve;
and (4) matplotlib's default backend on a dev Mac is `macosx`, so `plots.py`
must force Agg or CI will be rendering on an interactive backend it does not
have.

## Existing Architecture

### Relevant Documentation Found

| Document | Contents relevant to M1c |
| -------- | ------------------------ |
| `specs/M1_python_core.md` | Master spec, wins on conflict. Frozen `run_backtest` signature and `BacktestResult` shape, the backtest metrics list, master AC-7 (runtime recorded in metrics JSON) and AC-8 (CLI end-to-end), default config, and the DoD README results table. |
| `specs/M1c_backtest_cli.md` | The task spec. 8 acceptance criteria, full-horizon only, two gotchas (annualization from real window hours, daily-revenue grouping must pick UTC or local and say so). |
| `specs/M1a_data_layer.md` | Upstream. Defines the fixture (`tests/fixtures/hb_north_2023_07.parquet`, 744 rows) that every M1c test runs from. |
| `specs/M1b_optimizer.md` | Upstream. The purity rule and the `DispatchResult` contract `run_backtest` consumes. Its AC-10 already covers the simultaneous-dispatch WARNING path, which the July fixture cannot exercise. |
| `specs/TASKS.md` | T3 is this task, depends on T1 and T2 merged. Notes explicitly that T3 finishes the M1 DoD "including the README results section with real numbers from the fixture month". |
| `CLAUDE.md` | Repo rules: frozen interfaces, optimizer purity, no network in tests, no em-dashes, no AI-attribution commit trailer. States that "backtest and plot run entirely from the parquet cache". |
| `app_docs/feature-3c648beb-data-layer.md`, `app_docs/feature-3b9cf1a9-lp-optimizer.md` | The documentation format the document phase will mirror for M1c. |
| `specs/review_issues/review-3c648beb.md` | M1a review. Issue #2: no CliRunner test exists for any Typer command yet, explicitly deferred to a later milestone. Issue #3: delete stale scaffold TODO comments as they are implemented. |
| `specs/review_issues/review-3b9cf1a9.md` | M1b review. Only issue was the stray `.ports.env` modification. |
| `ai_docs/memory/entries/lesson-lp-optimizer-degeneracy-in-tests.md` | Prior lesson: LP optima are non-unique, so assert net dispatch and revenue, not per-interval vertex values. Directly applicable to the M1c integration assertions. |
| `ai_docs/memory/entries/pitfall-adw-worktree-port-file-cleanup.md` | `.ports.env` is tracked and is dirty in this worktree right now (`M .ports.env`). Restore or untrack before finalizing. |
| `ai_docs/memory/entries/pitfall-highspy-untyped-mypy.md` | highspy is untyped; values read from it need explicit casts under `warn_return_any`. Relevant if `run_backtest` reads solver output directly (it should not; it reads `DispatchResult` fields). |

The README `## Architecture` and `## Results` sections are still TODO
placeholders and are owned by this task.

### Component Map

```
config.toml ──┐
              ▼
      src/bess/cli.py
        ├── fetch     (M1a, done)
        ├── backtest  (M1c, STUB)  ──┐
        └── plot      (M1c, STUB)  ──┤
                                     │
   ┌─────────────────────────────────┴──────────────────────────┐
   ▼                                                            ▼
src/bess/data/prices.py                              src/bess/viz/plots.py
  fetch_da_prices()  (M1a, done)                       plot_dispatch_detail()      STUB
  parquet cache under cache_dir                        plot_cumulative_revenue()   STUB
   │  canonical DataFrame (744 rows for the fixture)          ▲
   ▼                                                         │
src/bess/backtest/runner.py                                   │
  run_backtest(prices_df, battery, optimizer=...)  STUB       │
   ├── df -> prices ndarray + dt_hours  (the only new         │
   │        DataFrame/array boundary in the project)          │
   ├── optimizer(prices, dt_hours, battery)  <-- M4 Rust      │
   │        seam; nothing here may assume the impl            │
   ▼                                                          │
src/bess/optimizer/lp.py :: optimize_dispatch()  (M1b, done)  │
   │  DispatchResult(c, d, soc, objective, status, simul)     │
   ▼                                                          │
BacktestResult (frozen, models.py) ───────────────────────────┘
   │  metrics JSON per location + combined comparison table
   ▼
README results table + two embedded PNGs
```

### Key Files and Modules

| File | State | Role in M1c |
| ---- | ----- | ----------- |
| `src/bess/backtest/runner.py:17` | `raise NotImplementedError` | `run_backtest`, the whole of in-scope item 1 and 2. Signature and docstring already written and correct; only the body is missing. |
| `src/bess/viz/plots.py:18` | `raise NotImplementedError` | `plot_dispatch_detail(prices_df, result, output_path, window_start=None, window_days=7)`. Signature declared and described as "not spec-frozen; keep them stable anyway". |
| `src/bess/viz/plots.py:38` | `raise NotImplementedError` | `plot_cumulative_revenue(daily_revenue_by_hub: dict[str, pd.Series], output_path)`. The dict shape already encodes "one line per location". |
| `src/bess/cli.py:74` | `raise NotImplementedError` | `bess backtest --config`. |
| `src/bess/cli.py:87` | `raise NotImplementedError` | `bess plot --config`. |
| `src/bess/cli.py:31` | implemented | `bess fetch`, the pattern to mirror: `tomllib.load`, `settings["..."]` with `settings.get(key, default)` fallbacks for keys not frozen by the spec, flag overrides. |
| `src/bess/models.py:49` | frozen | `BacktestResult`. Nine fields; `daily_revenue` is a `pd.Series`, which is the only field needing custom JSON encoding. |
| `src/bess/data/prices.py:144` | implemented | `_cache_path(cache_dir, location, start, end)` produces `HB_NORTH_2023-07-01_2023-07-31.parquet`. The CLI test must copy the fixture to exactly that name. |
| `tests/test_backtest_integration.py` | 4 TODO comments, 0 tests | The single test file this task fills in. |
| `tests/conftest.py:18` | implemented | Autouse socket guard, marker-aware. Any accidental network in an M1c test fails loudly. |
| `tests/fixtures/hb_north_2023_07.parquet` | committed, 744 rows | The only offline data in the repo. HB_NORTH, 2023-07-01 05:00 UTC through 2023-08-01 05:00 UTC. |

## Affected Areas

### Files That Will Need Changes

| File | Change |
| ---- | ------ |
| `src/bess/backtest/runner.py` | Implement `run_backtest`: extract prices and `dt_hours` from the canonical frame, time the `optimizer(...)` call, compute all nine `BacktestResult` fields. Document the daily-revenue grouping choice in the docstring (gotcha 2). |
| `src/bess/viz/plots.py` | Force the Agg backend at import, implement both plot functions, return the written `Path`. |
| `src/bess/cli.py` | Implement `backtest` (load cached prices per configured location, run the backtest, write metrics JSON per location plus a combined comparison table, persist whatever the plot command needs) and `plot` (render both PNGs). Add `--output-dir` style options with `settings.get(...)` fallbacks. |
| `tests/test_backtest_integration.py` | Replace the four TODO comments with the real tests for M1c AC-1 through AC-7. |
| `README.md` | Replace the `## Architecture` and `## Results` TODOs: module diagram and data flow, results table with the real fixture-month numbers, both PNGs embedded (AC-8). |
| `app_docs/feature-27b2b22d-*.md` | New feature doc from the document phase, mirroring the two existing ones. |
| `.ports.env` | Restore or untrack. Currently dirty and unrelated to this feature. |
| new: a tracked image directory | The README-embedded PNGs need a tracked path. `.gitignore` blocks `*.parquet` but nothing blocks PNGs, so `app_docs/img/` or `docs/img/` both work. Do not put them in `data/`, which is the parquet cache dir and reads as generated output. |

No changes are needed to `models.py`, `prices.py`, `lp.py`, `pyproject.toml`,
`config.toml`, `conftest.py`, or CI.

### Dependencies

`run_backtest` depends on `bess.models`, `bess.optimizer.lp.optimize_dispatch`
(as a default argument only), pandas, and numpy. `plots.py` depends on
matplotlib and pandas. `cli.py` depends on all of the above plus `tomllib` and
typer.

Nothing depends on `run_backtest` or the plot functions yet except
`tests/test_smoke.py:19`, which only asserts the modules import. The M4 Rust
engine will depend on the `optimizer` parameter staying a plain injected
callable, which is why AC-5 exists.

All runtime dependencies are already pinned and installed: matplotlib 3.11.1,
typer 0.27.0, pandas 2.x with `pandas-stubs`, numpy 2.x, highspy 1.15.1.

### Integration Points

1. **DataFrame to ndarray boundary** (`run_backtest`). This is the only place
   in the project where canonical price rows become the pure arrays the
   optimizer contract requires. `dt_hours` must be derived here, not assumed.
2. **Injected-optimizer seam** (`run_backtest`'s `optimizer` parameter). The
   M4 drop-in point. `run_backtest` must call it and must not reach around it
   to `optimize_dispatch`.
3. **CLI to cache** (`bess backtest`). Per `cli.py`'s module docstring and
   CLAUDE.md, backtest and plot "run entirely from the parquet cache".
4. **Backtest to plot** (`bess plot`). See the risk below; this handoff is
   currently undefined.

## Impact Analysis

### Scope of Change

Additive and self-contained. Five stub bodies, one test file, one README, one
new image directory. Roughly 350 to 500 LOC including tests. No existing
implemented code changes; no frozen interface changes. The riskiest parts are
not the LP or the data (both proven) but the JSON/plot/CLI plumbing decisions
the spec leaves open.

### Risks and Considerations

**1. AC-4 (byte-identical metrics JSON) contradicts the required
`solve_time_seconds` field.** In-scope item 2 requires solve wall time in the
metrics, and master AC-7 requires it recorded in the metrics JSON. Wall time
differs between runs by construction, so two consecutive runs cannot produce
byte-identical JSON if the timing field is compared. Resolution: the
determinism test must compare the metrics with `solve_time_seconds` popped (or
compare a "deterministic subset"), and the docstring or test name must say so
explicitly. Do not quietly round the timing to make the bytes match; that
would defeat AC-7's purpose.

The underlying solve is genuinely deterministic. I ran the fixture solve in
three separate processes and the SHA-256 of the objective plus the full charge
and discharge arrays was identical every time
(`f7ac739b...`), so everything except the timing field will match byte for
byte.

**2. Gotcha 2, daily-revenue grouping, is effectively decided by the fixture.**
The fixture window is Central-day aligned: it starts at 2023-07-01 05:00 UTC
(midnight CDT) and ends at 2023-08-01 05:00 UTC. Measured on the fixture:

| Grouping | Distinct days | First day hours | Last day hours |
| -------- | ------------- | --------------- | -------------- |
| UTC date of `interval_start_utc` | 32 | 19 | 5 |
| `US/Central` local date | 31 | 24 | 24 |

UTC grouping produces two partial edge days on a window that is exactly 31
whole market days. Pick Central local date, and say so in the `run_backtest`
docstring as the spec demands. Note that `US/Central` is already the constant
`_CENTRAL_TZ` in `prices.py`, but `runner.py` should not import from
`prices.py` for this; a local constant or a small shared constant is cleaner
than coupling the backtest to the fetch module.

**3. `bess plot` has no defined input.** In-scope item 4 says `bess plot`
"renders both PNGs from a metrics/dispatch output", but the frozen
`BacktestResult` carries only `daily_revenue`, not the dispatch arrays that
`plot_dispatch_detail` needs (it takes a `DispatchResult`). Three options:

- (a) `bess backtest` writes a dispatch artifact per location (parquet or CSV
  of `interval_start_utc, price, charge_mw, discharge_mw, soc_mwh`) alongside
  the metrics JSON, and `bess plot` reads it. Cleanest, keeps `plot` cheap and
  offline, and gives the M6 dashboard something to consume. Note `.gitignore`
  has a blanket `*.parquet` rule, so such an artifact will never be committed
  by accident.
- (b) `bess plot` re-solves from cached prices. Simple, cheap here (0.014 s for
  a month), but wasteful for the full two-year window and it makes `plot`
  depend on the optimizer.
- (c) `bess backtest` renders the plots itself and `bess plot` is a thin
  re-render. Conflicts with in-scope item 4's split.

Recommend (a). AC-6 says "CLI end-to-end from the fixture produces the JSON and
both PNGs", which is satisfied by running `backtest` then `plot` in the test.

**4. matplotlib backend.** The default backend in this environment is `macosx`.
CI is headless Linux, where it would fall back to Agg, but relying on that is
fragile and can hang or warn. Set the backend explicitly in `plots.py` before
importing pyplot, or build figures with `matplotlib.figure.Figure` plus
`FigureCanvasAgg` and skip pyplot's global state entirely (also avoids figure
leaks across repeated test calls). Either way, close figures after saving.

**5. AC-6's 10 KB PNG floor is not tight.** A prototype three-panel 7-day plot
at 12x8 inches, dpi 120, rendered to 69,929 bytes. No risk, but do not drop dpi
below roughly 80 or shrink the figure much.

**6. The July fixture has no negative prices** (min $12.91, max $1,013.38), so
`simultaneous_hours` is 0 on every M1c integration run. The metrics field must
still be present and zero. Do not try to build a simultaneous-dispatch
assertion into the integration tests; M1b's `test_optimizer_properties.py`
already covers that path with a purpose-built single-interval case, and the
memory entry `lesson-lp-optimizer-degeneracy-in-tests` records why a naive
multi-hour construction does not work.

**7. The shipped `config.toml` cannot run offline.** It names three locations
over 2023-01-01 to 2024-12-31; only HB_NORTH July 2023 exists as a fixture. The
CLI test must write its own temp config (`locations = ["HB_NORTH"]`,
`start = 2023-07-01`, `end = 2023-07-31`, plus a `cache_dir` pointing at a
`tmp_path` containing a copy of the fixture named
`HB_NORTH_2023-07-01_2023-07-31.parquet`). `config.toml` is described as
"frozen by the spec", so add new keys via `settings.get(key, default)`
fallbacks and CLI flags rather than editing the tracked file, exactly as
`cli.py:64` already does for `cache_dir`.

Related: decide whether `bess backtest` calls `fetch_da_prices` (which will
silently fetch from the network on a cache miss) or reads the cache directly
and fails loudly. CLAUDE.md and the `cli.py` docstring both say backtest is
cache-only; a cache miss should be a clear error naming the expected file, not
a surprise download. The conftest socket guard would catch a regression here,
but only if a test exercises the missing-cache path.

**8. Annualization, gotcha 1.** Use the real window duration:
`(interval_end_utc.iloc[-1] - interval_start_utc.iloc[0])` in hours, which is
744.0 for the fixture, giving a factor of `8760 / 744`. Do not use
`len(df)` blindly either; it happens to equal the hour count only because
`dt_hours` is 1.0. Do not use calendar days, which breaks on DST windows.

**9. The annualized number is honest arithmetic but a misleading headline.**
$114,320 per MW-year extrapolated from a single ERCOT July is a heat-wave month
annualized; the README already carries a "read this before quoting numbers"
scope note, and the results section should say the per-MW-year figure is a
single-month annualization, not an observed annual result.

**10. README table shape conflict.** The master spec DoD asks for "revenue per
MW-year by hub by year" and the existing README stub has rows for all three
hubs. M1c AC-8 asks for "a small table (revenue, revenue per MW-year, cycles
for the fixture month)". Only the fixture month is available without network,
so build AC-8's table and either drop the hub-by-year stub or label it as
pending the full fetch. Flag this rather than silently leaving three TODO rows.

**11. mypy strictness.** `disallow_untyped_defs`, `warn_return_any`, and
`strict_equality` are on, and pandas-stubs is installed, so pandas reductions
returning `Any` (for example `Series.sum()`) need explicit `float(...)` casts.
Prefer converting to numpy early and doing the arithmetic on arrays, which
types cleanly and matches the optimizer's world.

**12. Stale TODO comments.** M1a's review flagged leaving scaffold TODOs above
implemented tests as an issue. Delete the four TODO blocks in
`tests/test_backtest_integration.py` as they are implemented rather than
leaving them above the new tests.

### Existing Patterns to Follow

- **Docstrings carry the spec rationale**, not just the behavior: see
  `lp.py:33` (no terminal SoC constraint, deferred cycle cap) and
  `prices.py:1` (why `get_dam_spp` over `get_spp`). Gotcha 2's grouping choice
  belongs in the `run_backtest` docstring in the same voice.
- **Acceptance criteria are named in docstrings** (`"""AC-5: ..."""`) in both
  existing test modules. Follow that so the review phase can map tests to
  criteria.
- **Guard tests parse the AST**, not source text
  (`test_data.py:203`, `test_optimizer_properties.py:145`). If M1c adds any
  import-confinement guard, use `ast`.
- **Assert net dispatch and revenue, not per-interval vertex values**
  (memory: `lesson-lp-optimizer-degeneracy-in-tests`). The integration
  assertions should be about invariants and totals.
- **Validation runs on every return path** and failures name the offending
  values (`prices.py:101`). Apply the same for a non-uniform `dt` or a
  multi-location frame handed to `run_backtest`.
- **CLI config handling**: `tomllib.load`, spec keys by index, non-spec keys
  via `settings.get(key, default)` with a module-level `_DEFAULT_*` constant
  and a comment explaining it is not spec-frozen (`cli.py:26`).
- **No em-dashes** anywhere in code comments, docstrings, or docs.

## Recommendations

### Prototyped results (validated, use these for the README)

Full backtest of the frozen fixture, default config
(100 MW / 200 MWh, 0.927 each way), `dt_hours = 1.0`:

| Metric | Value |
| ------ | ----- |
| Window | 2023-07-01 through 2023-07-31 CDT, 744 hourly intervals |
| Solver status | optimal |
| Total revenue | $970,937.15 |
| Objective vs recomputed revenue | agree to 2e-10, well inside the 1e-4 tolerance |
| Total discharged | 6,635.40 MWh (charged 7,721.60 MWh) |
| Equivalent full cycles | 33.18 (corridor 5 to 60, comfortably inside) |
| Revenue per MWh discharged | $146.33 |
| Revenue per MW-year | $114,320 (annualized from 744 h, factor 8760/744) |
| `simultaneous_hours` | 0 (no negative prices in this month) |
| Solve wall time | 0.014 s |

AC-1 and AC-2 are therefore already known to pass. SoC bounds and dynamics
residual are the same checks M1b already runs on synthetic series; on real data
they will pass for the same reason.

### Implementation shape

`run_backtest`:

1. Validate the frame is single-location and that `interval_start_utc` diffs
   are uniform; raise naming the offending value otherwise. In UTC the diff
   stays 1 h even across both DST transitions, which M1a's fixtures already
   prove, so this check is safe.
2. `dt_hours = diff.total_seconds() / 3600`.
3. `prices = df["price"].to_numpy(dtype=np.float64)`.
4. Time only the `optimizer(prices, dt_hours, battery)` call with
   `time.perf_counter()`. Call it positionally so any callable matching
   `optimize_dispatch`'s signature works.
5. Per-interval revenue `prices * (discharge_mw - charge_mw) * dt_hours`;
   total is its sum. Recompute rather than trusting `objective_value`, and
   assert nothing: AC-1 tests the agreement.
6. `daily_revenue`: group per-interval revenue by
   `interval_start_utc.dt.tz_convert("US/Central").dt.date`. Document this.
7. `window_hours = (interval_end_utc[-1] - interval_start_utc[0]) / 1 h`;
   `revenue_per_mw_year = total / power_mw * (8760 / window_hours)`.
8. Guard the two ratio metrics against a zero denominator
   (`total_discharged_mwh == 0` is reachable with flat prices, which is master
   AC-1's golden case). Return 0.0 rather than raising or emitting NaN, which
   would not round-trip through JSON.

`bess backtest`: read the config, load each location's cached parquet, run the
backtest, write `<output_dir>/<LOCATION>_metrics.json` (sorted keys, dates as
ISO strings) and a dispatch artifact per location, then write the combined
comparison table across locations. `bess plot`: read those artifacts and call
the two plot functions.

`plots.py`: force Agg, use `Figure` + `FigureCanvasAgg`, always
`fig.savefig(output_path, dpi=120)` and close, return `output_path`.

### Test plan mapping

| M1c AC | Test |
| ------ | ---- |
| 1 real-data properties | Run `run_backtest` (or `optimize_dispatch` via it) on the fixture; assert status optimal, SoC in `[0, energy_mwh]` within 1e-6, dynamics residual < 1e-6, recomputed revenue vs objective within 1e-4. |
| 2 sanity corridor | `total_revenue_usd > 0` and `5 <= equivalent_full_cycles <= 60`. Known value 33.18. |
| 3 metrics JSON completeness | Assert the JSON has exactly the expected key set and that `revenue_per_mw_year` equals `total / power_mw * 8760 / 744` rather than `total / power_mw` (which would be the hardcoded-8760 bug). |
| 4 determinism | Two CLI invocations into separate output dirs; compare `json.dumps(sort_keys=True)` with `solve_time_seconds` removed. Note the exclusion in the test name and docstring. |
| 5 injected optimizer | Stub returning a fixed `DispatchResult`; assert the returned metrics are derived from the stub's arrays (not the LP's) and that the stub was called once with the expected shapes. |
| 6 CLI end-to-end | `CliRunner` over a temp config plus a `tmp_path` cache holding the fixture; assert exit code 0, JSON exists and parses, both PNGs exist and are > 10 KB. `CliRunner.__init__` in typer 0.27 / click 8.2 takes `(charset, env)` only; do not pass `mix_stderr`. |
| 7 no network | Automatic via the autouse `block_network` fixture; no new test needed, but do not add a `manual` marker anywhere in this file. |
| 8 README | Not a pytest assertion; verify by hand during the document phase. |

Also add the AC-7-from-the-master-spec check the scaffold TODO calls for:
`solve_time_seconds` present in the JSON and strictly positive.

### Sequencing

1. `run_backtest` plus its unit-level integration tests (AC-1 through AC-5,
   AC-7). This is the highest-value, lowest-ambiguity piece.
2. `plots.py` with the Agg decision.
3. CLI `backtest` and `plot`, including the artifact handoff decision, then
   the `CliRunner` end-to-end test (AC-6) and the determinism test (AC-4).
4. Generate the real PNGs into the tracked image directory, write the README
   architecture and results sections with the numbers above (AC-8).
5. Before finalizing: `git status` and restore or untrack `.ports.env`, and
   confirm no `*.parquet` or `data/` output slipped into the diff.

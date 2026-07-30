# Research: M2b Benchmarks, Capture Rates, and Parameter Sweeps

## Metadata

adw_id: `325296bb`
prompt: `specs/M2b_benchmarks.md`
date: `2026-07-30`

## Executive Summary

M2b is an additive analytics slice: one new package (`src/bess/analytics/`
with `benchmarks.py` and `sweep.py`), two new CLI commands (`bess benchmark`,
`bess sweep`), one new plot function, a `[sweep]` table in `config.toml`, and
two new test files. Nothing frozen changes and M2a's rolling engine is only
consumed, never modified. Baseline gates are green today: ruff clean, mypy
clean on 20 source files, 59 tests passing and 1 deselected (`manual`).

I prototyped every acceptance criterion numerically against the committed
fixtures. Three findings the build phase needs before writing code:

1. **The headline capture rate is exactly 1.00000000 on the July fixture,**
   for both forecast variants. M1's perfect-foresight optimum on this month is
   day-separable (SoC returns to 0 at every Central day boundary), so rolling
   with `lookahead_days=1` reproduces perfect revenue bit for bit
   ($970,937.149952 both ways). AC-4's corridor is `(0, 1]` / `[0.4, 1.0]`, so
   1.0 passes, but a test written as `capture < 1.0` will fail and the README
   headline needs framing (see Risks). The M2a research doc flagged this in
   advance; it is now confirmed end to end.
2. **`bess backtest` writes both modes to the same file**, `{location}_metrics.json`
   (src/bess/cli.py:240), so the perfect metrics JSON is overwritten by a
   rolling run. AC-7 requires "both perfect and rolling metrics JSONs exist at
   the default output paths", which cannot happen today. M2b must introduce
   mode-qualified default paths; the low-risk shape is to keep writing the
   existing filename and *additionally* write `{location}_metrics_{mode}.json`,
   which leaves M1c AC-6 and M2a AC-9 tests untouched.
3. **Cost is negligible; the sweep is not a runtime concern.** Twelve backtests
   (3 durations plus 3 efficiencies, each in both modes) over the July fixture
   ran in **0.16 s** total. A full-month perfect solve is ~0.013 s, a rolling
   month ~0.05 s.

All golden values reproduce: constructed-day TB4 = 360.0 / TB2 = 180.0 by
construction; spring-forward 2023-03-12 gives 23 rows, TB4 = 75.37; fall-back
2023-11-05 gives 25 rows, TB4 = 91.07; fixture-month TB4 capture = 0.547038
(both modes), inside AC-5's open interval.

## Existing Architecture

### Relevant Documentation Found

| Document | What it contributes to M2b |
| -------- | -------------------------- |
| `specs/M2_rolling_and_benchmarks.md` | Master, wins on conflict. Exact TBk / foresight capture / TB4 capture definitions, the `[sweep]` config keys, the gotchas (DST, annualization, wall-time determinism). |
| `specs/M2b_benchmarks.md` | The task spec: 10 acceptance criteria, in-scope file list, out-of-scope list, three gotchas. |
| `specs/M2a_rolling_horizon.md` | Sibling slice, already merged. Its out-of-scope list explicitly assigns "plots changes" to M2b, which is what licenses touching `src/bess/viz/plots.py`. |
| `specs/M1_python_core.md`, `specs/M1c_backtest_cli.md` | Default config values, canonical schema, the CLI shape M2b extends. M1c line 37 defers TB2/TB4 and capture rate to M2 explicitly. |
| `app_docs/feature-cea65174-rolling-horizon-backtest.md` | How the rolling engine is wired (windowing, SoC carry, `mode` block), and that the dispatch-detail PNG is skipped in rolling mode. |
| `ai_docs/research/cea65174-m2a-rolling-horizon-analysis.md` | Predicted the capture-rate-equals-1.0 result and the DST source-day hole; both confirmed here. |
| `specs/review_issues/review-27b2b22d.md` (Issue: AC-4 determinism) | The exact T3 review note that M2b in-scope item 6 must close. |
| `ai_docs/memory/MEMORY.md` + entries | Determinism excludes wall-clock fields; matplotlib must stay on Agg; AST-based import guards; `.ports.env` cleanup pitfall. |
| `CLAUDE.md` | Frozen-interface list, canonical schema, no-em-dash rule, no-network-in-tests rule. |

### Component Map

```
config.toml ([sweep] NEW, [rolling], battery, locations, window)
      |
      v
src/bess/cli.py  ── fetch ── backtest ── plot ── benchmark (NEW) ── sweep (NEW)
      |                 |                              |               |
      |                 |                              |               |
      v                 v                              v               v
data/prices.py    backtest/runner.py            analytics/          analytics/
fetch_da_prices   solve_dispatch                benchmarks.py       sweep.py
(parquet cache)   metrics_from_dispatch          (NEW, pure)         (NEW, pure)
                  run_backtest [frozen]              |                   |
                        |                            |          runs run_backtest /
                  backtest/rolling.py                |          run_backtest_rolling
                  _local_market_day  <───── reuse ───┘          over BatterySpec variants
                  _day_blocks                                          |
                  run_backtest_rolling [frozen]                        v
                        |                                     viz/plots.py
                        v                                     plot_sweep_duration (NEW)
                  optimizer/lp.py optimize_dispatch [frozen, pure]
```

Data flow for the two new commands:

- `bess benchmark` -> `fetch_da_prices` (cache only) -> `benchmarks.daily_tbk` /
  aggregations -> `output/benchmarks.json`; separately reads the two mode
  metrics JSONs from disk -> capture rates appended to the same JSON.
- `bess sweep` -> `fetch_da_prices` -> for each variant BatterySpec, both
  `run_backtest` and `run_backtest_rolling` -> `output/sweep.json` +
  `output/sweep_duration.png`.

### Key Files and Modules

| File | Purpose / relevance |
| ---- | ------------------- |
| `src/bess/models.py` | Frozen `BatterySpec` / `DispatchResult` / `BacktestResult`. Sweeps build `BatterySpec` variants; nothing here changes. |
| `src/bess/optimizer/lp.py` | Pure HiGHS LP. Untouched; hard import-purity rule enforced by a test. |
| `src/bess/data/prices.py` | Canonical schema + parquet cache + `_cache_path`. Both new commands read through `fetch_da_prices` (cache hit, no network). |
| `src/bess/backtest/runner.py` | `solve_dispatch`, `metrics_from_dispatch`, `run_backtest`, `_price_series_and_dt`, `_single_location`. Sweep's perfect mode calls `run_backtest`. |
| `src/bess/backtest/rolling.py` | `RollingConfig`, `run_backtest_rolling`, and the day-slicing helpers `_local_market_day` (line 59) and `_day_blocks` (line 77) that M2b gotcha 1 requires reusing. |
| `src/bess/cli.py` | Typer app, `_load_settings`, `_battery_from_settings`, `_metrics_dict`, `_rolling_config_from_settings`, `_mode_block`, `_run_location`. Both new commands mirror this structure. |
| `src/bess/viz/plots.py` | Agg-forced matplotlib. Natural home for the sweep plot. |
| `tests/conftest.py` | Marker-aware socket block (AC-9 comes free if fixtures are used). |
| `tests/test_rolling_golden.py` | `_synthetic_day` helper and the `_canonicalize`-the-raw-DST-fixture pattern that M2b's DST TB test (AC-2) should copy. |
| `tests/fixtures/` | `hb_north_2023_07.parquet` (canonical, 744 rows), `hb_north_2023_03_12_raw.parquet` (23 raw rows), `hb_north_2023_11_05_raw.parquet` (25 raw rows). |

## Affected Areas

### Files That Will Need Changes

| File | Change | Why |
| ---- | ------ | --- |
| `src/bess/analytics/__init__.py` | NEW (empty, matching `data/__init__.py`) | New package; hatch already packages all of `src/bess`. |
| `src/bess/analytics/benchmarks.py` | NEW | Spec item 1 and 2: daily TBk, per-year / per-window aggregations, `foresight_capture_rate`, `tb4_capture`. Pure functions, no I/O. |
| `src/bess/analytics/sweep.py` | NEW | Spec item 4: build the duration and efficiency variant lists, run both modes, return structured results. Pure (no file writes). |
| `src/bess/viz/plots.py` | ADD one function | Spec item 4's plot: revenue per MW-year vs duration, one line per hub, solid rolling / dashed perfect. M2a's out-of-scope list assigns plot changes here to M2b. |
| `src/bess/cli.py` | ADD `benchmark` and `sweep` commands; ADD mode-qualified metrics path; ADD the `solve_time_seconds` docstring note | Spec items 3, 4, 6, plus the finding that both modes currently collide on one filename. |
| `config.toml` | ADD `[sweep]` table | Master spec "Config additions". |
| `tests/test_benchmarks.py` | NEW | AC-1..5, AC-7. |
| `tests/test_sweep.py` | NEW | AC-6, AC-8. |
| `README.md` | ADD M2 results section | AC-10; also the M1 "Results" section still says perfect-foresight only and the scope note still calls rolling horizon "on the roadmap". |
| `docs/sweep_duration.png` | NEW committed image | `/output/` is gitignored; README images live in tracked `docs/` (`docs/dispatch_detail.png` precedent). |

### Dependencies

What M2b depends on (all merged and green on this branch):

- `bess.backtest.runner.run_backtest` and `metrics_from_dispatch` for perfect-mode scoring.
- `bess.backtest.rolling.run_backtest_rolling` + `RollingConfig` for rolling-mode scoring.
- `bess.backtest.rolling._local_market_day` / `_day_blocks` for day slicing (gotcha 1).
- `bess.data.prices.fetch_da_prices` for cached price frames; `_cache_path` in tests.
- `bess.models.BatterySpec` for sweep variants (`dataclasses.replace` is the natural constructor).
- The `mode` block written by `bess backtest` for identifying a metrics JSON's mode.

What depends on M2b: nothing yet in-repo. Downstream in the roadmap, M5/M6
consume the benchmark JSON shape, and M4's Rust engine drops in behind
`optimize_dispatch`, so sweeps must keep calling the injected-optimizer entry
points rather than the LP directly.

### Integration Points

1. **CLI/config**: `[sweep]` keys `durations_h` and `round_trip_efficiencies`,
   read with `RollingConfig`-style fallbacks (`_rolling_config_from_settings`
   at src/bess/cli.py:94 is the pattern).
2. **Metrics JSON on disk**: capture rates are computed from files, not from
   in-process results (spec item 2). Requires the two-path fix below.
3. **Output directory**: `output_dir` resolution and `mkdir(parents=True)`
   already exist in `backtest`/`plot`; reuse verbatim.
4. **Plot layer**: one more function in `viz/plots.py`, keeping the
   `-> Path` return convention and the Agg backend.

## Impact Analysis

### Scope of Change

Additive and self-contained. Two new modules under a new package, two new CLI
commands, one plot function, one config table, two test files, a README
section. The only edits to existing behavior are the mode-qualified metrics
filename (a strict addition if the current filename keeps being written) and a
docstring. No frozen interface, no optimizer change, no rolling-engine change.

Measured cost on the fixture (nothing here is a runtime risk):

| Operation | Wall time |
| --------- | --------- |
| Perfect backtest, July fixture | 0.013 s |
| Rolling backtest (persistence, lookahead 1) | 0.052 s |
| Full 12-run sweep, one hub | 0.16 s |

### Risks and Considerations

1. **Capture rate is exactly 1.0 on the only committed fixture.** Confirmed:
   perfect = rolling-persistence = rolling-perfect = $970,937.149952, ratio
   1.00000000. Consequences:
   - AC-4's assertion must be `0 < capture <= 1.0` (with a small epsilon on
     the upper bound for float noise), never `< 1.0`.
   - The README headline "foresight capture rate" for the fixture month is
     100 percent, which reads as a bug unless explained. The honest framing:
     July 2023 HB_NORTH's optimal schedule happens to be day-separable, so a
     one-day-lookahead operator loses nothing; this is a property of the month,
     not a general result. The 4-hour duration variant does separate the two
     (capture 0.999957), as does the 0.92 round-trip efficiency variant
     (0.998978), so the sweep output is where the difference is visible.
2. **Both modes currently write `{location}_metrics.json`** (src/bess/cli.py:240).
   AC-7's "both metrics JSONs exist at the default output paths" is
   unreachable without a path change. Recommended: write the existing file
   *and* `{location}_metrics_{mode}.json`; `bess benchmark` reads the
   mode-qualified pair and skips capture cleanly (exit 0 + notice) when either
   is missing. Do not silently rename the existing file: two committed tests
   assert it (`tests/test_backtest_integration.py:245`,
   `tests/test_rolling_properties.py:277`).
3. **UTC-day vs local-market-day grouping.** `metrics_from_dispatch` groups
   `daily_revenue` by **UTC** date (32 buckets for the 31-day July fixture,
   documented at src/bess/backtest/runner.py:95). TBk is defined on **local**
   market days (31 buckets). Do not join the two by date key, and do not reuse
   `daily_revenue`'s grouping for TBk: grouping TBk by UTC day would produce
   two partial 5-hour/19-hour days at the window edges and silently wrong
   spreads. Capture rates use window totals, not daily series, so they are
   unaffected.
4. **DST both directions.** Confirmed from the raw fixtures: 2023-03-12 has
   local hours `[0,1,3,...,23]` (23 rows, no hour 2) and 2023-11-05 has
   `[0,1,1,2,...,23]` (25 rows). TBk itself only needs "all available hours"
   so it is safe, but the day-slicing must come from M2a's helpers rather than
   a fresh `groupby(dt.date)` on UTC timestamps.
5. **Days with fewer than 2k intervals.** TBk is ill-defined when top-k and
   bottom-k overlap (a clipped partial day would double-count). Canonical
   frames from `fetch_da_prices` are sliced on Central days so this cannot
   occur in practice, but the function should fail loudly with the day named,
   matching the project's "gaps fail loudly, never interpolate" convention,
   rather than emit a NaN that AC-3 then has to catch.
6. **Efficiency-sweep vs default-config mismatch.** `config.toml` uses
   `charge_eff = discharge_eff = 0.927`, while the sweep's 0.86 round trip is
   `sqrt(0.86) = 0.9273618`. The sweep's "0.86" point therefore reports
   $971,434.69, not the README's $970,937.15 headline. Document the sqrt
   convention *and* this ~$500 difference in the sweep JSON so the two numbers
   are not read as inconsistent (gotcha 2).
7. **Determinism (AC-8).** Both `BacktestResult.solve_time_seconds` and any
   aggregate sweep timing are wall-clock. Keep exactly one documented
   non-deterministic field per record and strip it in the test, mirroring
   `test_backtest_metrics_json_is_deterministic_across_runs`
   (tests/test_backtest_integration.py:128) and the
   `determinism-tests-exclude-wallclock-fields` memory entry.
8. **mypy is strict** (`disallow_untyped_defs`, `warn_return_any`,
   `check_untyped_defs`). `groupby(...).apply(lambda ...)` on a pandas Series
   returns `Any` and will trip `warn_return_any`. A numpy implementation over
   `_day_blocks` boundaries avoids the problem entirely and is also the
   literal "reuse the same day-slicing helper" the spec asks for.
9. **matplotlib backend.** `viz/plots.py` forces Agg at import time; add the
   sweep plot to that module rather than importing pyplot anywhere else
   (`matplotlib-agg-backend-for-plots` memory entry).
10. **`.ports.env` is already dirty on this branch** (`git status` shows it
    modified). This has been flagged as a skippable review issue in three
    prior runs. Restore or untrack it before finalizing so it does not land in
    the PR diff again (`adw-worktree-port-file-cleanup` memory entry).

### Existing Patterns to Follow

- **Cross-module private helper imports are established practice**:
  `rolling.py` imports `_price_series_and_dt` and `_single_location` from
  `runner.py` (src/bess/backtest/rolling.py:28). Importing `_local_market_day`
  and `_day_blocks` into `analytics/benchmarks.py` is consistent and avoids
  editing M2a's module (which is out of scope).
- **Pure library / IO-owning CLI split**: `optimize_dispatch` and
  `metrics_from_dispatch` take and return values; `cli.py` owns paths, JSON,
  and `typer.echo`. Gotcha 3 restates this for the analytics layer.
- **Config reading with defaults**: `_rolling_config_from_settings`
  (src/bess/cli.py:94) reads a sub-table with dataclass-default fallbacks.
- **JSON writing**: `json.dumps(..., indent=2, sort_keys=True)` everywhere.
- **Docstrings cite the acceptance criterion they satisfy** (see
  `fetch_da_prices`, `run_backtest`, and every test docstring in
  `tests/test_rolling_*.py`). Match that density.
- **Test fixtures**: `pd.read_parquet(JULY_FIXTURE)` for the canonical month;
  `_canonicalize(pd.read_parquet(RAW_DST_FIXTURE), day, day)` for DST days;
  `_synthetic_day` for hand-built local days (tests/test_rolling_golden.py:31).
- **CLI tests**: `CliRunner().invoke(app, [...])` with a `tmp_path` config
  written by a `_write_fixture_config` helper and the fixture copied to
  `_cache_path(cache_dir, LOCATION, start, end)`.
- **No em-dashes** anywhere in code comments, docstrings, or docs.

## Recommendations

### 1. `src/bess/analytics/benchmarks.py`

Pure functions over the canonical frame, numpy-based, using M2a's day slicing:

```python
def daily_tbk(prices_df: pd.DataFrame, k: int) -> pd.Series:      # index: local market date
def tbk_summary(prices_df: pd.DataFrame, k: int) -> dict[str, float]   # window mean/sum, per-calendar-year mean
def foresight_capture_rate(rolling_revenue: float, perfect_revenue: float) -> float
def tb4_capture(total_revenue_usd: float, daily_tb4: pd.Series, power_mw: float) -> float
```

Implementation sketch for `daily_tbk`: `_local_market_day` -> `_day_blocks` ->
for each block `np.sort` the slice, `v[-k:].sum() - v[:k].sum()`. Raise
`ValueError` naming the date if a block has fewer than `2 * k` intervals.
Docstring must state: raw prices, no efficiency adjustment, DST days use all
23/25 hours, units `$/MW-day`.

### 2. Metrics-path fix (do this before the benchmark command)

In `backtest`, after writing `{location}_metrics.json` unchanged, also write
`{location}_metrics_{mode.value}.json` with identical content. Then
`bess benchmark` looks for `{location}_metrics_perfect.json` and
`{location}_metrics_rolling.json`, and on a missing file emits
`typer.echo("... skipping capture rates ...")` and exits 0 (AC-7). Validate the
`mode` block inside each file rather than trusting the filename.

### 3. `src/bess/analytics/sweep.py`

```python
@dataclass(frozen=True)
class SweepConfig:
    durations_h: tuple[float, ...] = (1.0, 2.0, 4.0)
    round_trip_efficiencies: tuple[float, ...] = (0.80, 0.86, 0.92)

def duration_variants(battery, durations_h) -> list[tuple[float, BatterySpec]]   # energy = power * h
def efficiency_variants(battery, rtes) -> list[tuple[float, BatterySpec]]        # eff = sqrt(rte) per side
def run_sweep(prices_df, battery, sweep_config, rolling_config) -> dict[str, Any]
```

`run_sweep` calls `run_backtest` and `run_backtest_rolling` per variant and
returns plain dicts (no file I/O). Record `round_trip_efficiency`, the derived
one-way `charge_eff`/`discharge_eff`, and a `"efficiency_convention":
"round-trip split as sqrt per side"` note in the JSON (gotcha 2).

### 4. Plot

`plot_sweep_duration(results_by_hub: dict[str, ...], output_path: Path) -> Path`
in `viz/plots.py`: x = duration hours, y = `revenue_per_mw_year`, one color per
hub, solid line for rolling and dashed for perfect, legend, `dpi=120`, returns
the path. Copy `plot_cumulative_revenue`'s structure verbatim.

### 5. Tests

- `tests/test_benchmarks.py`: constructed-day golden (TB4 360.0 / TB2 180.0);
  DST golden using the raw fixtures (23 rows / TB4 75.37 and 25 rows / TB4
  91.07 as exact goldens if you want them tighter than the spec's row-count
  requirement); TB4 >= TB2 >= 0 and no-NaN over the July fixture; capture-rate
  corridor with `<= 1.0`; TB4 capture in (0, 1) both modes (measured 0.547038);
  CLI end-to-end for both the both-modes-present and rolling-missing paths.
- `tests/test_sweep.py`: perfect-mode revenue non-decreasing in duration
  (measured 568,566.54 -> 970,937.15 -> 1,640,743.57); `log`, do not assert,
  the rolling ordering; CLI writes sweep JSON + PNG > 10 KB; two runs
  byte-identical after stripping the wall-time field.

### 6. README

Extend the "Results" section with an M2 subsection: perfect vs rolling revenue
for the fixture month, the capture-rate headline **with the day-separability
caveat from Risk 1**, mean daily TB2/TB4 ($332.95 / $572.55) and TB4 capture
(0.547), the duration-sweep table, and the embedded
`docs/sweep_duration.png`. Also update the scope note, which currently lists
rolling-horizon dispatch as "on the roadmap" when it has shipped.

### 7. Sequencing

Path fix and `[sweep]` config -> `benchmarks.py` + its tests (fastest feedback,
no LP in the golden path) -> `sweep.py` + plot + tests -> CLI wiring -> README
and the `solve_time_seconds` docstring note (spec item 6, closes the T3 review
note at `specs/review_issues/review-27b2b22d.md`) -> `git status` check for
`.ports.env` before finalizing.

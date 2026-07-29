# Backtest, CLI, and Plots (M1c)

**ADW ID:** 27b2b22d
**Date:** 2026-07-29
**Specification:** specs/M1c_backtest_cli.md

## Overview

Wires the M1a data layer and M1b optimizer into an end-to-end backtest: load
canonical prices, solve the full horizon, compute per-hub revenue metrics,
and emit a metrics JSON and two plots. Implements `run_backtest`, the
`bess backtest` and `bess plot` CLI commands, and both matplotlib plots,
closing out the M1 milestone.

## What Was Built

- `run_backtest(prices_df, battery, optimizer=optimize_dispatch) -> BacktestResult`,
  implemented exactly as frozen in `specs/M1_python_core.md`, built on top of
  two new non-frozen helpers so the CLI can solve each location once and
  reuse it for both metrics and the dispatch plot.
- All `BacktestResult` metrics: total revenue, revenue per MW-year (annualized
  from the actual observed window length, not a hardcoded 8760), revenue per
  MWh discharged, total MWh discharged, equivalent full cycles, a UTC-day
  daily revenue series, simultaneous charge/discharge hours, and solve wall
  time.
- `plot_dispatch_detail`: a two-panel, 7-day price/dispatch/SoC PNG (price on
  top, charge/discharge bars with SoC on a twin y-axis below).
- `plot_cumulative_revenue`: one cumulative-revenue line per hub over the full
  backtest window.
- `bess backtest --config config.toml`: runs every configured location, writes
  one `{location}_metrics.json`, a combined `comparison.json`, the per-location
  dispatch-detail PNG, and the cross-location cumulative-revenue PNG.
- `bess plot --config config.toml`: re-runs the same per-location pipeline but
  writes only the two PNGs, not the metrics JSON.
- `tests/test_backtest_integration.py`: 9 integration tests covering all 8
  acceptance criteria, driven entirely by the committed M1a HB_NORTH July
  2023 fixture.
- README "Results" section filled in with real numbers and both plots from a
  `bess backtest` run against the fixture.

## Technical Implementation

### Files Modified

- `src/bess/backtest/runner.py`: implemented `run_backtest`, plus two new
  non-frozen helpers, `solve_dispatch` (solves and times the LP for one
  location) and `metrics_from_dispatch` (computes `BacktestResult` from an
  already-solved `DispatchResult`).
- `src/bess/cli.py`: implemented the `backtest` and `plot` commands, plus
  private helpers `_load_settings`, `_battery_from_settings`, `_metrics_dict`,
  `_comparison_row`, and `_run_location` (the shared per-location solve/plot
  pipeline). Added a `--output-dir` option to both commands that overrides
  `config.toml`'s `output_dir` key.
- `src/bess/viz/plots.py`: implemented `plot_dispatch_detail` and
  `plot_cumulative_revenue`; switched matplotlib to the `Agg` backend for
  headless CI and test runs.
- `tests/test_backtest_integration.py`: implemented all 9 tests (dispatch
  properties, revenue/cycles sanity corridor, metrics field coverage and
  annualization, determinism, injected-optimizer contract, both plot
  functions, and both CLI commands end-to-end).
- `README.md`: replaced the M1 results TODO table with real fixture numbers
  and embedded both PNGs (also committed under `docs/`).
- `.gitignore`: added `/output/` (CLI-generated metrics/PNGs; the `docs/`
  images embedded in the README are committed separately and unaffected).

### Key Changes

- **Solve-once sharing:** `run_backtest` is `solve_dispatch` +
  `metrics_from_dispatch` composed. The CLI calls the same two helpers
  directly via `_run_location` so a location's LP is solved exactly once per
  command invocation even though both the metrics JSON and the dispatch plot
  need the raw `DispatchResult`.
- **Annualization uses the actual window:** `revenue_per_mw_year` divides by
  `window_hours` computed from `prices_df`'s own first/last timestamps, then
  scales by the `_HOURS_PER_YEAR = 8760.0` constant; it never assumes the
  window itself spans exactly one year (spec gotcha 1).
- **Daily revenue is grouped by UTC calendar date** of `interval_start_utc`,
  documented as such in `metrics_from_dispatch`'s docstring per spec gotcha 2
  (this module intentionally has no ISO-specific timezone knowledge; that
  lives only in `bess.data.prices`).
- **`bess backtest` and `bess plot` never touch the network.** Both load
  prices via `fetch_da_prices` against the local parquet cache populated
  earlier by `bess fetch`; `dt_hours` is derived from the first row's interval
  width rather than hardcoded to 1.0.
- **Determinism caveat (from code review):** the metrics JSON written to disk
  by `bess backtest` embeds `solve_time_seconds`, which is not
  byte-identical across runs by nature (wall-clock timing). Acceptance
  criterion 4's determinism test correctly excludes this field before
  comparing; every other field is byte-identical across consecutive runs on
  the fixture. See `specs/review_issues/review-27b2b22d.md` (tech-debt,
  non-blocking): a docstring note calling this out explicitly near the CLI
  write path is still open.

## Usage

```bash
uv run bess fetch --config config.toml      # pull + cache ERCOT DA prices (network, manual only)
uv run bess backtest --config config.toml   # metrics JSON + plots from cache (no network)
uv run bess plot --config config.toml       # re-render PNGs only, from cache (no network)
```

### Examples

```python
from bess.backtest.runner import run_backtest
from bess.data.prices import fetch_da_prices
from bess.models import BatterySpec
from datetime import date
from pathlib import Path

battery = BatterySpec(
    power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927
)
prices_df = fetch_da_prices(
    "HB_NORTH", date(2023, 7, 1), date(2023, 7, 31), Path("data")
)
result = run_backtest(prices_df, battery)

result.total_revenue_usd       # $ over the window
result.revenue_per_mw_year     # $/MW-yr, annualized from the actual window
result.equivalent_full_cycles  # discharged MWh / energy_mwh
result.daily_revenue           # pd.Series, index: UTC date
```

```bash
uv run bess backtest --config config.toml --output-dir output
# output/HB_NORTH_metrics.json
# output/HB_NORTH_dispatch_detail.png
# output/comparison.json
# output/cumulative_revenue.png
```

## Configuration

No new frozen `config.toml` keys. `bess backtest` and `bess plot` read the
existing battery fields (`power_mw`, `energy_mwh`, `charge_eff`,
`discharge_eff`, `initial_soc_mwh`, `max_cycles_per_day`) plus `locations`,
`start`, and `end`. Two optional, non-frozen keys (mirroring the `fetch`
command's `cache_dir` fallback):

- `output_dir` in `config.toml` (falls back to `output/` if absent).
- `--output-dir` CLI flag on both `backtest` and `plot`, which overrides
  `config.toml`.

## Testing

```bash
uv run pytest tests/test_backtest_integration.py
uv run ruff check src/bess/backtest/runner.py src/bess/cli.py src/bess/viz/plots.py
uv run mypy
```

All 8 acceptance criteria from `specs/M1c_backtest_cli.md` are covered: the
real-data property run (status optimal, SoC/dynamics/revenue tolerances),
the revenue/cycles sanity corridor, full metrics field coverage with correct
annualization, run-to-run determinism (excluding solve time), the
injected-optimizer contract via a stub `DispatchResult`, CLI end-to-end
producing JSON and both PNGs (each over 10 KB), no network in any test, and
the README results section.

## Notes

- Rolling horizon, TB2/TB4 benchmarks, capture rate, parameter sweeps, and a
  dashboard remain explicitly out of scope for M1c, deferred to M2.
- The code review (`specs/review_issues/review-27b2b22d.md`) passed with one
  non-blocking tech-debt issue: the `solve_time_seconds` non-determinism
  caveat noted above.
- `.ports.env` was touched (ADW worktree port bookkeeping), unrelated to this
  feature, consistent with prior milestones.

# Rolling-Horizon Backtest (M2a)

**ADW ID:** cea65174
**Date:** 2026-07-30
**Specification:** specs/M2a_rolling_horizon.md

## Overview

M1's `run_backtest` gives the optimizer perfect foresight over the entire
horizon at once, an unrealistic upper bound. This feature adds a
rolling-horizon backtest mode that re-solves once per local market day, using
only that day plus a short lookahead of forecast prices, commits just the
current day's dispatch, and carries state of charge into the next day. It
reuses the same frozen `optimize_dispatch` LP and the same `metrics_from_dispatch`
scoring path as M1, so perfect and rolling results are directly comparable.

## What Was Built

- `RollingConfig` dataclass and `run_backtest_rolling(prices_df, battery, config, optimizer=optimize_dispatch) -> BacktestResult`, the new frozen M2 entry point.
- `solve_rolling_dispatch`, a non-frozen helper that exposes the stitched committed `DispatchResult` (per-interval charge/discharge/SoC) for tests and future plotting.
- Local-market-day windowing (America/Chicago) with `persistence` and `perfect` forecast variants for the lookahead days, mapped by local hour-of-day to stay correct across DST transitions.
- `bess backtest --mode perfect|rolling` CLI flag (default `perfect`, unchanged M1 behavior); rolling mode reads `[rolling]` from `config.toml`.
- An additive `mode` block in every metrics JSON (`{"mode": "perfect"}` or `{"mode": "rolling", "lookahead_days": ..., "forecast": ...}`).
- Golden tests (`tests/test_rolling_golden.py`) and property tests (`tests/test_rolling_properties.py`) covering all 10 acceptance criteria from the spec.

## Technical Implementation

### Files Modified

- `src/bess/backtest/rolling.py` (new): `RollingConfig`, `solve_rolling_dispatch`, `run_backtest_rolling`, and the local-market-day/persistence-forecast helpers.
- `src/bess/cli.py`: adds `BacktestMode` enum, `--mode` option on `bess backtest`, `_rolling_config_from_settings`, `_mode_block`, and threads `rolling_config` through `_run_location`.
- `tests/test_rolling_golden.py` (new): two-day foresight golden, equivalence golden vs. M1 on the July 2023 fixture, DST window goldens.
- `tests/test_rolling_properties.py` (new): solver-status, SoC continuity, dominance, committed-series integrity, runtime budget, CLI, and determinism properties.
- `config.toml`: adds the default `[rolling]` table (`lookahead_days = 1`, `forecast = "persistence"`).

### Key Changes

- **Windowing.** `_day_blocks` splits the canonical, UTC-sorted price series into contiguous per-local-day blocks (a local calendar day is always contiguous in UTC order except at the DST-transition instant). Each iteration solves `[commit day] + [up to lookahead_days forecast days]`, truncating at the end of `prices_df` so the final day is always solved alone.
- **Forecast mapping by local hour, not array position.** `_persistence_forecast` builds an hour-of-day -> price lookup from the commit day (deduping a 25-hour fall-back source, forward/back-filling a 23-hour spring-forward source) and reads it back in the lookahead day's local-hour order. This is what makes the persistence forecast DST-safe (spec gotcha 2): positional mapping would silently misalign prices on a shifted day.
- **SoC carry.** Each window's `BatterySpec.initial_soc_mwh` is replaced with the previous day's committed ending SoC (`dataclasses.replace`); only the commit-day slice of each solve is written into the output arrays, the lookahead days are re-solved (never reused) on the next iteration.
- **Scoring stays shared.** `solve_rolling_dispatch` stitches a composite `DispatchResult` across all committed days (recomputing `simultaneous_hours` and `objective_value` itself, since no single solver call produced the whole series), then `run_backtest_rolling` scores it with the exact same `metrics_from_dispatch` M1 uses.
- **CLI wiring is additive.** `_run_location` now takes an optional `rolling_config`; when set, it calls `run_backtest_rolling` instead of `solve_dispatch` and skips the per-location dispatch-detail PNG (an M2b concern for full-horizon plots). The `mode` block is merged into the metrics dict regardless of mode, so perfect-mode JSON output also gains `{"mode": "perfect"}`.

## Usage

```bash
uv run bess backtest --config config.toml                 # perfect mode (default, unchanged M1 behavior)
uv run bess backtest --config config.toml --mode rolling  # M2a rolling-horizon mode, reads [rolling] from config.toml
```

`config.toml` rolling settings:

```toml
[rolling]
lookahead_days = 1        # forecast market days appended after the commit day
forecast = "persistence"  # "persistence" (headline) or "perfect" (diagnostic)
```

### Examples

```python
from bess.backtest.rolling import RollingConfig, run_backtest_rolling
from bess.data.prices import fetch_da_prices

prices_df = fetch_da_prices("HB_NORTH", start, end, cache_dir)
config = RollingConfig(lookahead_days=1, forecast="persistence")
result = run_backtest_rolling(prices_df, battery, config)
```

## Configuration

- `[rolling].lookahead_days` (int, default 1): number of forecast market days per solve window.
- `[rolling].forecast` (str, default `"persistence"`): `"persistence"` reuses the commit day's own prices by local hour-of-day; `"perfect"` uses the real future prices for the lookahead days (diagnostic only, not a realistic forecast).

## Testing

```bash
uv run pytest tests/test_rolling_golden.py tests/test_rolling_properties.py
uv run pytest       # full suite
```

## Notes

- `lookahead_days > 1` combined with `forecast="persistence"` is implemented (each lookahead day independently reuses the commit day's prices, not chained day-to-day) but has no dedicated test yet; it is not exercised by `config.toml`'s default or by any of the 10 acceptance criteria.
- Benchmarks, capture rates, sweeps, and plot changes for rolling mode are explicitly out of scope here and land in M2b.
- No M1 frozen interface (`BatterySpec`, `DispatchResult`, `BacktestResult`, `optimize_dispatch`, `fetch_da_prices`, `run_backtest`) was touched.

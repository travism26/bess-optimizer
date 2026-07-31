# M2b: Benchmarks and Parameter Sweeps

**ADW ID:** 325296bb
**Date:** 2026-07-30
**Specification:** specs/M2b_benchmarks.md

## Overview

Adds the analytics that make M2's rolling-horizon results comparable and
publishable: TB2/TB4 daily-spread benchmarks, foresight capture rate (the
headline number, rolling revenue / perfect revenue), TB4 capture, and two
1-D parameter sweeps (duration, round-trip efficiency). Two new pure
analytics modules feed two new Typer commands, `bess benchmark` and
`bess sweep`, plus a new sweep plot and a live M2 results section in the
README.

## What Was Built

- `src/bess/analytics/benchmarks.py`: pure `daily_tbk`, `tbk_summary`,
  `foresight_capture_rate`, and `tb4_capture` functions.
- `src/bess/analytics/sweep.py`: pure `SweepConfig`, `duration_variants`,
  `efficiency_variants`, and `run_sweep` functions.
- `bess benchmark --config config.toml` CLI command: writes
  `output/benchmarks.json` (TB2/TB4 per hub, plus capture rates when both
  mode metrics files exist).
- `bess sweep --config config.toml` CLI command: writes `output/sweep.json`
  and `output/sweep_duration.png`.
- `plot_sweep_duration` in `src/bess/viz/plots.py`: revenue per MW-year vs
  duration, one line per hub, solid rolling / dashed perfect.
- Mode-qualified metrics JSON output (`{location}_metrics_{mode}.json`) from
  `bess backtest`, so `bess benchmark` can locate both a perfect-mode and a
  rolling-mode metrics file at once.
- `[sweep]` config.toml table (`durations_h`, `round_trip_efficiencies`).
- README M2 results section: perfect vs rolling revenue, the foresight
  capture-rate headline, TB2/TB4 numbers, TB4 capture, the duration-sweep
  table, and the embedded sweep plot.

## Technical Implementation

### Files Modified

- `src/bess/analytics/benchmarks.py`: new. Daily TBk, per-year/window
  aggregation, and the two capture-rate formulas.
- `src/bess/analytics/sweep.py`: new. Battery-variant builders for the
  duration and efficiency sweeps, plus `run_sweep`, which scores every
  variant with both `run_backtest` (perfect) and `run_backtest_rolling`
  (rolling).
- `src/bess/analytics/__init__.py`: new, empty package marker.
- `src/bess/cli.py`: added `benchmark` and `sweep` commands, helpers
  (`_sweep_config_from_settings`, `_mode_metrics_path`,
  `_read_mode_metrics`), and mode-qualified metrics JSON writing inside the
  existing `backtest` command.
- `src/bess/viz/plots.py`: added `plot_sweep_duration`.
- `config.toml`: added the `[sweep]` table.
- `README.md`: added the "M2 results: rolling horizon and benchmarks"
  section with real fixture-month numbers and the sweep plot.
- `tests/test_benchmarks.py`, `tests/test_sweep.py`: new, cover all 10
  spec acceptance criteria.

### Key Changes

- **Day-slicing is reused, not reimplemented.** `daily_tbk` calls
  `bess.backtest.rolling._day_blocks` and `_local_market_day` directly (spec
  gotcha 1), so TBk agrees with the rolling engine's DST handling by
  construction: spring-forward days use all 23 hours, fall-back days all 25,
  never a hardcoded 24. A day with fewer than `2*k` hourly intervals raises
  `ValueError` rather than silently double-counting.
- **Capture rates are two mode-qualified metrics JSONs, not a live rerun.**
  `bess benchmark` reads `{location}_metrics_perfect.json` and
  `{location}_metrics_rolling.json` from the output directory (written by
  prior `bess backtest --mode perfect|rolling` runs). If either is missing,
  it prints a notice and skips capture for that location; it never raises
  and always exits 0.
- **`bess backtest` now writes two files per run**, not one: the existing
  unqualified `{location}_metrics.json` (M1 behavior, unchanged) plus a new
  mode-qualified `{location}_metrics_{mode}.json` with identical content.
  The unqualified name is shared by both modes and would otherwise get
  overwritten by whichever mode ran last; the mode-qualified copy is what
  lets both coexist for `bess benchmark` to read.
- **The efficiency sweep splits round-trip efficiency as `sqrt()` per
  side** (spec gotcha 2), matching `optimize_dispatch`'s default
  0.927-per-side / 86% round-trip convention. The convention is echoed
  verbatim into `sweep.json` via `EFFICIENCY_CONVENTION_NOTE` so a reader
  never has to guess why `round_trip_efficiency=0.86` produces
  `charge_eff=discharge_eff=0.9273618...`.
- **Both sweeps run every variant in both modes** (perfect via
  `run_backtest`, rolling via `run_backtest_rolling` with `[rolling]`
  config defaults), with the optimizer injected as a callable in both
  calls, the same seam `run_backtest`/`run_backtest_rolling` already use, so
  the M4 Rust engine drops into sweeps unchanged.
- Analytics stay pure per spec gotcha 3: neither `benchmarks.py` nor
  `sweep.py` does file I/O; `bess.cli` owns every path and JSON write.

## Usage

```bash
uv run bess fetch --config config.toml                    # pull + cache ERCOT DA prices (network, manual only)
uv run bess backtest --config config.toml                  # perfect-foresight metrics JSON + plots
uv run bess backtest --config config.toml --mode rolling   # rolling-horizon metrics JSON
uv run bess benchmark --config config.toml                 # TB2/TB4 + capture rates -> output/benchmarks.json
uv run bess sweep --config config.toml                     # duration/efficiency sweeps -> output/sweep.json, sweep_duration.png
```

`bess benchmark` needs cached prices (`bess fetch` first) and, for capture
rates, both `bess backtest --mode perfect` and
`bess backtest --mode rolling` to have already run against the same output
directory. `bess sweep` only needs cached prices; it runs its own perfect
and rolling backtests per variant internally.

### Examples

```toml
# config.toml
[sweep]
durations_h = [1, 2, 4]                        # energy_mwh = power_mw * duration_h
round_trip_efficiencies = [0.80, 0.86, 0.92]   # split sqrt() per side
```

## Configuration

- `[sweep].durations_h`: battery durations in hours to sweep; each variant's
  `energy_mwh = power_mw * duration_h`, other fields held at the base
  battery's values. Defaults to `[1, 2, 4]`.
- `[sweep].round_trip_efficiencies`: round-trip efficiencies to sweep; each
  variant's `charge_eff = discharge_eff = sqrt(round_trip_efficiency)`.
  Defaults to `[0.80, 0.86, 0.92]`.
- Both commands reuse the existing `cache_dir`, `output_dir`, `locations`,
  `start`/`end`, battery, and `[rolling]` settings already used by `fetch`
  and `backtest`.

## Testing

```bash
uv run pytest
```

`tests/test_benchmarks.py` and `tests/test_sweep.py` cover all 10 spec
acceptance criteria: the golden 24-hour TB4/TB2 values, DST day-count
agreement (23/25 hours), TB4 >= TB2 >= 0 with no NaNs, the foresight
capture-rate sanity corridor `[0.4, 1.0]`, TB4 capture in `(0, 1)`, sweep
monotonicity in perfect mode, end-to-end `bess benchmark` and `bess sweep`
behavior (including the missing-metrics graceful skip and PNG-size check),
and byte-identical repeated `sweep.json` runs after excluding
`solve_time_seconds`. All tests run from `tests/fixtures/`; none touch the
network.

## Notes

The review (`specs/review_issues/review-325296bb.md`) passed with one
skippable documentation gap: `sweep()`'s docstring (and
`sweep.py::_scalar_metrics`) don't yet note that `solve_time_seconds` is the
intentionally non-deterministic field the way `backtest()`'s docstring
does. Not a blocker; worth a one-line fix in a follow-up pass.

The July 2023 fixture happens to produce a 100.0% foresight capture rate at
HB_NORTH because that month's optimal schedule is day-separable at this hub
(the LP naturally returns state of charge to 0 at every local day boundary).
This is a property of this fixture and hub, not a general result; the
duration sweep shows rolling starting to lag perfect at the 4-hour point,
where the persistence forecast's inaccuracy matters more over a longer
hold.

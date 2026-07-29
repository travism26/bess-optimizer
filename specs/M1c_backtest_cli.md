# ADW Feature Spec: M1c, Backtest, CLI, and Plots

- **Repo:** bess-optimizer
- **Master spec:** specs/M1_python_core.md (frozen interfaces live there; on any conflict the master wins)
- **Depends on:** M1a and M1b merged. This feature integrates them.
- **Implements:** src/bess/backtest/runner.py, src/bess/viz/plots.py, the
  `bess backtest` and `bess plot` CLI commands, tests/test_backtest_integration.py

## Objective

Wire the data layer and optimizer into an end-to-end backtest: load canonical
prices, solve the full horizon, compute revenue metrics per hub, emit a metrics
JSON and two plots, and validate optimizer behavior on real market data for the
first time.

## In scope

1. `run_backtest(prices_df, battery, optimizer=optimize_dispatch) ->
   BacktestResult` exactly as signed in the master spec. The optimizer stays an
   injected callable; nothing in this module may assume which implementation
   it received. Full-horizon mode only.
2. Metrics per the master spec: total revenue, revenue per MW-year, revenue per
   MWh discharged, total MWh discharged, equivalent full cycles (discharged MWh
   divided by energy_mwh), daily revenue series, simultaneous_hours, and solve
   wall time.
3. Plots: (a) 7-day dispatch detail with price, charge/discharge bars, and SoC
   on a twin axis; (b) cumulative revenue over the full window, one line per
   location when multiple are present.
4. CLI: `bess backtest --config config.toml` writes metrics JSON per location
   plus a combined comparison table; `bess plot` renders both PNGs from a
   metrics/dispatch output.
5. tests/test_backtest_integration.py, driven entirely by the committed M1a
   fixture.

## Out of scope

Rolling horizon, TB2/TB4 benchmarks and capture rate (M2), parameter sweeps
(M2), dashboard, any new data fetching.

## Acceptance criteria

1. Real-data property run on the frozen HB_NORTH July 2023 fixture with the
   default config: status optimal, SoC within bounds (1e-6), dynamics residual
   below 1e-6, recomputed revenue matches the objective within 1e-4.
2. On the fixture, total revenue is strictly positive and equivalent full
   cycles is between 5 and 60 for the month. This is a sanity corridor, not a
   golden value; a result outside it means a units or dt bug.
3. Metrics JSON contains every field in criterion-2 scope above, with revenue
   per MW-year correctly annualized from the window length, not hardcoded to
   8760 hours.
4. Determinism: two consecutive backtest runs on the fixture produce identical
   metrics JSON (byte-identical after key sorting).
5. Injected-optimizer contract: an integration test passes a stub optimizer
   returning a fixed DispatchResult and asserts run_backtest consumes it
   without touching the real LP. This proves the M4 Rust engine can drop in.
6. CLI end-to-end from the fixture produces the JSON and both PNGs, each PNG
   nonempty and larger than 10 KB.
7. No network in any test.
8. README gains an M1 results section: a small table (revenue, revenue per
   MW-year, cycles for the fixture month) and both plots embedded.

## Gotchas

1. Annualization must use the actual window duration in hours. Mixing calendar
   assumptions with DST-affected data is the likeliest silent bug here.
2. The daily revenue series must be grouped on interval_start_utc converted to
   the market's local date, or documented explicitly as UTC days. Pick one and
   say so in the docstring; do not mix.

## Definition of done

All 8 criteria green in CI, ruff and mypy clean, README updated with real
numbers from the fixture run.

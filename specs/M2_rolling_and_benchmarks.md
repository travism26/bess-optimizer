# ADW Feature Spec: M2, Rolling Horizon and Benchmarks (master)

- **Project:** bess-optimizer (public repo, MIT license)
- **Milestone:** M2 of 6
- **Slices:** M2a (specs/M2a_rolling_horizon.md), M2b (specs/M2b_benchmarks.md); on any conflict this master wins
- **Language:** Python 3.12
- **Depends on:** M1 merged (perfect-foresight LP, backtest, CLI, fixture)

## Objective

M1's perfect-foresight result is an upper bound: the optimizer sees every
future price across the whole horizon. M2 produces the honest number next to
it. A rolling-horizon dispatch mode removes cross-day foresight (commit one
market day at a time), and an analytics layer adds the industry benchmarks
(TB2/TB4, capture rates) plus parameter sweeps that make the results
comparable and blog-ready. Headline metric: foresight capture rate, rolling
revenue divided by perfect-foresight revenue.

## In scope

1. Rolling-horizon backtest mode: optimize the current market day plus a
   lookahead day, commit only the current day, carry state of charge.
2. Forecast stand-ins for the lookahead day: "persistence" (headline) and
   "perfect" (diagnostic), behind one enum.
3. `bess backtest --mode perfect|rolling` (default perfect, M1 behavior
   unchanged).
4. Benchmark analytics: TB2/TB4 daily spreads, foresight capture rate, TB4
   capture, via a new `bess benchmark` command.
5. Parameter sweeps: two 1-D sweeps (duration, round-trip efficiency) via a
   new `bess sweep` command, JSON plus one plot.
6. README M2 results section with the capture-rate headline.

## Out of scope (do not build)

Real forecasting models (ML or otherwise), ancillary services, real-time
market, CAISO, MILP charge/discharge exclusivity, degradation beyond M1's
throughput accounting, 2-D sweep grids, price-scenario sweeps, Rust (M4),
Snowflake/AWS (M5), dashboard (M6).

## Frozen interfaces

Nothing in M1's frozen set changes: `BatterySpec`, `DispatchResult`,
`BacktestResult`, and the signatures of `optimize_dispatch`,
`fetch_da_prices`, `run_backtest` stay untouched. M2 adds, and then freezes,
these additions:

```python
@dataclass(frozen=True)
class RollingConfig:
    lookahead_days: int = 1          # window = commit day + N lookahead days
    forecast: str = "persistence"    # "persistence" | "perfect"

def run_backtest_rolling(
    prices_df: pd.DataFrame,         # canonical schema, single location
    battery: BatterySpec,
    config: RollingConfig,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> BacktestResult: ...
```

The optimizer stays an injected callable solving each window; the M4 Rust
engine must drop into rolling mode unchanged. `run_backtest_rolling` returns
the same `BacktestResult` shape, scored on committed dispatch only, so
perfect and rolling results are directly comparable.

## Rolling mechanics (implement exactly this)

1. Windows are defined on **local market days** (America/Chicago), then
   sliced from the UTC canonical frame. DST days are naturally 23 or 25
   hours; never assume 24.
2. For each market day d in the requested range:
   - Window = real prices for day d, followed by forecast prices for the
     next `lookahead_days` market days.
   - Forecast per the enum. persistence: day d's prices mapped by local
     hour-of-day onto the lookahead day; on a 25-hour lookahead day the
     duplicated hour reuses the same source price; on a 23-hour day the
     skipped hour is simply absent. perfect: the actual future prices.
   - The lookahead truncates at the end of the requested range for BOTH
     forecast variants (the final day is optimized alone).
   - Solve the window with the injected optimizer, initial SoC = carried
     SoC (day one uses `battery.initial_soc_mwh`).
   - Commit only day d's intervals; carried SoC = the committed SoC value
     at the end of day d.
3. Concatenate all committed intervals; compute every M1 metric on the
   committed series exactly as `run_backtest` does. Metrics JSON gains a
   `mode` block: `{"mode": "rolling", "lookahead_days": N, "forecast": ...}`
   (perfect-mode runs emit `{"mode": "perfect"}`). All existing fields keep
   their meaning; the addition is purely additive.

## Benchmark definitions (exact, reproducible)

Per local market day, per hub, on DA hourly prices:

- **TBk ($/MW-day):** sum of the k highest hourly prices minus the sum of
  the k lowest, k in {2, 4}. Raw prices, no efficiency adjustment (state
  this in the docstring). DST days use all 23 or 25 hours.
- **Foresight capture rate:** rolling total revenue / perfect total revenue,
  same battery, same window, same hub. The M2 headline number.
- **TB4 capture:** total revenue / (sum of daily TB4 x power_mw), reported
  for both modes. A 2-hour battery cannot reach 1.0 by construction.

## Config additions (config.toml)

```
[rolling]
lookahead_days = 1
forecast = "persistence"

[sweep]
durations_h = [1, 2, 4]              # energy_mwh = power_mw * duration
round_trip_efficiencies = [0.80, 0.86, 0.92]   # split sqrt() per side
```

## Acceptance criteria (rollup; slices carry the detail)

M2a: equivalence golden (rolling reproduces the M1 objective when the
window covers the horizon with perfect forecast), the two-day foresight
golden (perfect 275.0 vs persistence 0.0, exact), SoC continuity, dominance
(rolling <= perfect), DST window slicing, runtime budget (2-year rolling
backtest under 60 s), CLI `--mode rolling` end to end.

M2b: TB golden on a constructed day (TB4 == 360.0, TB2 == 180.0), TB and
capture properties, byte-identical JSON determinism with the wall-time
field documented as the sole exception, sweep JSON + plot, README section.

## Known gotchas

1. **DST:** window slicing and the persistence hour-of-day mapping are the
   likeliest silent bugs. Dedicated tests use the M1a raw DST samples.
2. **Zero-profit ties:** with lossless efficiency, an LP is indifferent to
   buying and selling at the same price, so committed SoC can drift on flat
   prices. Golden tests use lossy efficiency (0.8 charge) so idling is
   strictly optimal; do not "fix" solver ties in library code.
3. **Annualization:** reuse M1c's actual-window-hours annualization for
   rolling metrics. Never hardcode 8760.
4. **Determinism:** solve wall time is the one intentionally
   non-deterministic metrics field. Document it where it is written (this
   also closes the T3 review note).

## Definition of done

Both slices merged, all acceptance criteria green in CI, ruff and mypy
clean, README M2 section with the capture-rate headline (perfect vs rolling
vs TB4 for the fixture month), no changes to any M1 frozen interface.

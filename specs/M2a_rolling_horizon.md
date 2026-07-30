# ADW Feature Spec: M2a, Rolling-Horizon Dispatch

- **Repo:** bess-optimizer
- **Master spec:** specs/M2_rolling_and_benchmarks.md (mechanics and frozen additions live there; on any conflict the master wins)
- **Depends on:** M1 merged. Independent of M2b.
- **Implements:** src/bess/backtest/rolling.py, the `--mode` flag on `bess backtest`, tests/test_rolling_golden.py, tests/test_rolling_properties.py

## Objective

Implement `run_backtest_rolling` exactly as specified in the master:
optimize the current market day plus `lookahead_days` of forecast, commit
one day, carry SoC, score committed dispatch identically to M1. This
removes cross-day foresight, which is the unrealistic half of M1, while
reusing the pure `optimize_dispatch` per window through the injected
callable seam (the M4 Rust engine must drop in unchanged).

## In scope

1. `RollingConfig` and `run_backtest_rolling(prices_df, battery, config,
   optimizer=optimize_dispatch) -> BacktestResult`, signatures exactly as
   in the master spec.
2. Window construction on local market days (23/24/25 hours), persistence
   and perfect forecast variants, end-of-range truncation, SoC carry, all
   exactly per the master's "Rolling mechanics" section.
3. `bess backtest --mode perfect|rolling` (default perfect; rolling reads
   `[rolling]` from config.toml). Metrics JSON gains the additive `mode`
   block per the master.
4. Both test files below. No changes to optimizer/lp.py, models.py, or any
   frozen M1 interface.

## Out of scope

Benchmarks, capture rates, sweeps, plots changes (all M2b), forecasting
models, cycle caps, MILP exclusivity.

## Acceptance criteria

Golden (exact, within 1e-6 unless stated):

1. **Two-day foresight golden.** 48 hourly prices: hours 0-23 at $50;
   hours 24-25 at $200; hours 26-47 at $50. Battery 1 MW / 2 MWh,
   charge_eff 0.8, discharge_eff 1.0, initial SoC 0, lookahead_days 1.
   - forecast="perfect": committed revenue == 275.0 (charge 2.5 MWh from
     grid on day 1 costing $125, discharge 2 MWh at $200 on day 2 earning
     $400).
   - forecast="persistence": committed revenue == 0.0 (day 1 window sees a
     flat $50 tomorrow, so any position strictly loses through the lossy
     charge; the day 2 spike is unreachable at SoC 0 and no later spread
     pays back the charge loss).
   - Cross-check: M1 `optimize_dispatch` on the same 48h vector returns
     275.0; rolling-perfect matches it.
2. **Equivalence golden.** On the July 2023 fixture with the default
   battery: rolling with forecast="perfect" and lookahead_days >= 31
   (every window reaches the end of the range) produces total revenue
   equal to the M1 perfect-foresight backtest within $0.01.

Properties, on the July 2023 fixture, default battery, lookahead_days=1,
both forecast variants:

3. solver_status "optimal" for every window; any other status raises with
   the window's date in the message.
4. SoC continuity: committed SoC at each day boundary equals the next
   window's initial SoC within 1e-6, and 0 <= SoC <= energy_mwh everywhere.
5. Dominance: rolling total revenue <= M1 perfect-foresight total revenue
   plus 1e-6, for both variants.
6. Committed series integrity: exactly one committed interval per fixture
   hour, none duplicated, none missing; recomputed revenue from committed
   (prices, charge, discharge) matches the reported total within 1e-4.

Behavior and budget:

7. **DST windows:** from the M1a raw DST samples, the 2023-03-12 commit
   window has 23 hours and 2023-11-05 has 25; the persistence mapping
   fills a 25-hour lookahead day using the duplicated local hour's source
   price. No test touches the network.
8. **Runtime:** a synthetic 730-day rolling backtest (T about 17,520,
   lookahead 1, persistence) completes in under 60 seconds; wall time is
   recorded in the metrics JSON.
9. **CLI:** `bess backtest --config config.toml --mode rolling` on the
   fixture writes metrics JSON containing the `mode` block with
   lookahead_days and forecast echoed, plus every M1 metric field.
10. **Determinism:** two consecutive rolling runs produce identical
    metrics JSON after key sorting, excluding the documented wall-time
    field.

## Gotchas

1. Zero-profit ties: the goldens use lossy charge efficiency so the LP has
   a strict optimum; do not add tie-breaking to library code.
2. The lookahead day's forecast must be built by local hour-of-day, not
   array position: DST days shift positions.
3. Do not re-implement metrics: score the committed series with the same
   code path M1c uses, so the two modes stay comparable field by field.

## Definition of done

All 10 criteria green in CI, ruff and mypy clean, `run_backtest_rolling`
docstring states the commit/carry rule and end-of-range truncation, no M1
frozen interface touched.

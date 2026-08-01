# ADW Feature Spec: M3c, AS Backtest, CLI, and README

- **Repo:** bess-optimizer
- **Master spec:** specs/M3_ancillary_services.md (interfaces and assumptions live there; on any conflict the master wins)
- **Depends on:** M3a AND M3b merged to main (integrates both).
- **Implements:** `AsBacktestResult` in src/bess/models.py, `run_backtest_as` in src/bess/backtest/as_runner.py, the `--ancillary` flag on `bess backtest`, the uplift leg of `bess benchmark`, tests/test_as_backtest_integration.py, README M3 section

## Objective

Wire the co-optimizer into the backtest and CLI so one command produces the
M3 headline: AS uplift (co-optimized revenue / energy-only revenue) and the
revenue mix by product, from cached fixtures, offline, deterministic.

## In scope

1. `run_backtest_as(prices_df, as_prices_df, battery,
   products=DEFAULT_AS_PRODUCTS, optimizer=optimize_dispatch_as) ->
   AsBacktestResult`, signature exactly as frozen in the master.
   Responsibilities: align the long AS frame to the energy timeline into
   (P, T) price and availability matrices (absent product-hours, such as
   pre-launch ECRS, get price 0 and availability False), run one co-opt
   solve, compute every M1 metric on the co-optimized dispatch via the
   same code path `run_backtest` uses (memory:
   backtest-shared-solve-for-metrics-and-plots), and fill the AS fields
   (as_revenue_usd, revenue_by_product, award_mw_hours).
2. `bess backtest --ancillary` (also `[ancillary].enabled` in config):
   runs the co-opt backtest per configured hub. Metrics JSON is the M1/M2
   shape plus an additive `ancillary` block: products, sustain hours,
   energy_revenue_usd, as_revenue_usd, revenue_by_product,
   award_mw_hours, total_revenue_usd. Written to a filename qualified with
   both mode and ancillary flag (memory:
   metrics-json-unqualified-filename-collision). `--ancillary` with
   `--mode rolling` exits with a clear error: out of scope in M3.
3. `bess benchmark` extension: when an energy-only perfect metrics JSON
   and an ancillary metrics JSON both exist for a hub, emit AS uplift
   (total co-opt / energy-only total) and the revenue mix percentages;
   missing either file skips cleanly with a notice, never an error
   (mirrors the M2b capture-rate pattern).
4. Pure analytics helpers in src/bess/analytics/benchmarks.py for uplift
   and mix (no I/O; the Typer layer owns files).
5. README M3 section: uplift headline and revenue mix for the July 2023
   fixture month, the modeling assumptions note copied verbatim from the
   master ("Modeling assumptions" section), and the scope-note paragraph
   updated: energy-only understates, capacity-only co-opt overstates, the
   honest number lies between.
6. `tests/test_as_backtest_integration.py` covering the criteria below.

## Out of scope

Rolling + AS combined mode, plots changes (the two existing plots stay
as-is; an AS plot is future work), sweep integration, new market data,
any change to M3b's optimizer or to frozen M1/M2 interfaces.

## Acceptance criteria

1. **Alignment:** on a doctored AS frame missing one product-hour
   mid-window for a live product, run_backtest_as raises listing the
   (product, interval) pair; pre-launch ECRS absence is masked, not
   raised (build the mask from the master's launch rule).
2. **Metrics integrity:** on the July fixtures, energy_revenue_usd +
   as_revenue_usd == total_revenue_usd within 1e-4;
   revenue_by_product sums to as_revenue_usd within 1e-4; every M1 metric
   field is present and finite.
3. **Dominance end to end:** total co-opt revenue >= the energy-only
   perfect backtest revenue on the same fixture, same battery.
4. **Uplift sanity corridor:** July 2023 uplift is in [1.0, 8.0]. A value
   outside means a units or alignment bug, not a finding (mirrors the M2b
   corridor convention).
5. **CLI end to end:** `bess backtest --config config.toml --ancillary` on
   fixtures writes the qualified metrics JSON with the full ancillary
   block; the energy-only output files are byte-identical to a run without
   `--ancillary` (the flag must not perturb the existing pipeline).
6. **Benchmark integration:** with both metrics files present,
   `bess benchmark` emits uplift and mix; with the ancillary file absent,
   exits 0 with a notice.
7. **Rolling guard:** `--ancillary --mode rolling` exits nonzero with a
   message naming M3's perfect-only scope.
8. **Determinism:** two consecutive ancillary runs produce identical
   metrics JSON after key sorting, excluding the documented wall-time
   field (memory: determinism-tests-exclude-wallclock-fields).
9. **No network in CI;** everything runs from the committed July and DST
   fixtures.
10. **README:** M3 section live with real fixture-month numbers (uplift,
    mix table by product), the assumptions note, and the updated scope
    paragraph. Annualized figures reuse the actual-window-hours
    convention; never hardcode 8760.

## Gotchas

1. Do not re-implement metrics: score the co-optimized dispatch with the
   exact code path M1c/M2a use so all modes stay comparable field by
   field.
2. Frozen AsBacktestResult carries no per-interval arrays; share one solve
   between metrics and any future plotting, per the M1c lesson.
3. pd.Series fields keyed by product must use a stable product order (the
   products tuple order) so JSON serialization is deterministic.
4. The uplift corridor check needs the energy-only number from the SAME
   window as the ancillary run; guard against comparing a July metrics
   file against a full-year one (assert matching window fields in the
   JSONs before dividing).

## Definition of done

All 10 criteria green in CI, ruff and mypy clean, README M3 section live,
`bess --help` shows the new flag with an honest one-line description,
no frozen M1/M2 interface changed, fixtures unchanged from M3a.

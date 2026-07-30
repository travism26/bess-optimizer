# ADW Feature Spec: M2b, Benchmarks and Parameter Sweeps

- **Repo:** bess-optimizer
- **Master spec:** specs/M2_rolling_and_benchmarks.md (definitions live there; on any conflict the master wins)
- **Depends on:** M2a merged (capture rate consumes rolling results).
- **Implements:** src/bess/analytics/benchmarks.py, src/bess/analytics/sweep.py, the `bess benchmark` and `bess sweep` CLI commands, tests/test_benchmarks.py, tests/test_sweep.py, README M2 section

## Objective

Make M2's results comparable and publishable: TB2/TB4 daily spread
benchmarks, foresight capture rate (the headline: rolling revenue divided
by perfect revenue), TB4 capture, and two 1-D parameter sweeps, all with
exact reproducible definitions from the master spec.

## In scope

1. `src/bess/analytics/benchmarks.py`: pure functions over the canonical
   price frame. Daily TBk per the master definition (k in {2, 4}, local
   market days, DST days use all 23/25 hours, raw prices, no efficiency
   adjustment). Aggregations: mean daily TBk per hub per calendar year and
   for the requested window.
2. Capture rates per the master: foresight capture (rolling / perfect) and
   TB4 capture (revenue / (sum daily TB4 x power_mw)), computed from two
   metrics JSONs (one per mode).
3. `bess benchmark --config config.toml`: reads the price cache, writes
   benchmarks JSON (TB2/TB4 stats per hub); when both perfect and rolling
   metrics JSONs exist at the default output paths, also emits the capture
   rates; missing metrics files skip capture cleanly with a notice, never
   an error.
4. `bess sweep --config config.toml`: two 1-D sweeps from `[sweep]` config
   (duration over energy_mwh = power_mw x {1,2,4} h; round-trip efficiency
   over {0.80, 0.86, 0.92} split sqrt per side), each run in both modes
   (perfect, rolling with config defaults). Writes sweep JSON plus one
   plot: revenue per MW-year vs duration, one line per hub, solid rolling,
   dashed perfect.
5. README M2 results section: perfect vs rolling revenue, foresight
   capture rate headline, TB4 for the fixture month, the sweep plot.
6. Docstring note where metrics JSON is written documenting
   solve_time_seconds (wall time) as the single intentionally
   non-deterministic field (closes the T3 review note).

## Out of scope

2-D sweep grids, price-scenario or degradation sweeps, forecasting models,
new market data, dashboard, any change to M1 frozen interfaces or to
M2a's rolling engine.

## Acceptance criteria

Golden (exact, within 1e-6):

1. **TB golden:** constructed 24-hour day with 4 hours at $100, 4 at $10,
   16 at $50: TB4 == 360.0 and TB2 == 180.0.
2. **DST TB:** on the M1a raw DST samples, TB4 for the 23-hour and
   25-hour days computes from all available hours and the daily row count
   matches 23 and 25.

Properties, on the July 2023 fixture, default battery:

3. TB4 >= TB2 >= 0 for every day; no NaN for any day in the window.
4. Foresight capture rate is in (0, 1] and within the sanity corridor
   [0.4, 1.0]; a value outside means a units or windowing bug, not a
   finding (corridor mirrors M1c criterion 2).
5. TB4 capture is in (0, 1) for the 2-hour default battery, both modes.
6. Sweep monotonicity sanity: perfect-mode revenue is non-decreasing in
   duration (1h -> 2h -> 4h) on the fixture; log, do not assert, the
   rolling ordering.

Behavior:

7. `bess benchmark` end to end from the fixture cache: benchmarks JSON
   written with TB2/TB4 per hub; with both mode metrics present, capture
   rates included; with rolling metrics absent, exits 0 with a notice.
8. `bess sweep` end to end on the fixture: sweep JSON plus a PNG larger
   than 10 KB; two consecutive runs byte-identical after key sorting,
   excluding the documented wall-time field.
9. No test touches the network; everything runs from committed fixtures.
10. README updated with real fixture-month numbers, the capture headline,
    and the sweep plot embedded.

## Gotchas

1. TBk uses local market days: reuse the same day-slicing helper as M2a
   rather than reimplementing it; a second implementation WILL disagree on
   DST days.
2. The efficiency sweep splits round-trip efficiency as sqrt per side
   (matching M1's 0.927 convention); document the convention in the sweep
   JSON.
3. Keep analytics pure: no CLI I/O inside benchmarks.py or sweep.py;
   the Typer layer owns files and paths.

## Definition of done

All 10 criteria green in CI, ruff and mypy clean, README M2 section live
with the capture-rate headline, benchmarks and sweep JSONs documented in
the README alongside the M1 outputs.

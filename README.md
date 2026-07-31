# bess-optimizer

Perfect-foresight battery energy arbitrage on ERCOT day-ahead hub prices:
ingest historical prices, solve a linear program for the revenue-maximizing
charge/discharge schedule under real battery constraints, backtest over
2023-2024, and plot the results. Python core first; a Rust engine (PyO3) drops
in behind the same frozen interfaces in a later milestone.

## Scope note (read this before quoting numbers)

This model captures day-ahead energy arbitrage only, with perfect foresight.
That understates and misstates total ERCOT BESS revenue: in recent years the
majority of real ERCOT battery revenue has come from ancillary services
(Regulation, RRS, ECRS, Non-Spin), not energy arbitrage, and real operators do
not have perfect foresight. Treat the perfect-foresight number as an upper
bound on DA energy arbitrage value, not a project pro forma; the rolling-
horizon mode below is the honest number next to it. Ancillary-service
co-optimization is still on the roadmap.

## Quick start

```
uv sync
uv run bess fetch --config config.toml               # pulls prices (network)
uv run bess backtest --config config.toml             # perfect-foresight metrics JSON + plots
uv run bess backtest --config config.toml --mode rolling  # honest, one-day-lookahead metrics
uv run bess benchmark --config config.toml             # TB2/TB4 + capture rates
uv run bess sweep --config config.toml                 # duration/efficiency sweeps + plot
```

All commands after `fetch` run entirely from the parquet cache (no network).

## Architecture

TODO: module diagram and data flow (data/prices -> optimizer/lp -> backtest ->
viz), the frozen interfaces, and where the Rust engine slots in.

## Results

M1 results below are from `bess backtest` against the frozen HB_NORTH July
2023 fixture (`tests/fixtures/hb_north_2023_07.parquet`), the default
config.toml battery (100 MW / 200 MWh, 0.927 charge/discharge efficiency),
and perfect foresight. One month, one hub: an illustration of the pipeline,
not a multi-year, multi-hub result (see the scope note above).

| Hub      | Window       | Revenue      | Revenue ($/MW-yr) | Equivalent full cycles |
| -------- | ------------ | ------------ | ------------------ | ----------------------- |
| HB_NORTH | Jul 2023     | $970,937.15  | $114,320.02         | 33.18                    |

![7-day dispatch detail](docs/dispatch_detail.png)

![Cumulative revenue](docs/cumulative_revenue.png)

## M2 results: rolling horizon and benchmarks

M1's perfect-foresight number sees every future price in the horizon at
once, an unrealistic upper bound. M2 adds a rolling-horizon mode that
commits one market day at a time (real prices for the day, a persistence
forecast for the lookahead day, carried state of charge), plus the industry
benchmarks that make the result comparable: TB2/TB4 daily spreads and
capture rates. Numbers below are from `bess backtest --mode rolling` and
`bess benchmark`, same fixture, hub, and default battery as M1.

**Headline: foresight capture rate.** Rolling revenue / perfect-foresight
revenue, same battery and window: **100.0%** for HB_NORTH, July 2023
(rolling $970,937.15 vs perfect $970,937.15, both to the cent). This is not
a general result: July 2023's optimal schedule happens to be day-separable
at this hub (the LP naturally returns state of charge to 0 at every local
day boundary), so a one-day-lookahead operator loses nothing that month. The
duration and efficiency sweeps below do show a small gap opening up at
longer duration, where the persistence forecast starts to matter.

| Mode    | Revenue      | Revenue ($/MW-yr) | Equivalent full cycles |
| ------- | ------------ | ------------------ | ----------------------- |
| Perfect | $970,937.15  | $114,320.02         | 33.18                    |
| Rolling | $970,937.15  | $114,320.02         | 33.18                    |

**TB2/TB4 (daily spread benchmarks).** Mean daily TBk for HB_NORTH, July
2023, raw prices, local (America/Chicago) market days, no efficiency
adjustment:

| Benchmark | Mean daily ($/MW-day) |
| --------- | ----------------------- |
| TB2       | $332.95                  |
| TB4       | $572.55                  |

**TB4 capture** (revenue / (sum of daily TB4 x power_mw)) for the 2-hour
default battery: **0.547** in both modes. A 2-hour battery cannot reach 1.0
against a 4-highest/4-lowest daily spread by construction; this is the
number that says how much of that spread the battery's duration actually
lets it capture.

**Duration sweep.** `bess sweep` varies energy_mwh = power_mw x duration for
duration in {1, 2, 4} h, holding efficiency fixed, in both modes:

| Duration | Perfect revenue ($/MW-yr) | Rolling revenue ($/MW-yr) |
| -------- | --------------------------- | --------------------------- |
| 1 h      | $66,944.12                   | $66,944.12                   |
| 2 h      | $114,320.02                  | $114,320.02                  |
| 4 h      | $193,184.32                  | $193,176.05                  |

Revenue per MW-year is non-decreasing in duration in perfect mode, as
expected (more storage can only add optionality); rolling tracks it almost
exactly, with the persistence forecast costing a small amount only at the
4-hour point, where longer holds make the lookahead's accuracy matter more.

![Duration sweep](docs/sweep_duration.png)

## License

MIT. See [LICENSE](LICENSE).

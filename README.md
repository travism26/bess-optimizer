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
not have perfect foresight. Treat the output as an upper bound on DA energy
arbitrage value, not a project pro forma. Ancillary-service co-optimization and
rolling-horizon (imperfect foresight) dispatch are on the roadmap.

## Quick start

```
uv sync
uv run bess fetch --config config.toml      # pulls prices (network)
uv run bess backtest --config config.toml   # metrics JSON + plots (no network)
```

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

## License

MIT. See [LICENSE](LICENSE).

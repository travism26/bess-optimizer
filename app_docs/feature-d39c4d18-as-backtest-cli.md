# M3c: AS Backtest, CLI, and README

**ADW ID:** d39c4d18
**Date:** 2026-08-01
**Specification:** specs/M3c_as_backtest_cli.md

## Overview

Wires the M3b energy + AS co-optimizer into the backtest and CLI so one
command produces the M3 headline: AS uplift (co-optimized revenue /
energy-only revenue) and the revenue mix by product, from cached fixtures,
offline, deterministic. This is the integration milestone that makes M3a
(AS price data) and M3b (the co-optimizer LP) usable end to end.

## What Was Built

- `run_backtest_as` in `src/bess/backtest/as_runner.py`: aligns the long
  canonical AS price frame to `(P, T)` matrices, runs one co-opt solve, and
  scores the energy leg with the same metrics code path M1/M2 use.
- `AsBacktestResult` in `src/bess/models.py`: the frozen M3 backtest result
  shape (energy `BacktestResult`, total/AS revenue, revenue by product,
  award MW-hours).
- `bess backtest --ancillary` CLI flag (also `[ancillary].enabled` in
  `config.toml`): runs the co-opt backtest per configured hub alongside the
  existing energy-only pipeline, writing a qualified metrics JSON.
- `bess benchmark` extension: when an energy-only and an ancillary metrics
  JSON both exist for a hub, emits AS uplift and revenue mix percentages;
  missing either file skips cleanly with a notice.
- Pure `as_uplift` and `revenue_mix` analytics helpers in
  `src/bess/analytics/benchmarks.py`.
- README M3 section: uplift headline, revenue mix table, modeling
  assumptions, and an updated scope-note paragraph for the July 2023
  fixture month.
- `tests/test_as_backtest_integration.py`: end-to-end coverage of all 10
  spec acceptance criteria.

## Technical Implementation

### Files Modified

- `src/bess/backtest/as_runner.py`: new. `_align_as_matrices` and
  `run_backtest_as`.
- `src/bess/models.py`: added `AsBacktestResult` (frozen, additive to the
  existing M1/M3a/M3b contracts).
- `src/bess/analytics/benchmarks.py`: added `as_uplift` and `revenue_mix`
  (pure, no I/O).
- `src/bess/cli.py`: added the `--ancillary` option on `backtest`, helpers
  (`_ancillary_enabled_from_settings`, `_ancillary_products_from_settings`,
  `_ancillary_block`, `_ancillary_metrics_path`, `_read_ancillary_metrics`,
  `_same_window`), and the AS uplift/mix leg of `benchmark`.
- `src/bess/data/as_prices.py`: renamed `_PRODUCT_LAUNCH` to `PRODUCT_LAUNCH`
  (public) so `as_runner` can build the same launch-rule availability mask
  without reaching into a private name. Pure rename; behavior unchanged.
- `config.toml`: added the `[ancillary]` table (`enabled`, `products`,
  `[ancillary.sustain_hours]`).
- `README.md`: rewrote the scope note (energy-only understates, AS co-opt
  overstates, the honest number lies between) and added the "M3 results"
  section.
- `tests/test_as_backtest_integration.py`: new, covers all 10 acceptance
  criteria.

### Key Changes

- **One co-opt solve, scored by the existing metrics code path.**
  `run_backtest_as` does not reimplement metrics: it swaps the raw co-opt
  `DispatchResult.objective_value` for `AsDispatchResult.energy_revenue_usd`
  (via `dataclasses.replace`) before handing it to
  `bess.backtest.runner.metrics_from_dispatch`. This keeps
  `energy.total_revenue_usd + as_revenue_usd == total_revenue_usd` and
  makes the co-opt result's energy leg directly comparable, field by field,
  to a plain energy-only `BacktestResult`.
- **Per-product AS gaps follow the same launch-rule mask as the data layer.**
  `_align_as_matrices` reindexes the long AS frame onto the energy
  timeline; a product-hour missing before its `PRODUCT_LAUNCH` date is
  masked silently (price 0, availability `False`), while a missing hour at
  or after launch raises, listing every offending `(product, interval)`
  pair.
- **`--ancillary` never perturbs the existing energy-only pipeline.** The
  co-opt backtest runs as an additional step per location and writes to a
  separately named file
  (`{location}_metrics_{mode}_ancillary.json`, distinct from
  `{location}_metrics_{mode}.json`); the energy-only output is
  byte-identical with or without the flag.
- **`--ancillary --mode rolling` is rejected up front.** M3 co-optimization
  is perfect-foresight only; the CLI checks this before doing any work and
  exits nonzero with a message naming the scope limitation.
- **`bess benchmark`'s AS uplift guards against mismatched windows.**
  `_same_window` compares both metrics JSONs' `daily_revenue` date ranges
  before dividing, so a July co-opt total can never silently get divided by
  a full-year energy-only total (or vice versa).
- Product order is anchored to the `products` tuple everywhere
  (`revenue_by_product`, `award_mw_hours`), keeping `pd.Series`-keyed JSON
  serialization deterministic.

## Usage

```bash
uv run bess fetch --config config.toml                     # pull + cache DA prices + AS MCPCs (network, manual only)
uv run bess backtest --config config.toml                  # perfect-foresight metrics JSON + plots
uv run bess backtest --config config.toml --ancillary       # + energy/AS co-optimized metrics JSON
uv run bess benchmark --config config.toml                  # TB2/TB4 + capture rates + AS uplift/mix
```

`--ancillary` requires `--mode perfect` (the default); combining it with
`--mode rolling` exits nonzero. `bess benchmark`'s AS uplift section needs
both `{location}_metrics_perfect.json` and
`{location}_metrics_perfect_ancillary.json` to already exist under the
output directory (written by a prior `bess backtest --ancillary` run); if
either is missing it prints a notice and skips that section, still exiting 0.

### Examples

```toml
# config.toml
[ancillary]
enabled = false            # backtest co-opt off unless --ancillary or this flag
products = ["REG_UP", "REG_DOWN", "RRS", "ECRS", "NONSPIN"]

[ancillary.sustain_hours]  # defaults for DEFAULT_AS_PRODUCTS
REG_UP = 1.0
REG_DOWN = 1.0
RRS = 1.0
ECRS = 2.0
NONSPIN = 4.0
```

```python
from bess.backtest.as_runner import run_backtest_as
from bess.models import BatterySpec

result = run_backtest_as(prices_df, as_prices_df, battery)
result.total_revenue_usd     # energy leg + AS leg
result.as_revenue_usd
result.revenue_by_product    # pd.Series, index: product name
result.award_mw_hours        # pd.Series, index: product name
```

## Configuration

- `[ancillary].enabled`: run the co-opt backtest on every `bess backtest`
  invocation without passing `--ancillary`. Defaults to `false`.
- `[ancillary].products`: subset or reorder which of the five default AS
  products (`REG_UP`, `REG_DOWN`, `RRS`, `ECRS`, `NONSPIN`) to co-optimize.
  Unknown names raise. Defaults to all five, in `DEFAULT_AS_PRODUCTS` order.
- `[ancillary.sustain_hours]`: per-product sustain-duration override in
  hours; unset products fall back to `DEFAULT_AS_PRODUCTS`' defaults.

## Testing

```bash
uv run pytest
```

`tests/test_as_backtest_integration.py` covers all 10 M3c acceptance
criteria: the doctored-gap raise (naming the missing product and ISO
timestamp), the pre-launch ECRS mask on the 2023-03-12 spring-forward DST
fixture, metrics integrity (`energy_revenue_usd + as_revenue_usd ==
total_revenue_usd`, `revenue_by_product` sums to `as_revenue_usd`, all M1
fields finite), dominance of the co-opt total over the energy-only optimum,
the `[1.0, 8.0]` uplift sanity corridor on the July fixture, end-to-end CLI
behavior (`--ancillary` writes the qualified JSON, energy-only output stays
byte-identical), `bess benchmark`'s uplift/mix output and its graceful skip
when the ancillary file is absent, the `--ancillary --mode rolling` guard,
and determinism across two consecutive runs (excluding
`solve_time_seconds`). All tests run from `tests/fixtures/`; none touch the
network.

## Notes

The review (`specs/review_issues/review-d39c4d18.md`) passed. Two
non-blocking issues were noted for a future pass:

1. When `--ancillary` is active, `backtest` re-fetches `prices_df` a second
   time per location for `run_backtest_as`, even though the energy-only leg
   already loaded the identical cached parquet a few lines earlier. Correct
   but redundant I/O; worth threading the already-loaded frame through if
   `--ancillary` usage grows.
2. `revenue_mix` divides by `sum(revenue_by_product.values())` with no
   zero-guard. A window with exactly $0 total AS revenue across all
   products (a plausible LP-degeneracy edge case) would raise
   `ZeroDivisionError` inside `bess benchmark` instead of skipping cleanly.
   Not reachable on the current committed fixtures.

On the committed HB_NORTH July 2023 fixture, AS uplift is 2.7705x
(energy-only $970,937.15 vs co-optimized $2,689,961.68). `NONSPIN` earns
exactly $0.00 in that window: its 4-hour sustain-duration assumption is
structurally unaffordable for the 100 MW / 200 MWh (2-hour) default
battery, a real modeling consequence, not a bug. Per-product dollar figures
can shift under LP ties at identical total revenue, so the revenue-mix
table is a fixture illustration, not a precise attribution.

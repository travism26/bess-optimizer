# M3b: Energy + Ancillary-Service Co-optimization LP

**ADW ID:** 3034ec63
**Date:** 2026-08-01
**Specification:** specs/M3b_as_cooptimizer.md

## Overview

Implements `optimize_dispatch_as`, a second pure LP function that co-optimizes
energy dispatch with per-product ancillary-service (AS) capacity awards in a
single HiGHS solve. It sits alongside the frozen M1 `optimize_dispatch`
(untouched) and adds the `AsProduct`, `DEFAULT_AS_PRODUCTS`, and
`AsDispatchResult` contracts to `src/bess/models.py` per the M3 master spec.

## What Was Built

- `AsProduct` frozen dataclass: name, direction (`"up"` / `"down"`), and
  `sustain_hours` (energy adequacy duration backing a 1 MW award).
- `DEFAULT_AS_PRODUCTS`: the five ERCOT DAM products (`REG_UP`, `REG_DOWN`,
  `RRS`, `ECRS`, `NONSPIN`) with their default sustain hours (1.0 / 1.0 / 1.0
  / 2.0 / 4.0).
- `AsDispatchResult` frozen dataclass: wraps a `DispatchResult` (whose
  `objective_value` is the full co-optimized dollar figure), the echoed
  `products` row order, `awards_mw` (P, T), and the energy/AS revenue split.
- `optimize_dispatch_as(prices, as_prices, as_available, dt_hours, battery,
  products) -> AsDispatchResult` in the new `src/bess/optimizer/as_lp.py`
  module: one HiGHS solve with award variables `a_pt >= 0` added on top of
  the unchanged M1 charge/discharge/SoC variables and dynamics.
- Input validation: shape agreement between `as_prices` / `as_available` and
  `(len(products), len(prices))`; unknown direction strings raise
  `ValueError`.
- Golden tests (`tests/test_as_optimizer_golden.py`) and property tests
  (`tests/test_as_optimizer_properties.py`) covering all 10 acceptance
  criteria from the spec, including a synthetic 2-year / 5-product
  (T=17,520, ~122k variable) runtime budget test.
- `AsProduct`, `DEFAULT_AS_PRODUCTS`, `AsDispatchResult` exported from
  `bess.__init__`.

## Technical Implementation

### Files Modified

- `src/bess/models.py`: added `AsProduct`, `DEFAULT_AS_PRODUCTS`,
  `AsDispatchResult` (additive only, no changes to the frozen M1 dataclasses).
- `src/bess/optimizer/as_lp.py` (new): `optimize_dispatch_as` and its private
  `_validate_as_inputs` / `_build_as_lp` helpers.
- `src/bess/__init__.py`: re-exports the three new model classes.
- `tests/test_as_optimizer_golden.py` (new): five hand-derived golden
  objectives plus the masked/zero-price equivalence checks (AC 1-5).
- `tests/test_as_optimizer_properties.py` (new): solver status, SoC/power
  bounds, constraint residuals, revenue decomposition, dominance over
  energy-only, product-order-shuffle invariance, runtime budget, validation
  error paths, and an import-allowlist guard (AC 6-10).
- `ai_docs/research/3034ec63-m3b-as-cooptimizer-analysis.md` (new): research
  notes backing the implementation.

### Key Changes

- **Single LP, added columns/rows.** The column layout is `[c_0..c_{T-1},
  d_0..d_{T-1}, s_0..s_{T-1}, a_0_0..a_0_{T-1}, ..., a_{P-1}_0..a_{P-1}_{T-1}]`
  (award columns grouped by product, row-ordered by `products`); the row
  layout adds `up coupling`, `down coupling`, `up adequacy`, and `down room
  adequacy` (each length T) after the unchanged M1 `dynamics` block. The
  dynamics recursion is byte-for-byte identical to `optimizer/lp.py`'s
  `_build_lp`, and award columns carry a zero coefficient there so awards
  never move SoC.
- **Three pinned conventions**, all locked in by golden tests: adequacy uses
  end-of-interval SoC (matching `DispatchResult`'s convention); awards may
  exceed `power_mw` while charging (real swing capability via the coupling
  constraint, not capped); awards are capacity-only payments (deployment,
  performance, and mileage payments are out of scope).
- **Availability as a bound, not a constraint row.** `as_available[p, t] ==
  False` is implemented as a zero upper bound on that award column, avoiding
  an extra row per masked interval.
- **Built via raw CSC arrays**, not the high-level `Highs()` API, which is
  what keeps the T=17,520 / P=5 (~122k variable) solve inside the 60-second
  runtime budget (AC 10).
- Revenue is decomposed post-solve as `energy_revenue_usd = sum_t p_t *
  (d_t - c_t) * dt` and `as_revenue_usd = sum_{p,t} q_pt * a_pt * dt`; both
  are asserted to reconstruct `dispatch.objective_value`.
- Degenerate awards (zero MCPC, or ties on marginal adequacy/coupling value)
  are explicitly out of scope for exact assertions; only revenue and
  constraint residuals are asserted outside the five strict goldens.

## Usage

`optimize_dispatch_as` is a library function, not yet wired into the CLI
(`bess backtest` / `bess fetch` remain M3c scope). It is called directly from
Python or tests:

### Examples

```python
import numpy as np
from bess.models import DEFAULT_AS_PRODUCTS, BatterySpec
from bess.optimizer.as_lp import optimize_dispatch_as

battery = BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)
products = DEFAULT_AS_PRODUCTS

prices = np.zeros(24)                                    # $/MWh, shape (T,)
as_prices = np.full((len(products), 24), 10.0)            # $/MW-h MCPC, shape (P, T)
as_available = np.ones((len(products), 24), dtype=bool)   # shape (P, T)

result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

result.dispatch.objective_value   # full co-optimized $ (energy + AS)
result.energy_revenue_usd         # energy leg only
result.as_revenue_usd             # AS leg only
result.awards_mw                  # shape (P, T), row order == `products`
```

```bash
uv run bess fetch --config config.toml      # pull + cache ERCOT DA prices (network, manual only)
uv run bess backtest --config config.toml   # metrics JSON + plots from cache (no network)
uv run bess plot                            # re-render PNGs from a backtest output
```

## Configuration

No new configuration surface. `products` and `as_available`/`as_prices`
matrices are passed in by the caller; `DEFAULT_AS_PRODUCTS` supplies the
standard five-product ordering when a caller does not need a custom set.

## Testing

```bash
uv run pytest tests/test_as_optimizer_golden.py tests/test_as_optimizer_properties.py
uv run pytest      # full suite
uv run ruff check .
uv run mypy
```

## Notes

- `optimizer/lp.py` and `optimize_dispatch` are untouched; this is purely
  additive, mirroring the M1 formulation rather than modifying it.
- The module's import list is restricted to `numpy`, `highspy`, and
  `bess.models` (plus stdlib `logging`), enforced by a test that parses the
  module's AST; this keeps the M4 Rust port's purity boundary intact.
- Cycle-cap (`max_cycles_per_day`) enforcement remains out of scope, same as
  M1.
- MILP exclusivity for simultaneous charge/discharge is explicitly deferred;
  `simultaneous_hours` is still reported and logged, never raised.
- Backtest/CLI wiring for AS revenue (M3c) and rolling-horizon AS are out of
  scope for this slice.

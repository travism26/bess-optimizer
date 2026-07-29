# LP Dispatch Optimizer (M1b)

**ADW ID:** 3b9cf1a9
**Date:** 2026-07-29
**Specification:** specs/M1b_optimizer.md

## Overview

Implements `optimize_dispatch`, the perfect-foresight battery arbitrage LP
that serves as the correctness oracle for the later M4 Rust engine. Given a
price array and a `BatterySpec`, it solves for the revenue-maximizing
charge/discharge/SoC schedule via HiGHS (`highspy`) and returns a
`DispatchResult`, exactly as frozen in `specs/M1_python_core.md`.

## What Was Built

- `optimize_dispatch(prices, dt_hours, battery) -> DispatchResult` in
  `src/bess/optimizer/lp.py`, solving the LP formulation from the master spec
  exactly: charge/discharge/SoC decision variables, the SoC recursion with
  split charge/discharge efficiency, power and SoC bounds, and no terminal
  SoC constraint.
- A hand-vectorized, column-wise sparse `HighsLp` builder (`_build_lp`) that
  constructs the CSC arrays directly with numpy instead of adding rows/columns
  one at a time through the high-level `Highs()` API, keeping a T=17,520 solve
  well inside the 30-second runtime budget.
- Non-optimal solver status raises `RuntimeError` with the HiGHS status
  string included.
- Simultaneous charge/discharge detection (threshold 1e-3 MW), reported via
  `DispatchResult.simultaneous_hours` and logged as a `WARNING`, never raised.
- 4 golden tests (`tests/test_optimizer_golden.py`) and 7 property/behavior
  tests plus an AST-based import purity test (`tests/test_optimizer_properties.py`),
  covering all 11 acceptance criteria in the spec.

## Technical Implementation

### Files Modified

- `src/bess/optimizer/lp.py`: implemented `optimize_dispatch` and the private
  `_build_lp` helper; added a module-level logger.
- `tests/test_optimizer_golden.py`: implemented the 4 golden cases (flat
  prices, lossless step, lossy-charge step, negative-price hour).
- `tests/test_optimizer_properties.py`: implemented property tests on 3 seeded
  random price series, the simultaneous charge/discharge behavior test, the
  T=17,520 runtime budget test, and the import-allowlist purity test.

### Key Changes

- **Column layout:** decision variables are laid out as a single flat vector
  `[c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]` (charge, then discharge, then
  SoC), with one row per interval `t` encoding the SoC recursion
  `s_t - s_{t-1} + charge_eff * c_t * dt - (d_t * dt) / discharge_eff = 0`, and
  the first row pinning `s_{-1}` to `battery.initial_soc_mwh` via equal lower
  and upper row bounds.
- **Objective:** `col_cost_` is `[-prices * dt, prices * dt, 0...]` with
  `sense_ = kMaximize`, so charging costs `price * dt` and discharging earns
  it, matching `sum_t p_t * (d_t - c_t) * dt` from the spec.
- **No terminal SoC constraint:** the final SoC column is left unconstrained
  by design (see docstring); a rolling-horizon caller is expected to re-solve
  with a fresh `initial_soc_mwh` rather than rely on a terminal target here.
- **`max_cycles_per_day` is accepted but ignored** in M1, per the spec's
  explicit out-of-scope list; the field exists on `BatterySpec` for later
  milestones only.
- **Purity enforced by test, not just docstring:** `test_lp_module_imports_are_restricted_to_the_purity_allowlist`
  parses `lp.py`'s AST and asserts its top-level imports are a subset of
  `{numpy, highspy, bess.models, logging, __future__}`.

## Usage

`optimize_dispatch` is a library function, not a CLI command; it is called
directly or via the (not-yet-implemented) `run_backtest` in
`src/bess/backtest/runner.py`.

### Examples

```python
import numpy as np
from bess.models import BatterySpec
from bess.optimizer.lp import optimize_dispatch

prices = np.array([10.0] * 12 + [100.0] * 12)  # $/MWh, T=24
battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=1.0, discharge_eff=1.0)

result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

result.objective_value      # 180.0 ($ revenue)
result.solver_status        # "optimal"
result.simultaneous_hours   # 0
result.charge_mw            # shape (24,)
result.discharge_mw         # shape (24,)
result.soc_mwh              # shape (24,), end-of-interval SoC
```

## Configuration

No new configuration. Battery parameters come from `BatterySpec`
(`src/bess/models.py`); the default config (100 MW / 200 MWh, 0.927 each-way
efficiency) lives in `config.toml` and is used by the property tests.

## Testing

```bash
uv run pytest tests/test_optimizer_golden.py tests/test_optimizer_properties.py
uv run ruff check src/bess/optimizer/lp.py
uv run mypy
```

All 11 acceptance criteria from `specs/M1b_optimizer.md` are covered:
4 golden cases (objective values exact to 1e-6), 5 property checks on 3
seeded random series (SoC bounds, SoC dynamics residual, independently
recomputed revenue, power limits), the simultaneous charge/discharge
behavior case, and the T=17,520 runtime budget (observed ~0.2s, well under
the 30s budget).

## Notes

- Cycle caps, rolling horizon, and MILP charge/discharge exclusivity remain
  out of scope for M1, matching the spec.
- `run_backtest` in `src/bess/backtest/runner.py` still raises
  `NotImplementedError`; wiring `optimize_dispatch` into a full backtest is a
  separate milestone.
- The code review for this task (`specs/review_issues/review-3b9cf1a9.md`)
  passed with one skippable, unrelated issue: a stray modification to
  `.ports.env` (ADW worktree port bookkeeping, not part of this feature).

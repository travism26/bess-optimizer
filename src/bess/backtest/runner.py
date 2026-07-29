"""Backtest runner producing revenue metrics per hub.

Bridges the canonical price DataFrame world to the pure-array optimizer world.
The optimizer parameter exists so the M4 Rust implementation drops in unchanged.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from bess.models import BacktestResult, BatterySpec, DispatchResult
from bess.optimizer.lp import optimize_dispatch


def run_backtest(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> BacktestResult:
    """Run a full-horizon perfect-foresight backtest for a single location.

    Intended behavior:
    - prices_df is canonical schema, one location, validated (sorted, gap-free).
    - Extract the price array and dt, call optimizer(prices, dt_hours, battery),
      and time the solve (recorded as solve_time_seconds, acceptance criterion 7).
    - Compute BacktestResult metrics: total revenue, revenue per MW-year,
      revenue per MWh discharged, total MWh discharged, equivalent full cycles
      (discharged MWh / energy_mwh), daily revenue series, and total
      simultaneous_hours.

    Covered by acceptance criteria: 7 (runtime budget recorded in metrics) and
    8 (CLI end-to-end produces metrics JSON), tested in
    tests/test_backtest_integration.py.
    """
    raise NotImplementedError

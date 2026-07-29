"""Backtest runner producing revenue metrics per hub.

Bridges the canonical price DataFrame world to the pure-array optimizer world.
The optimizer parameter exists so the M4 Rust implementation drops in unchanged.

`run_backtest` is the frozen entry point (specs/M1_python_core.md). It is
built on top of two smaller, non-frozen helpers, `solve_dispatch` and
`metrics_from_dispatch`, so that a caller that also needs the raw
`DispatchResult` for plotting (the CLI's `backtest` and `plot` commands) can
solve each location exactly once instead of paying for the LP twice.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np
import pandas as pd

from bess.models import BacktestResult, BatterySpec, DispatchResult
from bess.optimizer.lp import optimize_dispatch

# Standard hours in a calendar year, used only as the annualization scale for
# revenue_per_mw_year. The value actually divided out is the observed window
# length computed from prices_df's own timestamps (spec gotcha 1), never a
# hardcoded assumption that the window itself spans exactly one year.
_HOURS_PER_YEAR = 8760.0


def _single_location(prices_df: pd.DataFrame) -> str:
    locations = prices_df["location"].unique()
    if len(locations) != 1:
        raise ValueError(
            f"run_backtest expects a single-location price frame, got {list(locations)}"
        )
    return str(locations[0])


def _price_series_and_dt(prices_df: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Extract the price array and dt_hours from a canonical-schema frame.

    dt_hours is derived from the first row's interval width rather than
    hardcoded to 1.0, so this keeps working if a future ISO's canonical
    schema uses a different (but still uniform) settlement interval.
    """
    prices = prices_df["price"].to_numpy(dtype=np.float64)
    dt_hours = (
        prices_df["interval_end_utc"].iloc[0] - prices_df["interval_start_utc"].iloc[0]
    ).total_seconds() / 3600.0
    return prices, dt_hours


def solve_dispatch(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> tuple[DispatchResult, float]:
    """Solve one location's full horizon and time the solve.

    Returns the raw DispatchResult alongside the wall-clock solve time in
    seconds (acceptance criterion 7), so callers that also need per-interval
    dispatch for plotting can reuse this single solve rather than calling
    run_backtest and re-solving.
    """
    prices, dt_hours = _price_series_and_dt(prices_df)

    started = time.perf_counter()
    result = optimizer(prices, dt_hours, battery)
    solve_time_seconds = time.perf_counter() - started
    return result, solve_time_seconds


def metrics_from_dispatch(
    location: str,
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    dispatch: DispatchResult,
    solve_time_seconds: float,
) -> BacktestResult:
    """Compute BacktestResult metrics from an already-solved DispatchResult.

    total_revenue_usd is the solver's own objective_value (the DispatchResult
    contract defines it as "$ revenue from the solver"); recomputing revenue
    independently from (prices, charge, discharge) and checking it matches
    within 1e-4 is a correctness property exercised in
    tests/test_backtest_integration.py, not a step performed here.

    revenue_per_mw_year annualizes total_revenue_usd using the *actual*
    window length (interval_end_utc of the last row minus interval_start_utc
    of the first), never a hardcoded 8760-hour year (spec gotcha 1);
    _HOURS_PER_YEAR is only the annualization scale, not the divisor.

    daily_revenue groups per-interval revenue by the UTC calendar date of
    interval_start_utc. This is UTC days, not the market's local (e.g.
    Central) trading day, chosen so this module needs no ISO-specific
    timezone knowledge (spec gotcha 2 requires picking one and documenting
    it; timezone handling otherwise lives only in bess.data.prices).
    """
    prices, dt_hours = _price_series_and_dt(prices_df)

    total_revenue_usd = float(dispatch.objective_value)

    discharged_mwh = dispatch.discharge_mw * dt_hours
    total_discharged_mwh = float(discharged_mwh.sum())

    window_hours = (
        prices_df["interval_end_utc"].iloc[-1] - prices_df["interval_start_utc"].iloc[0]
    ).total_seconds() / 3600.0
    revenue_per_mw_year = total_revenue_usd / battery.power_mw * (_HOURS_PER_YEAR / window_hours)
    revenue_per_mwh_discharged = (
        total_revenue_usd / total_discharged_mwh if total_discharged_mwh > 0 else 0.0
    )
    equivalent_full_cycles = total_discharged_mwh / battery.energy_mwh

    interval_revenue = prices * (dispatch.discharge_mw - dispatch.charge_mw) * dt_hours
    daily_revenue = (
        pd.Series(interval_revenue, index=prices_df["interval_start_utc"].dt.date)
        .groupby(level=0)
        .sum()
    )
    daily_revenue.index.name = "date"

    return BacktestResult(
        location=location,
        total_revenue_usd=total_revenue_usd,
        revenue_per_mw_year=revenue_per_mw_year,
        revenue_per_mwh_discharged=revenue_per_mwh_discharged,
        total_discharged_mwh=total_discharged_mwh,
        equivalent_full_cycles=equivalent_full_cycles,
        daily_revenue=daily_revenue,
        simultaneous_hours=dispatch.simultaneous_hours,
        solve_time_seconds=solve_time_seconds,
    )


def run_backtest(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> BacktestResult:
    """Run a full-horizon perfect-foresight backtest for a single location.

    prices_df must be canonical schema (bess.data.prices.CANONICAL_COLUMNS)
    for exactly one location; it is not re-validated here (bess.data.prices
    already validates on every fetch_da_prices return path). optimizer
    defaults to the real LP but is fully injectable: this module never
    assumes which implementation it received, which is what lets the M4 Rust
    engine drop in unchanged.

    Covered by acceptance criteria: 7 (runtime budget recorded in metrics),
    8 (CLI end-to-end produces metrics JSON), and the M1c injected-optimizer
    contract, tested in tests/test_backtest_integration.py.
    """
    location = _single_location(prices_df)
    dispatch, solve_time_seconds = solve_dispatch(prices_df, battery, optimizer)
    return metrics_from_dispatch(location, prices_df, battery, dispatch, solve_time_seconds)

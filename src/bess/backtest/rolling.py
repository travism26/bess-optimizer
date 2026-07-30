"""Rolling-horizon backtest: commit one market day at a time, carry SoC.

specs/M2a_rolling_horizon.md, mechanics defined in specs/M2_rolling_and_benchmarks.md
("Rolling mechanics"). M1's `run_backtest` sees every price in the horizon at once,
an unrealistic upper bound. This module instead re-solves once per local market day
over a short window (the real day plus `lookahead_days` of forecast), commits only
that day's dispatch, and carries the committed end-of-day SoC into the next day's
solve. The result is scored with the exact same `metrics_from_dispatch` code path
M1 uses, on the committed series only, so perfect and rolling results stay directly
comparable field by field.

`run_backtest_rolling` is the frozen entry point (specs/M2_rolling_and_benchmarks.md,
"Frozen interfaces"). Like `run_backtest`, it is built on top of a non-frozen helper,
`solve_rolling_dispatch`, which exposes the raw committed `DispatchResult` for callers
(and tests) that need per-interval charge/discharge/SoC rather than only the scored
`BacktestResult`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from bess.backtest.runner import _price_series_and_dt, _single_location, metrics_from_dispatch
from bess.models import BacktestResult, BatterySpec, DispatchResult
from bess.optimizer.lp import optimize_dispatch

_MARKET_TZ = "America/Chicago"

# Matches DispatchResult.simultaneous_hours' contract (bess.models): "count of t
# where both charge and discharge > 1e-3 MW". Recomputed here because the composite
# DispatchResult built below is stitched together from committed day-slices, never
# from one solver call, so there is no single DispatchResult.simultaneous_hours to
# reuse directly.
_SIMULTANEOUS_THRESHOLD_MW = 1e-3

_FORECAST_MODES = ("persistence", "perfect")


@dataclass(frozen=True)
class RollingConfig:
    """Rolling-horizon parameters (specs/M2_rolling_and_benchmarks.md, frozen).

    lookahead_days: number of forecast market days appended after the commit
    day in each solve window.
    forecast: "persistence" (headline) reuses the commit day's own prices,
    mapped by local hour-of-day, as the stand-in for each lookahead day;
    "perfect" (diagnostic) uses the lookahead day's actual future prices.
    """

    lookahead_days: int = 1
    forecast: str = "persistence"


def _local_market_day(timestamps: pd.Series) -> np.ndarray:
    """One America/Chicago calendar date per row, as an object array."""
    return np.asarray(timestamps.dt.tz_convert(_MARKET_TZ).dt.date)


def _local_hour_of_day(timestamps: pd.Series) -> np.ndarray:
    """One America/Chicago wall-clock hour (0-23) per row.

    Computed from local time, not array position: a spring-forward day shifts
    every later row's array position by one hour relative to a normal day, so
    positional mapping would silently misalign a persistence forecast (spec
    gotcha 2). A fall-back day's duplicated local hour keeps both rows' hour
    value equal, which is exactly what the persistence mapping needs to reuse
    the same source price for both.
    """
    return np.asarray(timestamps.dt.tz_convert(_MARKET_TZ).dt.hour)


def _day_blocks(market_day: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split a sorted local-market-day array into contiguous per-day blocks.

    Returns (days, block_starts, block_ends): one entry per market day, in
    order, with block_ends exclusive. A local calendar day's rows are always
    contiguous in UTC-sorted order (a fixed local-to-UTC offset applies for
    all but the DST-transition instant itself), so a single pass over
    day-to-day changes is enough; no need to group and re-sort.
    """
    block_starts = np.flatnonzero(np.r_[True, market_day[1:] != market_day[:-1]])
    block_ends = np.r_[block_starts[1:], len(market_day)]
    return market_day[block_starts], block_starts, block_ends


def _persistence_forecast(
    source_hours: np.ndarray, source_prices: np.ndarray, target_hours: np.ndarray
) -> np.ndarray:
    """Map one market day's prices onto another day's rows by local hour-of-day.

    Builds an hour-of-day -> price lookup from the source day (keeping the
    first occurrence if the source itself is a 25-hour fall-back day, and
    forward/back-filling the one missing hour if the source is a 23-hour
    spring-forward day), then reads it back out in the target day's hour
    order. A 25-hour target day naturally gets the same source price at both
    of its duplicated-hour rows; a 23-hour target day naturally never looks up
    the local hour it skips.
    """
    by_hour = pd.Series(source_prices, index=source_hours)
    by_hour = by_hour[~by_hour.index.duplicated(keep="first")]
    by_hour = by_hour.reindex(range(24)).ffill().bfill()
    return by_hour.loc[target_hours].to_numpy(dtype=np.float64)


def solve_rolling_dispatch(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    config: RollingConfig,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> tuple[DispatchResult, float]:
    """Run the rolling-horizon loop and return the stitched committed DispatchResult.

    For each local market day d, solves [day d's real prices] + [the next
    config.lookahead_days market days' forecast prices] with the injected
    optimizer, initial SoC carried from the previous day's committed ending
    SoC (day one uses battery.initial_soc_mwh). Only day d's portion of the
    solved window is committed; the lookahead days exist solely to inform
    that one decision and are re-solved (not reused) on the next iteration.
    The lookahead truncates at the end of prices_df for both forecast
    variants, so the final market day in range is always solved alone.

    Returns the full-horizon committed DispatchResult (one entry per row of
    prices_df, exactly once) alongside the total wall-clock solve time across
    all windows, mirroring bess.backtest.runner.solve_dispatch's contract so
    callers needing per-interval detail (tests, future plotting) don't have
    to re-solve.

    Raises:
        ValueError: if config.forecast is not "persistence" or "perfect".
        RuntimeError: if any window's optimizer does not report solver_status
            "optimal"; the message names that window's market day.
    """
    if config.forecast not in _FORECAST_MODES:
        raise ValueError(
            f"RollingConfig.forecast must be one of {_FORECAST_MODES}, got {config.forecast!r}"
        )

    prices, dt_hours = _price_series_and_dt(prices_df)
    local_hour = _local_hour_of_day(prices_df["interval_start_utc"])
    market_day = _local_market_day(prices_df["interval_start_utc"])
    days, block_starts, block_ends = _day_blocks(market_day)
    num_days = len(days)

    committed_charge = np.full(len(prices_df), np.nan)
    committed_discharge = np.full(len(prices_df), np.nan)
    committed_soc = np.full(len(prices_df), np.nan)

    carried_soc = battery.initial_soc_mwh
    started = time.perf_counter()
    for i in range(num_days):
        commit_slice = slice(block_starts[i], block_ends[i])
        commit_prices = prices[commit_slice]
        commit_hours = local_hour[commit_slice]

        window_price_parts = [commit_prices]
        lookahead_end = min(i + config.lookahead_days + 1, num_days)
        for j in range(i + 1, lookahead_end):
            lookahead_slice = slice(block_starts[j], block_ends[j])
            if config.forecast == "perfect":
                window_price_parts.append(prices[lookahead_slice])
            else:
                window_price_parts.append(
                    _persistence_forecast(commit_hours, commit_prices, local_hour[lookahead_slice])
                )
        window_prices = np.concatenate(window_price_parts)

        window_battery = replace(battery, initial_soc_mwh=carried_soc)
        dispatch = optimizer(window_prices, dt_hours, window_battery)
        if dispatch.solver_status != "optimal":
            raise RuntimeError(
                f"Rolling window committing market day {days[i]} did not solve to "
                f"optimality: status={dispatch.solver_status!r}"
            )

        commit_len = block_ends[i] - block_starts[i]
        committed_charge[commit_slice] = dispatch.charge_mw[:commit_len]
        committed_discharge[commit_slice] = dispatch.discharge_mw[:commit_len]
        committed_soc[commit_slice] = dispatch.soc_mwh[:commit_len]
        carried_soc = float(dispatch.soc_mwh[commit_len - 1])
    solve_time_seconds = time.perf_counter() - started

    simultaneous_hours = int(
        np.count_nonzero(
            (committed_charge > _SIMULTANEOUS_THRESHOLD_MW)
            & (committed_discharge > _SIMULTANEOUS_THRESHOLD_MW)
        )
    )
    total_revenue = float(np.sum(prices * (committed_discharge - committed_charge) * dt_hours))

    committed_dispatch = DispatchResult(
        charge_mw=committed_charge,
        discharge_mw=committed_discharge,
        soc_mwh=committed_soc,
        objective_value=total_revenue,
        solver_status="optimal",
        simultaneous_hours=simultaneous_hours,
    )
    return committed_dispatch, solve_time_seconds


def run_backtest_rolling(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    config: RollingConfig,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> BacktestResult:
    """Rolling-horizon backtest: commit one market day at a time, carry SoC.

    Re-solves once per local market day (America/Chicago) over a window of
    that day's real prices plus config.lookahead_days of forecast (see
    RollingConfig and solve_rolling_dispatch for the exact mechanics), commits
    only the current day, and carries its ending SoC into the next day's
    initial SoC. The window truncates at the end of prices_df's range for
    both forecast variants, so the final market day is always optimized
    alone. The committed series is scored with
    bess.backtest.runner.metrics_from_dispatch, the same code path
    run_backtest uses, so perfect- and rolling-mode BacktestResults are
    directly comparable field by field (specs/M2_rolling_and_benchmarks.md,
    "Rolling mechanics").

    prices_df must be canonical schema (bess.data.prices.CANONICAL_COLUMNS)
    for exactly one location, already validated by its producer. optimizer is
    injected per window so the M4 Rust engine drops into rolling mode
    unchanged, same seam as run_backtest.
    """
    location = _single_location(prices_df)
    dispatch, solve_time_seconds = solve_rolling_dispatch(prices_df, battery, config, optimizer)
    return metrics_from_dispatch(location, prices_df, battery, dispatch, solve_time_seconds)

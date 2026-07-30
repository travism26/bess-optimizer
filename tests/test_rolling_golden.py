"""Golden-value tests for run_backtest_rolling (M2a acceptance criteria 1, 2, 7).

No network; DST cases reuse the M1a raw DST fixtures already committed under
tests/fixtures/ (spring-forward 2023-03-12, fall-back 2023-11-05).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bess.backtest.rolling import RollingConfig, run_backtest_rolling, solve_rolling_dispatch
from bess.backtest.runner import run_backtest
from bess.data.prices import _canonicalize
from bess.models import BatterySpec, DispatchResult
from bess.optimizer.lp import optimize_dispatch

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
SPRING_FORWARD_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_03_12_raw.parquet"
FALL_BACK_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_11_05_raw.parquet"

_LOCATION = "HB_NORTH"


def _synthetic_day(
    local_date: date, prices: Sequence[float], location: str = _LOCATION
) -> pd.DataFrame:
    """One local market day of canonical-schema rows, hand-built (no fetch/cache).

    Hours are placed by local wall-clock time (America/Chicago), so this
    reproduces a normal day's structure exactly; DST-transition days are built
    from the real raw fixtures via _canonicalize instead, since a spring-
    forward or fall-back day's precise hour structure is what those fixtures
    exist to pin down.
    """
    start_utc = pd.Timestamp(local_date, tz="America/Chicago").tz_convert("UTC")
    starts = pd.Series(pd.date_range(start_utc, periods=len(prices), freq="h"))
    ends = starts + pd.Timedelta(1, unit="h")
    return pd.DataFrame(
        {
            "interval_start_utc": starts.astype("datetime64[us, UTC]"),
            "interval_end_utc": ends.astype("datetime64[us, UTC]"),
            "iso": "ERCOT",
            "market": "DAY_AHEAD_HOURLY",
            "location": location,
            "location_type": "Trading Hub",
            "price": np.asarray(prices, dtype=np.float64),
        }
    )


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def test_two_day_foresight_golden_perfect_vs_persistence() -> None:
    """AC-1: 48h, day 1 flat $50, day 2 has a $200 spike at its first two hours.

    Battery 1 MW / 2 MWh, charge_eff 0.8, discharge_eff 1.0, initial SoC 0,
    lookahead_days 1.

    forecast="perfect": the day-1 window sees the real day-2 spike, so it is
    worth losing money on the lossy charge to reach it: charge 2.5 MWh from
    the grid at $50 (cost $125) on day 1, discharge the resulting 2 MWh at
    $200 on day 2 (revenue $400). Committed revenue == 275.0, matching M1
    optimize_dispatch on the same 48h vector run directly.

    forecast="persistence": the day-1 window instead sees a flat $50
    tomorrow (day 1's own prices, persisted), so any position strictly loses
    through the lossy charge and day 1 commits nothing. Day 2 is then solved
    alone from SoC 0, and its spike is at hours 0-1: with no stored energy
    and no cheaper hours before it within day 2, the spike is unreachable.
    Committed revenue == 0.0.
    """
    day1_prices = [50.0] * 24
    day2_prices = [200.0, 200.0] + [50.0] * 22
    prices_df = pd.concat(
        [
            _synthetic_day(date(2023, 7, 1), day1_prices),
            _synthetic_day(date(2023, 7, 2), day2_prices),
        ],
        ignore_index=True,
    )
    battery = BatterySpec(
        power_mw=1.0, energy_mwh=2.0, charge_eff=0.8, discharge_eff=1.0, initial_soc_mwh=0.0
    )

    full_horizon_prices = np.array(day1_prices + day2_prices)
    m1_result = optimize_dispatch(full_horizon_prices, dt_hours=1.0, battery=battery)
    assert m1_result.objective_value == pytest.approx(275.0, abs=1e-6)

    perfect = run_backtest_rolling(
        prices_df, battery, RollingConfig(lookahead_days=1, forecast="perfect")
    )
    assert perfect.total_revenue_usd == pytest.approx(275.0, abs=1e-6)
    assert perfect.total_revenue_usd == pytest.approx(m1_result.objective_value, abs=1e-6)

    persistence = run_backtest_rolling(
        prices_df, battery, RollingConfig(lookahead_days=1, forecast="persistence")
    )
    assert persistence.total_revenue_usd == pytest.approx(0.0, abs=1e-6)


def test_equivalence_golden_full_lookahead_perfect_matches_m1() -> None:
    """AC-2: on the July 2023 fixture, rolling with forecast="perfect" and a
    lookahead long enough to always reach the end of the range (>= 31 market
    days) reproduces the M1 perfect-foresight total, within $0.01.

    Every day's window then covers all remaining days with real (not
    forecast) prices, so re-solving day by day with the correct carried SoC
    reconstructs the same globally optimal schedule the one-shot M1 solve
    finds (a re-solve from any state along an optimal trajectory, given
    perfect information about everything remaining, stays optimal).
    """
    prices_df = pd.read_parquet(JULY_FIXTURE)
    battery = _default_battery()

    perfect_m1 = run_backtest(prices_df, battery)
    rolling_full_lookahead = run_backtest_rolling(
        prices_df, battery, RollingConfig(lookahead_days=31, forecast="perfect")
    )

    assert rolling_full_lookahead.total_revenue_usd == pytest.approx(
        perfect_m1.total_revenue_usd, abs=0.01
    )


def test_dst_spring_forward_commit_window_has_23_committed_hours() -> None:
    """AC-7: 2023-03-12 (spring forward) as the commit day.

    A stub optimizer records each window's length: the window committing
    2023-03-11 (normal, 24h) sees 2023-03-12 (23h) as its lookahead, total
    47; the window committing 2023-03-12 itself sees 2023-03-13 (normal,
    24h) as its lookahead, also total 47 but with only 23 real committed
    hours; the final window (2023-03-13, end of range) is solved alone, 24.
    """
    raw = pd.read_parquet(SPRING_FORWARD_RAW_FIXTURE)
    spring_forward_day = _canonicalize(raw, date(2023, 3, 12), date(2023, 3, 12))
    assert len(spring_forward_day) == 23

    prices_df = pd.concat(
        [
            _synthetic_day(date(2023, 3, 11), [40.0] * 24),
            spring_forward_day,
            _synthetic_day(date(2023, 3, 13), [40.0] * 24),
        ],
        ignore_index=True,
    )
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=0.9, discharge_eff=0.9)
    window_lengths: list[int] = []

    def recording_stub(prices: np.ndarray, dt_hours: float, battery: BatterySpec) -> DispatchResult:
        window_lengths.append(len(prices))
        horizon = len(prices)
        return DispatchResult(
            charge_mw=np.zeros(horizon),
            discharge_mw=np.zeros(horizon),
            soc_mwh=np.zeros(horizon),
            objective_value=0.0,
            solver_status="optimal",
            simultaneous_hours=0,
        )

    dispatch, _ = solve_rolling_dispatch(
        prices_df,
        battery,
        RollingConfig(lookahead_days=1, forecast="persistence"),
        optimizer=recording_stub,
    )

    assert window_lengths == [24 + 23, 23 + 24, 24]
    # The spring-forward day's own committed slice is exactly its 23 real hours.
    assert len(dispatch.charge_mw[24 : 24 + 23]) == 23


def test_dst_fall_back_lookahead_day_duplicated_hour_reuses_source_price() -> None:
    """AC-7: persistence forecast onto a 25-hour fall-back lookahead day.

    2023-11-04 (normal, distinct price per hour) commits with 2023-11-05
    (fall back, 25h) as its persistence lookahead. 2023-11-05's local hour 1
    is duplicated (it occurs at both 1 CDT and 1 CST); the persistence
    mapping must place the same source (2023-11-04, hour 1) price at both
    positions, never the array-position-shifted source price gotcha 2 warns
    about.
    """
    raw = pd.read_parquet(FALL_BACK_RAW_FIXTURE)
    fall_back_day = _canonicalize(raw, date(2023, 11, 5), date(2023, 11, 5))
    assert len(fall_back_day) == 25
    local_hours = fall_back_day["interval_start_utc"].dt.tz_convert("America/Chicago").dt.hour
    duplicated_positions = np.flatnonzero(local_hours.to_numpy() == 1)
    assert list(duplicated_positions) == [1, 2]

    commit_day_prices = [10.0 + h for h in range(24)]
    prices_df = pd.concat(
        [
            _synthetic_day(date(2023, 11, 4), commit_day_prices),
            fall_back_day,
            _synthetic_day(date(2023, 11, 6), [40.0] * 24),
        ],
        ignore_index=True,
    )
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=0.9, discharge_eff=0.9)
    windows: list[np.ndarray] = []

    def recording_stub(prices: np.ndarray, dt_hours: float, battery: BatterySpec) -> DispatchResult:
        windows.append(np.asarray(prices))
        horizon = len(prices)
        return DispatchResult(
            charge_mw=np.zeros(horizon),
            discharge_mw=np.zeros(horizon),
            soc_mwh=np.zeros(horizon),
            objective_value=0.0,
            solver_status="optimal",
            simultaneous_hours=0,
        )

    solve_rolling_dispatch(
        prices_df,
        battery,
        RollingConfig(lookahead_days=1, forecast="persistence"),
        optimizer=recording_stub,
    )

    first_window = windows[0]
    assert len(first_window) == 24 + 25
    lookahead_part = first_window[24:]
    source_hour1_price = commit_day_prices[1]
    assert lookahead_part[1] == pytest.approx(source_hour1_price)
    assert lookahead_part[2] == pytest.approx(source_hour1_price)

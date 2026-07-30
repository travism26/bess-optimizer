"""Property, behavior, and CLI tests for run_backtest_rolling (M2a acceptance
criteria 3-6 and 8-10).

Properties run on the real HB_NORTH July 2023 fixture (committed by M1a),
default battery, lookahead_days=1, both forecast variants; no network (the
conftest guard enforces this).
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from bess.backtest.rolling import RollingConfig, run_backtest_rolling, solve_rolling_dispatch
from bess.backtest.runner import metrics_from_dispatch, run_backtest
from bess.cli import _metrics_dict, app
from bess.data.prices import _cache_path
from bess.models import BatterySpec, DispatchResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
LOCATION = "HB_NORTH"
FIXTURE_START = date(2023, 7, 1)
FIXTURE_END = date(2023, 7, 31)

_FORECASTS = ("persistence", "perfect")


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _july_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_FIXTURE)


def _rolling_config(forecast: str) -> RollingConfig:
    return RollingConfig(lookahead_days=1, forecast=forecast)


@pytest.mark.parametrize("forecast", _FORECASTS)
def test_rolling_backtest_solves_every_window_optimally(forecast: str) -> None:
    """AC-3 (success path): the real optimizer reaches "optimal" for every
    market day window in the fixture month, for both forecast variants (no
    RuntimeError raised).
    """
    result = run_backtest_rolling(_july_prices_df(), _default_battery(), _rolling_config(forecast))

    # No RuntimeError means every one of the 31 daily windows reported "optimal";
    # a finite revenue confirms the composite result was actually built from them.
    assert np.isfinite(result.total_revenue_usd)


def test_non_optimal_window_status_raises_with_window_market_day() -> None:
    """AC-3 (failure path): an injected optimizer reporting a non-optimal
    status must raise, naming the window's market day, rather than silently
    propagating a bad DispatchResult. The real HiGHS-backed optimizer always
    raises internally before this point, so this only matters for an
    injected optimizer (e.g. a future M4 Rust engine) that returns a
    non-optimal status without raising itself.
    """

    def failing_optimizer(
        prices: np.ndarray, dt_hours: float, battery: BatterySpec
    ) -> DispatchResult:
        horizon = len(prices)
        return DispatchResult(
            charge_mw=np.zeros(horizon),
            discharge_mw=np.zeros(horizon),
            soc_mwh=np.zeros(horizon),
            objective_value=0.0,
            solver_status="infeasible",
            simultaneous_hours=0,
        )

    with pytest.raises(RuntimeError, match="2023-07-01") as excinfo:
        run_backtest_rolling(
            _july_prices_df(),
            _default_battery(),
            _rolling_config("persistence"),
            optimizer=failing_optimizer,
        )
    assert "infeasible" in str(excinfo.value)


@pytest.mark.parametrize("forecast", _FORECASTS)
def test_soc_continuity_and_bounds_hold_on_fixture_month(forecast: str) -> None:
    """AC-4: the committed SoC trajectory, recomputed from scratch as one
    continuous recursion over the whole committed charge/discharge series,
    matches the reported per-interval soc_mwh within 1e-6. A day-boundary
    carry bug (an off-by-one, or reusing the wrong window's ending SoC) would
    desynchronize this recomputation from the reported series; matching
    confirms the carry is exact. 0 <= soc_mwh <= energy_mwh holds everywhere.
    """
    battery = _default_battery()
    dt_hours = 1.0

    dispatch, _ = solve_rolling_dispatch(_july_prices_df(), battery, _rolling_config(forecast))

    assert np.all(dispatch.soc_mwh >= -1e-6)
    assert np.all(dispatch.soc_mwh <= battery.energy_mwh + 1e-6)

    deltas = (
        battery.charge_eff * dispatch.charge_mw * dt_hours
        - (dispatch.discharge_mw * dt_hours) / battery.discharge_eff
    )
    recomputed_soc = battery.initial_soc_mwh + np.cumsum(deltas)
    assert np.max(np.abs(recomputed_soc - dispatch.soc_mwh)) < 1e-6


@pytest.mark.parametrize("forecast", _FORECASTS)
def test_rolling_revenue_never_exceeds_perfect_foresight(forecast: str) -> None:
    """AC-5: rolling total revenue <= M1 perfect-foresight total, plus 1e-6.

    The committed rolling series is always a feasible schedule for the same
    full-horizon LP that M1 solves to its global maximum, for either
    forecast variant, so it can never score higher.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()

    perfect = run_backtest(prices_df, battery)
    rolling = run_backtest_rolling(prices_df, battery, _rolling_config(forecast))

    assert rolling.total_revenue_usd <= perfect.total_revenue_usd + 1e-6


@pytest.mark.parametrize("forecast", _FORECASTS)
def test_committed_series_covers_every_fixture_hour_exactly_once(forecast: str) -> None:
    """AC-6: the committed charge/discharge/SoC series has exactly one entry
    per fixture hour (right shape, no gaps left un-filled), and revenue
    recomputed independently from (price, committed charge, committed
    discharge) matches the reported total within 1e-4.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    dt_hours = 1.0

    dispatch, solve_time_seconds = solve_rolling_dispatch(
        prices_df, battery, _rolling_config(forecast)
    )

    assert dispatch.charge_mw.shape == (len(prices_df),)
    assert dispatch.discharge_mw.shape == (len(prices_df),)
    assert dispatch.soc_mwh.shape == (len(prices_df),)
    # Every position was written by exactly one day's commit slice: none left
    # at the NaN fill value solve_rolling_dispatch initializes arrays with,
    # and none written twice (day blocks partition the array without overlap).
    assert not np.any(np.isnan(dispatch.charge_mw))
    assert not np.any(np.isnan(dispatch.discharge_mw))
    assert not np.any(np.isnan(dispatch.soc_mwh))

    result = metrics_from_dispatch(LOCATION, prices_df, battery, dispatch, solve_time_seconds)
    prices = prices_df["price"].to_numpy()
    recomputed_revenue = float(
        np.sum(prices * (dispatch.discharge_mw - dispatch.charge_mw) * dt_hours)
    )
    assert recomputed_revenue == pytest.approx(result.total_revenue_usd, abs=1e-4)


def test_rolling_backtest_runtime_budget_two_year_horizon() -> None:
    """AC-8: a synthetic 730-day rolling backtest (T about 17,520 hourly
    intervals), lookahead_days=1, forecast="persistence", completes in under
    60 seconds; solve_time_seconds is recorded (> 0) on the result, which
    flows into the metrics JSON written by the CLI.
    """
    horizon = 17_520
    start_utc = pd.Timestamp(date(2023, 1, 1), tz="America/Chicago").tz_convert("UTC")
    starts = pd.Series(pd.date_range(start_utc, periods=horizon, freq="h"))
    ends = starts + pd.Timedelta(1, unit="h")
    prices_df = pd.DataFrame(
        {
            "interval_start_utc": starts.astype("datetime64[us, UTC]"),
            "interval_end_utc": ends.astype("datetime64[us, UTC]"),
            "iso": "ERCOT",
            "market": "DAY_AHEAD_HOURLY",
            "location": LOCATION,
            "location_type": "Trading Hub",
            "price": 50.0 + 10.0 * np.sin(np.arange(horizon) * 0.1),
        }
    )
    battery = _default_battery()

    started = time.perf_counter()
    result = run_backtest_rolling(prices_df, battery, _rolling_config("persistence"))
    elapsed = time.perf_counter() - started

    print(f"run_backtest_rolling T={horizon} lookahead=1 persistence wall time: {elapsed:.3f}s")
    assert elapsed < 60.0
    assert result.solve_time_seconds > 0
    assert result.solve_time_seconds < 60.0


def test_rolling_metrics_json_is_deterministic_across_runs() -> None:
    """AC-10: two consecutive rolling runs on the fixture produce identical
    metrics JSON (byte-identical after key sorting), aside from
    solve_time_seconds, mirroring M1's determinism guarantee
    (test_backtest_metrics_json_is_deterministic_across_runs).
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    config = _rolling_config("persistence")

    first = run_backtest_rolling(prices_df, battery, config)
    second = run_backtest_rolling(prices_df, battery, config)

    first_dict = _metrics_dict(first)
    second_dict = _metrics_dict(second)
    del first_dict["solve_time_seconds"]
    del second_dict["solve_time_seconds"]

    assert json.dumps(first_dict, indent=2, sort_keys=True) == json.dumps(
        second_dict, indent=2, sort_keys=True
    )
    assert first.solve_time_seconds > 0
    assert second.solve_time_seconds > 0


def _write_fixture_config(
    tmp_path: Path, cache_dir: Path, output_dir: Path, *, lookahead_days: int, forecast: str
) -> Path:
    """A config.toml pointing at the fixture window, cache, output dir, and
    an explicit [rolling] table, so the CLI test also exercises config.toml's
    rolling section being read rather than only RollingConfig's defaults.
    """
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""\
power_mw = 100.0
energy_mwh = 200.0
charge_eff = 0.927
discharge_eff = 0.927
initial_soc_mwh = 0.0
locations = ["{LOCATION}"]
start = {FIXTURE_START.isoformat()}
end = {FIXTURE_END.isoformat()}
cache_dir = "{cache_dir.as_posix()}"
output_dir = "{output_dir.as_posix()}"

[rolling]
lookahead_days = {lookahead_days}
forecast = "{forecast}"
"""
    )
    return config_path


def test_cli_backtest_rolling_mode_writes_mode_block_and_all_m1_fields(tmp_path: Path) -> None:
    """AC-9: `bess backtest --config config.toml --mode rolling` on the
    fixture writes metrics JSON containing the `mode` block with
    lookahead_days and forecast echoed from config.toml's [rolling] table,
    plus every M1 metric field.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(
        tmp_path, cache_dir, output_dir, lookahead_days=2, forecast="perfect"
    )

    result = CliRunner().invoke(
        app, ["backtest", "--config", str(config_path), "--mode", "rolling"]
    )
    assert result.exit_code == 0, result.output

    metrics_path = output_dir / f"{LOCATION}_metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text())

    assert metrics["mode"] == {"mode": "rolling", "lookahead_days": 2, "forecast": "perfect"}
    for key in (
        "location",
        "total_revenue_usd",
        "revenue_per_mw_year",
        "revenue_per_mwh_discharged",
        "total_discharged_mwh",
        "equivalent_full_cycles",
        "daily_revenue",
        "simultaneous_hours",
        "solve_time_seconds",
    ):
        assert key in metrics, key

    comparison = json.loads((output_dir / "comparison.json").read_text())
    assert comparison == [{k: v for k, v in metrics.items() if k != "daily_revenue"}]


def test_cli_backtest_default_mode_still_emits_perfect_mode_block(tmp_path: Path) -> None:
    """The additive `mode` block is written for the default perfect-foresight
    run too: {"mode": "perfect"}, per specs/M2_rolling_and_benchmarks.md.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(
        tmp_path, cache_dir, output_dir, lookahead_days=1, forecast="persistence"
    )

    result = CliRunner().invoke(app, ["backtest", "--config", str(config_path)])
    assert result.exit_code == 0, result.output

    metrics = json.loads((output_dir / f"{LOCATION}_metrics.json").read_text())
    assert metrics["mode"] == {"mode": "perfect"}

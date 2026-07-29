"""End-to-end backtest and CLI tests (M1c acceptance criteria).

Runs run_backtest and the Typer CLI against cached fixtures only; the conftest
network guard enforces acceptance criterion 7 (no network in any test). The
frozen HB_NORTH July 2023 fixture (tests/fixtures/hb_north_2023_07.parquet,
committed by M1a) is the only real-market data used here.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from bess.backtest.runner import run_backtest, solve_dispatch
from bess.cli import _metrics_dict, app
from bess.data.prices import _cache_path
from bess.models import BatterySpec, DispatchResult
from bess.viz.plots import plot_cumulative_revenue, plot_dispatch_detail

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
LOCATION = "HB_NORTH"
FIXTURE_START = date(2023, 7, 1)
FIXTURE_END = date(2023, 7, 31)

# The July fixture's UTC calendar dates span 2023-07-01 through 2023-08-01
# (32 dates): ERCOT's Central trading day is UTC-5 in summer, so the last
# Central day (July 31) spills five hours into August 1 UTC. This is the
# concrete effect of grouping daily_revenue by UTC day (metrics_from_dispatch
# docstring) rather than the market's local trading day.
_EXPECTED_DAILY_REVENUE_BUCKETS = 32


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _july_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_FIXTURE)


def test_dispatch_properties_hold_on_fixture_month() -> None:
    """AC-1: on real HB_NORTH July 2023 data, the M1b optimizer properties hold:
    solver optimal, SoC within bounds, dynamics residual negligible, and
    revenue recomputed from (price, charge, discharge) matches the objective.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    dt_hours = 1.0

    dispatch, solve_time_seconds = solve_dispatch(prices_df, battery)

    assert dispatch.solver_status == "optimal"
    assert solve_time_seconds > 0

    assert np.all(dispatch.soc_mwh >= -1e-6)
    assert np.all(dispatch.soc_mwh <= battery.energy_mwh + 1e-6)

    deltas = (
        battery.charge_eff * dispatch.charge_mw * dt_hours
        - (dispatch.discharge_mw * dt_hours) / battery.discharge_eff
    )
    recomputed_soc = battery.initial_soc_mwh + np.cumsum(deltas)
    assert np.max(np.abs(recomputed_soc - dispatch.soc_mwh)) < 1e-6

    prices = prices_df["price"].to_numpy()
    revenue = float(np.sum(prices * (dispatch.discharge_mw - dispatch.charge_mw) * dt_hours))
    assert revenue == pytest.approx(dispatch.objective_value, abs=1e-4)

    assert np.all(dispatch.charge_mw <= battery.power_mw + 1e-6)
    assert np.all(dispatch.discharge_mw <= battery.power_mw + 1e-6)


def test_backtest_revenue_and_cycles_are_in_sane_corridor() -> None:
    """AC-2: total revenue is strictly positive; equivalent full cycles falls
    between 5 and 60 for the fixture month. This is a sanity corridor, not a
    golden value: outside it signals a units or dt bug, not a market fact.
    """
    result = run_backtest(_july_prices_df(), _default_battery())

    assert result.total_revenue_usd > 0
    assert 5.0 <= result.equivalent_full_cycles <= 60.0


def test_backtest_result_has_all_metrics_fields_and_correct_annualization() -> None:
    """AC-3: every metrics field is present, and revenue_per_mw_year is
    annualized from the actual ~744-hour window length, not a hardcoded
    8760-hour year (which would badly understate a one-month annualization).
    """
    prices_df = _july_prices_df()
    battery = _default_battery()

    result = run_backtest(prices_df, battery)

    assert result.location == LOCATION
    assert isinstance(result.total_revenue_usd, float)
    assert isinstance(result.revenue_per_mwh_discharged, float)
    assert isinstance(result.total_discharged_mwh, float)
    assert isinstance(result.equivalent_full_cycles, float)
    assert isinstance(result.simultaneous_hours, int)
    assert result.solve_time_seconds > 0

    assert isinstance(result.daily_revenue, pd.Series)
    assert len(result.daily_revenue) == _EXPECTED_DAILY_REVENUE_BUCKETS
    assert result.daily_revenue.sum() == pytest.approx(result.total_revenue_usd, abs=1e-4)

    window_hours = (
        prices_df["interval_end_utc"].iloc[-1] - prices_df["interval_start_utc"].iloc[0]
    ).total_seconds() / 3600.0
    expected_per_mw_year = result.total_revenue_usd / battery.power_mw * (8760.0 / window_hours)
    assert result.revenue_per_mw_year == pytest.approx(expected_per_mw_year, rel=1e-9)

    # A hardcoded-8760-hours bug would treat the ~744-hour window as if it
    # were already a full year, understating the annualized figure roughly
    # 12x relative to correctly scaling by (8760 / window_hours).
    naive_if_hardcoded_year = result.total_revenue_usd / battery.power_mw
    assert result.revenue_per_mw_year > naive_if_hardcoded_year * 5


def test_backtest_metrics_json_is_deterministic_across_runs() -> None:
    """AC-4: two consecutive backtest runs on the fixture produce identical
    metrics JSON (byte-identical after key sorting), aside from
    solve_time_seconds. solve_time_seconds is documented as wall-clock LP
    solve time and is expected to vary run to run; it is excluded from the
    byte-identity comparison and checked separately for positivity instead.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()

    first = run_backtest(prices_df, battery)
    second = run_backtest(prices_df, battery)

    first_dict = _metrics_dict(first)
    second_dict = _metrics_dict(second)
    del first_dict["solve_time_seconds"]
    del second_dict["solve_time_seconds"]

    first_json = json.dumps(first_dict, indent=2, sort_keys=True)
    second_json = json.dumps(second_dict, indent=2, sort_keys=True)

    assert first_json == second_json
    assert first.solve_time_seconds > 0
    assert second.solve_time_seconds > 0


def test_run_backtest_uses_injected_optimizer_without_touching_real_lp() -> None:
    """AC-5: run_backtest consumes a stub optimizer's DispatchResult as-is.
    This is the seam the M4 Rust engine drops into unchanged: the fixed
    objective_value and discharge schedule below flow straight through to the
    metrics, which would not happen if the real HiGHS LP ran instead.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    horizon = len(prices_df)
    calls: list[tuple[np.ndarray, float, BatterySpec]] = []

    def stub_optimizer(prices: np.ndarray, dt_hours: float, battery: BatterySpec) -> DispatchResult:
        calls.append((prices, dt_hours, battery))
        return DispatchResult(
            charge_mw=np.zeros(horizon),
            discharge_mw=np.full(horizon, 5.0),
            soc_mwh=np.zeros(horizon),
            objective_value=12345.0,
            solver_status="optimal",
            simultaneous_hours=0,
        )

    result = run_backtest(prices_df, battery, optimizer=stub_optimizer)

    assert len(calls) == 1
    assert result.total_revenue_usd == pytest.approx(12345.0)
    assert result.total_discharged_mwh == pytest.approx(5.0 * horizon * 1.0)
    assert result.simultaneous_hours == 0


def test_plot_dispatch_detail_writes_nonempty_png(tmp_path: Path) -> None:
    """Direct unit check: plot_dispatch_detail writes a real, nonempty PNG."""
    prices_df = _july_prices_df()
    battery = _default_battery()
    dispatch, _ = solve_dispatch(prices_df, battery)

    output_path = tmp_path / "dispatch.png"
    written = plot_dispatch_detail(prices_df, dispatch, output_path)

    assert written == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 10_000


def test_plot_cumulative_revenue_writes_nonempty_png(tmp_path: Path) -> None:
    """Direct unit check: plot_cumulative_revenue writes a real, nonempty PNG."""
    result = run_backtest(_july_prices_df(), _default_battery())
    output_path = tmp_path / "cumulative.png"

    written = plot_cumulative_revenue({LOCATION: result.daily_revenue}, output_path)

    assert written == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 10_000


def _write_fixture_config(tmp_path: Path, cache_dir: Path, output_dir: Path) -> Path:
    """A config.toml pointing at the fixture window, cache, and output dir."""
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
"""
    )
    return config_path


def test_cli_backtest_produces_metrics_json_and_both_plots(tmp_path: Path) -> None:
    """AC-6: `bess backtest --config config.toml` against the cached fixture
    produces metrics JSON and both PNG plots, each nonempty and larger than
    10 KB.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)

    result = CliRunner().invoke(app, ["backtest", "--config", str(config_path)])
    assert result.exit_code == 0, result.output

    metrics_path = output_dir / f"{LOCATION}_metrics.json"
    comparison_path = output_dir / "comparison.json"
    dispatch_plot = output_dir / f"{LOCATION}_dispatch_detail.png"
    revenue_plot = output_dir / "cumulative_revenue.png"

    for path in (metrics_path, comparison_path, dispatch_plot, revenue_plot):
        assert path.exists(), path

    metrics = json.loads(metrics_path.read_text())
    assert metrics["location"] == LOCATION
    assert metrics["total_revenue_usd"] > 0

    comparison = json.loads(comparison_path.read_text())
    assert comparison == [{k: v for k, v in metrics.items() if k != "daily_revenue"}]

    for png_path in (dispatch_plot, revenue_plot):
        assert png_path.stat().st_size > 10_000


def test_cli_plot_produces_both_plots_without_metrics_json(tmp_path: Path) -> None:
    """`bess plot` writes only the two PNGs, not a metrics JSON."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)

    result = CliRunner().invoke(app, ["plot", "--config", str(config_path)])
    assert result.exit_code == 0, result.output

    assert (output_dir / f"{LOCATION}_dispatch_detail.png").stat().st_size > 10_000
    assert (output_dir / "cumulative_revenue.png").stat().st_size > 10_000
    assert not (output_dir / f"{LOCATION}_metrics.json").exists()

"""Tests for bess.analytics.benchmarks (M2b acceptance criteria 1-5, 7).

No network; DST cases reuse the M1a raw DST fixtures already committed under
tests/fixtures/ (spring-forward 2023-03-12, fall-back 2023-11-05), the same
pattern tests/test_rolling_golden.py uses.
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

from bess.analytics.benchmarks import daily_tbk, foresight_capture_rate, tb4_capture, tbk_summary
from bess.backtest.rolling import RollingConfig, run_backtest_rolling
from bess.backtest.runner import run_backtest
from bess.cli import app
from bess.data.prices import _cache_path, _canonicalize
from bess.models import BatterySpec

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
SPRING_FORWARD_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_03_12_raw.parquet"
FALL_BACK_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_11_05_raw.parquet"

LOCATION = "HB_NORTH"
FIXTURE_START = date(2023, 7, 1)
FIXTURE_END = date(2023, 7, 31)


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _july_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_FIXTURE)


def _synthetic_day(local_date: date, prices: list[float], location: str = LOCATION) -> pd.DataFrame:
    """One local market day of canonical-schema rows, hand-built (no fetch/cache).

    Mirrors tests/test_rolling_golden.py's helper of the same name.
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


def test_tbk_golden_constructed_day() -> None:
    """AC-1: 24-hour day, 4 hours at $100, 4 at $10, 16 at $50: TB4 == 360.0, TB2 == 180.0."""
    prices = [100.0] * 4 + [10.0] * 4 + [50.0] * 16
    prices_df = _synthetic_day(date(2023, 7, 10), prices)

    tb4 = daily_tbk(prices_df, k=4)
    tb2 = daily_tbk(prices_df, k=2)

    assert len(tb4) == 1
    assert len(tb2) == 1
    assert tb4.iloc[0] == pytest.approx(360.0, abs=1e-6)
    assert tb2.iloc[0] == pytest.approx(180.0, abs=1e-6)


def test_tbk_golden_requires_at_least_2k_hours() -> None:
    """A market day shorter than 2*k hours must fail loudly, not silently
    double-count or emit NaN (project convention: gaps fail loudly).
    """
    prices_df = _synthetic_day(date(2023, 7, 10), [10.0, 20.0, 30.0])

    with pytest.raises(ValueError, match="2023-07-10"):
        daily_tbk(prices_df, k=2)


def test_tbk_dst_days_use_all_available_hours() -> None:
    """AC-2: TB4 on the 23-hour spring-forward and 25-hour fall-back raw DST
    samples computes from all available hours (verified against an
    independent numpy computation over the same day, not a duplicated
    reimplementation); the daily row count matches 23 and 25.
    """
    spring_forward_raw = pd.read_parquet(SPRING_FORWARD_RAW_FIXTURE)
    spring_forward_day = _canonicalize(spring_forward_raw, date(2023, 3, 12), date(2023, 3, 12))
    assert len(spring_forward_day) == 23

    fall_back_raw = pd.read_parquet(FALL_BACK_RAW_FIXTURE)
    fall_back_day = _canonicalize(fall_back_raw, date(2023, 11, 5), date(2023, 11, 5))
    assert len(fall_back_day) == 25

    spring_forward_tb4 = daily_tbk(spring_forward_day, k=4)
    fall_back_tb4 = daily_tbk(fall_back_day, k=4)
    assert len(spring_forward_tb4) == 1
    assert len(fall_back_tb4) == 1

    sorted_spring_forward = np.sort(spring_forward_day["price"].to_numpy())
    expected_spring_forward_tb4 = sorted_spring_forward[-4:].sum() - sorted_spring_forward[:4].sum()
    assert spring_forward_tb4.iloc[0] == pytest.approx(expected_spring_forward_tb4, abs=1e-6)

    sorted_fall_back = np.sort(fall_back_day["price"].to_numpy())
    expected_fall_back_tb4 = sorted_fall_back[-4:].sum() - sorted_fall_back[:4].sum()
    assert fall_back_tb4.iloc[0] == pytest.approx(expected_fall_back_tb4, abs=1e-6)


def test_tbk_properties_on_july_fixture() -> None:
    """AC-3: TB4 >= TB2 >= 0 for every day of the July 2023 fixture window; no NaN."""
    prices_df = _july_prices_df()

    tb2 = daily_tbk(prices_df, k=2)
    tb4 = daily_tbk(prices_df, k=4)

    assert len(tb2) == 31
    assert len(tb4) == 31
    assert not tb2.isna().any()
    assert not tb4.isna().any()
    assert np.all(tb2.to_numpy() >= -1e-9)
    assert np.all(tb4.to_numpy() >= tb2.to_numpy() - 1e-9)


def test_tbk_summary_reports_window_and_per_year_means() -> None:
    """tbk_summary's window_mean matches the plain mean over the whole
    series, and the single-year 2023 fixture's by_year entry matches it too.
    """
    tb4 = daily_tbk(_july_prices_df(), k=4)
    summary = tbk_summary(tb4)

    assert summary["window_mean"] == pytest.approx(float(tb4.mean()), abs=1e-9)
    assert summary["by_year"] == {"2023": pytest.approx(float(tb4.mean()), abs=1e-9)}


def test_foresight_capture_rate_in_sanity_corridor_on_july_fixture() -> None:
    """AC-4: foresight capture rate is in (0, 1] and within the sanity
    corridor [0.4, 1.0] (mirrors M1c acceptance criterion 2's corridor
    style); outside it signals a units or windowing bug, not a finding.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()

    perfect = run_backtest(prices_df, battery)
    rolling = run_backtest_rolling(
        prices_df, battery, RollingConfig(lookahead_days=1, forecast="persistence")
    )

    capture = foresight_capture_rate(rolling.total_revenue_usd, perfect.total_revenue_usd)

    assert 0.0 < capture <= 1.0 + 1e-6
    assert 0.4 <= capture <= 1.0 + 1e-6


def test_tb4_capture_in_open_interval_both_modes_on_july_fixture() -> None:
    """AC-5: TB4 capture is in (0, 1) for the 2-hour default battery
    (100 MW / 200 MWh), both modes. A 2-hour battery cannot reach 1.0 by
    construction against a 4-highest/4-lowest daily spread.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    daily_tb4 = daily_tbk(prices_df, k=4)

    perfect = run_backtest(prices_df, battery)
    rolling = run_backtest_rolling(
        prices_df, battery, RollingConfig(lookahead_days=1, forecast="persistence")
    )

    perfect_capture = tb4_capture(perfect.total_revenue_usd, daily_tb4, battery.power_mw)
    rolling_capture = tb4_capture(rolling.total_revenue_usd, daily_tb4, battery.power_mw)

    assert 0.0 < perfect_capture < 1.0
    assert 0.0 < rolling_capture < 1.0


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


def test_cli_benchmark_writes_tbk_json_and_skips_capture_when_metrics_absent(
    tmp_path: Path,
) -> None:
    """AC-7 (missing-metrics path): `bess benchmark` on the fixture cache,
    with no prior `bess backtest` run, writes benchmarks.json with TB2/TB4
    per hub and exits 0 with a printed notice instead of a capture section.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)

    result = CliRunner().invoke(app, ["benchmark", "--config", str(config_path)])
    assert result.exit_code == 0, result.output
    assert "skipping capture rates" in result.output

    benchmarks = json.loads((output_dir / "benchmarks.json").read_text())
    assert set(benchmarks[LOCATION]) == {"tb2", "tb4"}
    assert benchmarks[LOCATION]["tb2"]["window_mean"] > 0
    assert benchmarks[LOCATION]["tb4"]["window_mean"] > 0


def test_cli_benchmark_includes_capture_rates_when_both_modes_present(tmp_path: Path) -> None:
    """AC-7 (both-modes-present path): after running `bess backtest` in both
    perfect and rolling mode into the same output dir, `bess benchmark`
    includes foresight_capture_rate and both tb4_capture values.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)

    runner = CliRunner()
    perfect_result = runner.invoke(app, ["backtest", "--config", str(config_path)])
    assert perfect_result.exit_code == 0, perfect_result.output
    rolling_result = runner.invoke(
        app, ["backtest", "--config", str(config_path), "--mode", "rolling"]
    )
    assert rolling_result.exit_code == 0, rolling_result.output

    benchmark_result = runner.invoke(app, ["benchmark", "--config", str(config_path)])
    assert benchmark_result.exit_code == 0, benchmark_result.output
    assert "skipping capture rates" not in benchmark_result.output

    benchmarks = json.loads((output_dir / "benchmarks.json").read_text())
    capture = benchmarks[LOCATION]["capture"]
    assert 0.0 < capture["foresight_capture_rate"] <= 1.0 + 1e-6
    assert 0.0 < capture["tb4_capture_perfect"] < 1.0
    assert 0.0 < capture["tb4_capture_rolling"] < 1.0

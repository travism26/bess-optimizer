"""Tests for bess.analytics.sweep and the `bess sweep` CLI command (M2b
acceptance criteria 6 and 8).

No network; runs entirely from the committed July 2023 fixture.
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from typer.testing import CliRunner

from bess.analytics.sweep import (
    SweepConfig,
    duration_variants,
    efficiency_variants,
    run_sweep,
)
from bess.backtest.rolling import RollingConfig
from bess.cli import app
from bess.data.prices import _cache_path
from bess.models import BatterySpec

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
LOCATION = "HB_NORTH"
FIXTURE_START = date(2023, 7, 1)
FIXTURE_END = date(2023, 7, 31)


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _july_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_FIXTURE)


def test_duration_variants_scale_energy_by_power_times_duration() -> None:
    """energy_mwh = power_mw x duration_h; power_mw and efficiencies unchanged."""
    battery = _default_battery()
    variants = duration_variants(battery, (1.0, 2.0, 4.0))

    assert [duration_h for duration_h, _ in variants] == [1.0, 2.0, 4.0]
    for duration_h, variant in variants:
        assert variant.energy_mwh == pytest.approx(battery.power_mw * duration_h)
        assert variant.power_mw == battery.power_mw
        assert variant.charge_eff == battery.charge_eff
        assert variant.discharge_eff == battery.discharge_eff


def test_efficiency_variants_split_round_trip_as_sqrt_per_side() -> None:
    """Gotcha 2: round-trip efficiency splits as sqrt() per side, matching
    optimize_dispatch's 0.927-per-side / 86 percent round-trip convention.
    """
    battery = _default_battery()
    variants = efficiency_variants(battery, (0.80, 0.86, 0.92))

    assert [rte for rte, _ in variants] == [0.80, 0.86, 0.92]
    for rte, variant in variants:
        expected_one_way = math.sqrt(rte)
        assert variant.charge_eff == pytest.approx(expected_one_way)
        assert variant.discharge_eff == pytest.approx(expected_one_way)
        assert variant.energy_mwh == battery.energy_mwh
        assert variant.power_mw == battery.power_mw

    # The spec's own 0.86 point reproduces M1's 0.927 default convention.
    rte_86 = next(variant for rte, variant in variants if rte == 0.86)
    assert rte_86.charge_eff == pytest.approx(0.927, abs=1e-3)


def test_sweep_duration_perfect_revenue_non_decreasing() -> None:
    """AC-6: perfect-mode revenue_per_mw_year is non-decreasing across
    duration 1h -> 2h -> 4h on the July fixture. Rolling's ordering is only
    logged, not asserted: a persistence forecast losing a bit of value at a
    longer duration in a given month is a legitimate finding, not a bug.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    sweep_config = SweepConfig(durations_h=(1.0, 2.0, 4.0))
    rolling_config = RollingConfig(lookahead_days=1, forecast="persistence")

    result = run_sweep(prices_df, battery, sweep_config, rolling_config)
    duration_points = result["duration"]

    perfect_revenue = [point["perfect"]["revenue_per_mw_year"] for point in duration_points]
    rolling_revenue = [point["rolling"]["revenue_per_mw_year"] for point in duration_points]

    for earlier, later in pairwise(perfect_revenue):
        assert later >= earlier - 1e-6

    print(f"Sweep duration rolling revenue_per_mw_year ordering: {rolling_revenue}")


def _strip_solve_time(value: Any) -> Any:
    """Recursively drop every 'solve_time_seconds' key (the one intentionally
    non-deterministic field, spec gotcha 4), so two sweep JSONs can be
    compared for byte-identity on every other field.
    """
    if isinstance(value, dict):
        return {k: _strip_solve_time(v) for k, v in value.items() if k != "solve_time_seconds"}
    if isinstance(value, list):
        return [_strip_solve_time(v) for v in value]
    return value


def test_sweep_json_is_deterministic_excluding_solve_time() -> None:
    """Two consecutive run_sweep calls on the fixture produce identical
    results after stripping every solve_time_seconds field, mirroring
    test_backtest_metrics_json_is_deterministic_across_runs.
    """
    prices_df = _july_prices_df()
    battery = _default_battery()
    sweep_config = SweepConfig()
    rolling_config = RollingConfig(lookahead_days=1, forecast="persistence")

    first = run_sweep(prices_df, battery, sweep_config, rolling_config)
    second = run_sweep(prices_df, battery, sweep_config, rolling_config)

    first_json = json.dumps(_strip_solve_time(first), sort_keys=True)
    second_json = json.dumps(_strip_solve_time(second), sort_keys=True)
    assert first_json == second_json


def _write_fixture_config(tmp_path: Path, cache_dir: Path, output_dir: Path) -> Path:
    """A config.toml pointing at the fixture window, cache, and output dir.
    No [sweep] table, so SweepConfig's defaults (1,2,4h; 0.80/0.86/0.92) apply.
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
"""
    )
    return config_path


def test_cli_sweep_writes_json_and_plot_and_is_deterministic(tmp_path: Path) -> None:
    """AC-8: `bess sweep` writes sweep JSON plus a PNG larger than 10 KB;
    two consecutive runs are byte-identical after key sorting, excluding
    the documented wall-time field.
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    shutil.copy(JULY_FIXTURE, _cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END))

    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)
    runner = CliRunner()

    first = runner.invoke(app, ["sweep", "--config", str(config_path)])
    assert first.exit_code == 0, first.output

    sweep_path = output_dir / "sweep.json"
    plot_path = output_dir / "sweep_duration.png"
    assert sweep_path.exists()
    assert plot_path.stat().st_size > 10_000

    first_json = json.loads(sweep_path.read_text())
    assert first_json["hubs"][LOCATION]["duration"][0]["duration_h"] == 1.0
    assert "efficiency_convention" in first_json

    second = runner.invoke(app, ["sweep", "--config", str(config_path)])
    assert second.exit_code == 0, second.output
    second_json = json.loads(sweep_path.read_text())

    first_stripped = json.dumps(_strip_solve_time(first_json), sort_keys=True)
    second_stripped = json.dumps(_strip_solve_time(second_json), sort_keys=True)
    assert first_stripped == second_stripped

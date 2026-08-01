"""End-to-end AS backtest, CLI, and benchmark tests (M3c acceptance criteria).

Runs run_backtest_as and the Typer CLI against cached fixtures only; the
conftest network guard enforces acceptance criterion 9 (no network in any
test). The frozen HB_NORTH July 2023 energy and AS fixtures (committed by
M1a and M3a) are the real-market data used for the bulk of these tests; the
2023-03-12 spring-forward raw pair covers the pre-launch ECRS mask path in
the same test as the DST path (acceptance criterion 1).
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner, Result

from bess.analytics.benchmarks import as_uplift, revenue_mix
from bess.backtest.as_runner import run_backtest_as
from bess.backtest.runner import run_backtest
from bess.cli import app
from bess.data.as_prices import _cache_path as as_cache_path
from bess.data.as_prices import _canonicalize as as_canonicalize
from bess.data.prices import _cache_path as energy_cache_path
from bess.data.prices import _canonicalize as energy_canonicalize
from bess.models import (
    DEFAULT_AS_PRODUCTS,
    AsDispatchResult,
    AsProduct,
    BatterySpec,
    DispatchResult,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_ENERGY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
JULY_AS_FIXTURE = FIXTURES_DIR / "as_mcpc_2023_07.parquet"
MARCH_ENERGY_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_03_12_raw.parquet"
MARCH_AS_RAW_FIXTURE = FIXTURES_DIR / "as_2023_03_12_raw.parquet"

LOCATION = "HB_NORTH"
FIXTURE_START = date(2023, 7, 1)
FIXTURE_END = date(2023, 7, 31)

# Measured on the committed fixtures (see ai_docs/research/d39c4d18-m3c-as-
# backtest-cli-analysis.md): energy-only $970,937.15 vs co-optimized
# $2,689,961.68, uplift 2.7705x. The corridor below is the spec's sanity
# check, not a golden value.
_UPLIFT_CORRIDOR = (1.0, 8.0)


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _july_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_ENERGY_FIXTURE)


def _july_as_prices_df() -> pd.DataFrame:
    return pd.read_parquet(JULY_AS_FIXTURE)


def test_run_backtest_as_raises_listing_missing_pair_for_doctored_gap() -> None:
    """AC-1 (gap path): dropping one REG_UP hour mid-window raises, naming REG_UP
    and the ISO timestamp of the missing interval. REG_UP is live for all of
    2023, so this is a genuine gap, not a pre-launch absence.
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()

    target_ts = prices_df["interval_start_utc"].iloc[400]
    doctored = as_prices_df.loc[
        ~((as_prices_df["product"] == "REG_UP") & (as_prices_df["interval_start_utc"] == target_ts))
    ]

    with pytest.raises(ValueError, match="REG_UP") as excinfo:
        run_backtest_as(prices_df, doctored, battery)
    assert target_ts.isoformat() in str(excinfo.value)


def test_run_backtest_as_masks_prelaunch_ecrs_on_spring_forward_dst_day() -> None:
    """AC-1 (mask path) + acceptance criterion 9: 2023-03-12 is a 23-hour
    spring-forward day entirely before ECRS's 2023-06-10 launch. ECRS is
    absent from the AS fixture for that day; run_backtest_as must solve
    cleanly (never raise) with ECRS availability and awards identically zero,
    since the absence is structural, not a gap.
    """
    energy_raw = pd.read_parquet(MARCH_ENERGY_RAW_FIXTURE)
    as_raw = pd.read_parquet(MARCH_AS_RAW_FIXTURE)
    prices_df = energy_canonicalize(energy_raw, date(2023, 3, 12), date(2023, 3, 12))
    as_prices_df = as_canonicalize(as_raw, date(2023, 3, 12), date(2023, 3, 12))
    battery = _default_battery()

    assert len(prices_df) == 23
    assert "ECRS" not in set(as_prices_df["product"])

    result = run_backtest_as(prices_df, as_prices_df, battery)

    assert result.award_mw_hours["ECRS"] == 0.0
    assert np.isfinite(result.total_revenue_usd)


def test_run_backtest_as_metrics_integrity_on_july_fixture() -> None:
    """AC-2: energy_revenue_usd + as_revenue_usd == total_revenue_usd within
    1e-4; revenue_by_product sums to as_revenue_usd within 1e-4; every M1
    metric field on `energy` is present and finite.
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()

    result = run_backtest_as(prices_df, as_prices_df, battery)

    assert result.energy.total_revenue_usd + result.as_revenue_usd == pytest.approx(
        result.total_revenue_usd, abs=1e-4
    )
    assert float(result.revenue_by_product.sum()) == pytest.approx(result.as_revenue_usd, abs=1e-4)

    assert result.energy.location == LOCATION
    for field in (
        result.energy.total_revenue_usd,
        result.energy.revenue_per_mw_year,
        result.energy.revenue_per_mwh_discharged,
        result.energy.total_discharged_mwh,
        result.energy.equivalent_full_cycles,
        result.energy.solve_time_seconds,
    ):
        assert np.isfinite(field)
    assert isinstance(result.energy.simultaneous_hours, int)
    assert not result.energy.daily_revenue.isna().any()
    assert np.all(np.isfinite(result.award_mw_hours.to_numpy()))
    assert np.all(np.isfinite(result.revenue_by_product.to_numpy()))


def test_run_backtest_as_dominates_energy_only_backtest_on_july_fixture() -> None:
    """AC-3: total co-opt revenue >= the energy-only perfect backtest revenue,
    same fixture, same battery. The co-optimized ENERGY leg alone may be
    lower (the battery trades arbitrage for AS capacity), but the combined
    total can never fall below the energy-only optimum since AS awards are
    optional (a_pt >= 0, no minimum).
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()

    energy_only = run_backtest(prices_df, battery)
    co_opt = run_backtest_as(prices_df, as_prices_df, battery)

    assert co_opt.total_revenue_usd >= energy_only.total_revenue_usd - 1e-6


def test_as_uplift_in_sanity_corridor_on_july_fixture() -> None:
    """AC-4: July 2023 uplift is in [1.0, 8.0]; outside it signals a units or
    alignment bug, not a finding (mirrors the M2b corridor convention).
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()

    energy_only = run_backtest(prices_df, battery)
    co_opt = run_backtest_as(prices_df, as_prices_df, battery)

    uplift = as_uplift(co_opt.total_revenue_usd, energy_only.total_revenue_usd)

    lower, upper = _UPLIFT_CORRIDOR
    assert lower <= uplift <= upper


def test_run_backtest_as_is_deterministic_across_runs() -> None:
    """AC-8: two consecutive run_backtest_as calls on the same fixture agree
    on every field except solve_time_seconds (documented wall-clock field,
    memory: determinism-tests-exclude-wallclock-fields).
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()

    first = run_backtest_as(prices_df, as_prices_df, battery)
    second = run_backtest_as(prices_df, as_prices_df, battery)

    assert first.total_revenue_usd == second.total_revenue_usd
    assert first.as_revenue_usd == second.as_revenue_usd
    assert first.energy.total_revenue_usd == second.energy.total_revenue_usd
    pd.testing.assert_series_equal(first.revenue_by_product, second.revenue_by_product)
    pd.testing.assert_series_equal(first.award_mw_hours, second.award_mw_hours)
    assert first.energy.solve_time_seconds > 0
    assert second.energy.solve_time_seconds > 0


def test_run_backtest_as_uses_injected_optimizer_without_touching_real_lp() -> None:
    """Contract test (the M4 seam): run_backtest_as consumes a stub
    AsDispatchResult as-is, the same injected-optimizer pattern
    run_backtest and run_backtest_rolling use.
    """
    prices_df = _july_prices_df()
    as_prices_df = _july_as_prices_df()
    battery = _default_battery()
    horizon = len(prices_df)
    products = DEFAULT_AS_PRODUCTS
    calls: list[
        tuple[np.ndarray, np.ndarray, np.ndarray, float, BatterySpec, tuple[AsProduct, ...]]
    ] = []

    def stub_optimizer(
        prices: np.ndarray,
        as_prices: np.ndarray,
        as_available: np.ndarray,
        dt_hours: float,
        battery: BatterySpec,
        products: tuple[AsProduct, ...],
    ) -> AsDispatchResult:
        calls.append((prices, as_prices, as_available, dt_hours, battery, products))
        dispatch = DispatchResult(
            charge_mw=np.zeros(horizon),
            discharge_mw=np.full(horizon, 5.0),
            soc_mwh=np.zeros(horizon),
            objective_value=99999.0,
            solver_status="optimal",
            simultaneous_hours=0,
        )
        awards_mw = np.zeros((len(products), horizon))
        return AsDispatchResult(
            dispatch=dispatch,
            products=products,
            awards_mw=awards_mw,
            energy_revenue_usd=12345.0,
            as_revenue_usd=87654.0,
        )

    result = run_backtest_as(prices_df, as_prices_df, battery, products, optimizer=stub_optimizer)

    assert len(calls) == 1
    assert result.energy.total_revenue_usd == pytest.approx(12345.0)
    assert result.as_revenue_usd == pytest.approx(87654.0)
    assert result.total_revenue_usd == pytest.approx(12345.0 + 87654.0)
    assert (result.award_mw_hours == 0.0).all()


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


def _seed_fixture_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        JULY_ENERGY_FIXTURE, energy_cache_path(cache_dir, LOCATION, FIXTURE_START, FIXTURE_END)
    )
    shutil.copy(JULY_AS_FIXTURE, as_cache_path(cache_dir, FIXTURE_START, FIXTURE_END))


def _invoke_backtest(tmp_path: Path, tag: str, extra_args: list[str]) -> tuple[Path, Result]:
    """Seed a fresh fixture cache under tmp_path/tag and invoke `bess backtest`."""
    cache_dir = tmp_path / tag / "cache"
    _seed_fixture_cache(cache_dir)
    output_dir = tmp_path / tag / "output"
    config_path = _write_fixture_config(tmp_path / tag, cache_dir, output_dir)

    result = CliRunner().invoke(app, ["backtest", "--config", str(config_path), *extra_args])
    return output_dir, result


def test_cli_backtest_ancillary_writes_qualified_metrics_with_full_block(tmp_path: Path) -> None:
    """AC-5 (ancillary output): `--ancillary` writes
    {location}_metrics_perfect_ancillary.json with the full additive
    `ancillary` block (products, sustain_hours, energy_revenue_usd,
    as_revenue_usd, revenue_by_product, award_mw_hours, total_revenue_usd).
    """
    output_dir, result = _invoke_backtest(tmp_path, "ancillary", ["--ancillary"])
    assert result.exit_code == 0, result.output

    ancillary_path = output_dir / f"{LOCATION}_metrics_perfect_ancillary.json"
    assert ancillary_path.exists()

    metrics = json.loads(ancillary_path.read_text())
    assert metrics["mode"] == {"mode": "perfect"}
    ancillary = metrics["ancillary"]
    assert set(ancillary["products"]) == {p.name for p in DEFAULT_AS_PRODUCTS}
    assert set(ancillary["sustain_hours"]) == {p.name for p in DEFAULT_AS_PRODUCTS}
    assert ancillary["energy_revenue_usd"] + ancillary["as_revenue_usd"] == pytest.approx(
        ancillary["total_revenue_usd"], abs=1e-4
    )
    assert set(ancillary["revenue_by_product"]) == {p.name for p in DEFAULT_AS_PRODUCTS}
    assert set(ancillary["award_mw_hours"]) == {p.name for p in DEFAULT_AS_PRODUCTS}
    assert ancillary["total_revenue_usd"] > metrics["total_revenue_usd"]


def test_cli_backtest_ancillary_leaves_energy_only_outputs_unperturbed(tmp_path: Path) -> None:
    """AC-5 (no perturbation): the energy-only output files from an
    `--ancillary` run are byte-identical (modulo solve_time_seconds, the
    documented non-deterministic field) to a run without `--ancillary`; the
    two PNG plots are exactly byte-identical since plotting has no
    wall-clock-dependent content.
    """
    plain_output_dir, plain_result = _invoke_backtest(tmp_path, "plain", [])
    assert plain_result.exit_code == 0, plain_result.output
    ancillary_output_dir, ancillary_result = _invoke_backtest(
        tmp_path, "ancillary", ["--ancillary"]
    )
    assert ancillary_result.exit_code == 0, ancillary_result.output

    for name in (f"{LOCATION}_metrics.json", f"{LOCATION}_metrics_perfect.json"):
        plain_metrics = json.loads((plain_output_dir / name).read_text())
        ancillary_metrics = json.loads((ancillary_output_dir / name).read_text())
        del plain_metrics["solve_time_seconds"]
        del ancillary_metrics["solve_time_seconds"]
        assert plain_metrics == ancillary_metrics

    plain_comparison = json.loads((plain_output_dir / "comparison.json").read_text())
    ancillary_comparison = json.loads((ancillary_output_dir / "comparison.json").read_text())
    for row in plain_comparison + ancillary_comparison:
        del row["solve_time_seconds"]
    assert plain_comparison == ancillary_comparison

    for png_name in (f"{LOCATION}_dispatch_detail.png", "cumulative_revenue.png"):
        plain_bytes = (plain_output_dir / png_name).read_bytes()
        ancillary_bytes = (ancillary_output_dir / png_name).read_bytes()
        assert plain_bytes == ancillary_bytes

    assert not (plain_output_dir / f"{LOCATION}_metrics_perfect_ancillary.json").exists()


def test_cli_backtest_ancillary_with_rolling_mode_exits_nonzero(tmp_path: Path) -> None:
    """AC-7: `--ancillary --mode rolling` exits nonzero with a message naming
    M3's perfect-foresight-only scope, and writes nothing.
    """
    cache_dir = tmp_path / "cache"
    _seed_fixture_cache(cache_dir)
    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)

    result = CliRunner().invoke(
        app, ["backtest", "--config", str(config_path), "--ancillary", "--mode", "rolling"]
    )

    assert result.exit_code != 0
    assert "M3" in result.output
    assert not output_dir.exists()


def test_cli_ancillary_enabled_via_config_toml_without_the_flag(tmp_path: Path) -> None:
    """Spec item 2: `[ancillary].enabled = true` in config.toml triggers the
    co-opt backtest without passing `--ancillary` on the command line.
    """
    cache_dir = tmp_path / "cache"
    _seed_fixture_cache(cache_dir)
    output_dir = tmp_path / "output"
    config_path = _write_fixture_config(tmp_path, cache_dir, output_dir)
    with config_path.open("a") as f:
        f.write("\n[ancillary]\nenabled = true\n")

    result = CliRunner().invoke(app, ["backtest", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert (output_dir / f"{LOCATION}_metrics_perfect_ancillary.json").exists()


def test_cli_benchmark_skips_as_uplift_when_ancillary_file_absent(tmp_path: Path) -> None:
    """AC-6 (missing path): with only the energy-only perfect metrics file
    present, `bess benchmark` skips AS uplift with a notice and exits 0.
    """
    output_dir, backtest_result = _invoke_backtest(tmp_path, "plain", [])
    assert backtest_result.exit_code == 0, backtest_result.output
    config_path = tmp_path / "plain" / "config.toml"

    result = CliRunner().invoke(app, ["benchmark", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "skipping AS uplift" in result.output

    benchmarks = json.loads((output_dir / "benchmarks.json").read_text())
    assert "ancillary" not in benchmarks[LOCATION]


def test_cli_benchmark_includes_as_uplift_and_mix_when_both_present(tmp_path: Path) -> None:
    """AC-6 (both-present path): with both the energy-only perfect metrics
    file and the perfect ancillary metrics file present, `bess benchmark`
    emits as_uplift (in the sanity corridor) and a revenue_mix that sums to
    ~1.0 across products.
    """
    output_dir, backtest_result = _invoke_backtest(tmp_path, "ancillary", ["--ancillary"])
    assert backtest_result.exit_code == 0, backtest_result.output
    config_path = tmp_path / "ancillary" / "config.toml"

    result = CliRunner().invoke(app, ["benchmark", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "skipping AS uplift" not in result.output

    benchmarks = json.loads((output_dir / "benchmarks.json").read_text())
    ancillary_benchmarks = benchmarks[LOCATION]["ancillary"]

    lower, upper = _UPLIFT_CORRIDOR
    assert lower <= ancillary_benchmarks["as_uplift"] <= upper

    mix = ancillary_benchmarks["revenue_mix"]
    assert set(mix) == {p.name for p in DEFAULT_AS_PRODUCTS}
    assert sum(mix.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(share >= -1e-9 for share in mix.values())


def test_revenue_mix_shares_sum_to_one() -> None:
    """Unit check on the pure analytics helper directly (spec item 4: no I/O)."""
    mix = revenue_mix({"REG_UP": 100.0, "REG_DOWN": 300.0, "ECRS": 600.0})

    assert sum(mix.values()) == pytest.approx(1.0)
    assert mix["ECRS"] == pytest.approx(0.6)

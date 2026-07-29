"""Property and behavior tests for optimize_dispatch (acceptance criteria 5-11).

All price series here are synthetic (seeded random or hand-built edge cases);
per specs/M1b_optimizer.md this module is independent of M1a and never touches
fixtures or the network.
"""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path

import numpy as np
import pytest

from bess.models import BatterySpec
from bess.optimizer.lp import optimize_dispatch

# Acceptance criteria 5-9: 3 fixed seeds, T=168, uniform on [-20, 150].
_SEEDS = (0, 1, 2)
_PROPERTY_HORIZON = 168


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _synthetic_prices(seed: int, horizon: int = _PROPERTY_HORIZON) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-20.0, 150.0, size=horizon)


@pytest.mark.parametrize("seed", _SEEDS)
def test_solver_reaches_optimal_on_random_price_series(seed: int) -> None:
    """AC-5: solver_status == 'optimal' for all seeded series."""
    result = optimize_dispatch(_synthetic_prices(seed), dt_hours=1.0, battery=_default_battery())

    assert result.solver_status == "optimal"


@pytest.mark.parametrize("seed", _SEEDS)
def test_soc_stays_within_battery_bounds(seed: int) -> None:
    """AC-6: 0 <= soc_mwh <= energy_mwh everywhere, tolerance 1e-6."""
    battery = _default_battery()
    result = optimize_dispatch(_synthetic_prices(seed), dt_hours=1.0, battery=battery)

    assert np.all(result.soc_mwh >= -1e-6)
    assert np.all(result.soc_mwh <= battery.energy_mwh + 1e-6)


@pytest.mark.parametrize("seed", _SEEDS)
def test_soc_dynamics_residual_is_negligible(seed: int) -> None:
    """AC-7: SoC recomputed from charge/discharge arrays matches soc_mwh, < 1e-6."""
    battery = _default_battery()
    dt_hours = 1.0
    result = optimize_dispatch(_synthetic_prices(seed), dt_hours=dt_hours, battery=battery)

    deltas = (
        battery.charge_eff * result.charge_mw * dt_hours
        - (result.discharge_mw * dt_hours) / battery.discharge_eff
    )
    recomputed_soc = battery.initial_soc_mwh + np.cumsum(deltas)

    assert np.max(np.abs(recomputed_soc - result.soc_mwh)) < 1e-6


@pytest.mark.parametrize("seed", _SEEDS)
def test_revenue_recomputed_matches_objective(seed: int) -> None:
    """AC-8: revenue independently recomputed from (prices, c, d) matches objective."""
    prices = _synthetic_prices(seed)
    battery = _default_battery()
    dt_hours = 1.0
    result = optimize_dispatch(prices, dt_hours=dt_hours, battery=battery)

    revenue = float(np.sum(prices * (result.discharge_mw - result.charge_mw) * dt_hours))

    assert revenue == pytest.approx(result.objective_value, abs=1e-4)


@pytest.mark.parametrize("seed", _SEEDS)
def test_charge_and_discharge_respect_power_limit(seed: int) -> None:
    """AC-9: charge_mw <= power_mw and discharge_mw <= power_mw everywhere."""
    battery = _default_battery()
    result = optimize_dispatch(_synthetic_prices(seed), dt_hours=1.0, battery=battery)

    assert np.all(result.charge_mw <= battery.power_mw + 1e-6)
    assert np.all(result.discharge_mw <= battery.power_mw + 1e-6)


def test_simultaneous_charge_discharge_at_negative_price_is_reported_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-10: deeply negative price with a full battery triggers simultaneous c/d.

    Burning energy through round-trip efficiency losses is genuinely profitable
    when the price is negative enough, and a full initial SoC forces exactly
    that: charging is only possible if enough simultaneous discharge makes
    room. This is expected LP behavior; it must be reported and logged, never
    raised (specs/M1b_optimizer.md, acceptance criterion 10).

    A single-interval horizon is used deliberately: with more than one
    interval, a solver is free to place the offsetting discharge in a
    different (equally revenue-neutral) zero-price interval instead of the
    negative-price one, which is an equally valid optimum but would not
    exercise the same-interval simultaneity this test targets.
    """
    prices = np.array([-1000.0])
    battery = BatterySpec(
        power_mw=1.0,
        energy_mwh=1.0,
        charge_eff=0.9,
        discharge_eff=0.9,
        initial_soc_mwh=1.0,
    )

    with caplog.at_level(logging.WARNING, logger="bess.optimizer.lp"):
        result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

    assert result.solver_status == "optimal"
    assert result.simultaneous_hours > 0
    assert result.charge_mw[0] > 1e-3
    assert result.discharge_mw[0] > 1e-3
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert "simultaneous" in caplog.text.lower()


def test_full_two_year_horizon_solves_within_runtime_budget() -> None:
    """AC-11: T=17,520 (2 hourly years) solves in under 30 seconds."""
    horizon = 17_520
    prices = _synthetic_prices(seed=2024, horizon=horizon)
    battery = _default_battery()

    start = time.perf_counter()
    result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)
    elapsed = time.perf_counter() - start

    print(f"optimize_dispatch T={horizon} wall time: {elapsed:.3f}s")
    assert result.solver_status == "optimal"
    assert elapsed < 30.0


def _top_level_import_modules(path: Path) -> set[str]:
    """Root module names from every top-level import statement in `path`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_lp_module_imports_are_restricted_to_the_purity_allowlist() -> None:
    """Hard purity rule: lp.py imports only numpy, highspy, and bess.models.

    logging is allowed too (a module-level logger is explicitly fine per the
    spec); anything else, in particular pandas, would violate the "no I/O, no
    DataFrames, no timezone logic" contract that makes this module the
    frozen, drop-in-replaceable correctness oracle for the M4 Rust engine.
    """
    lp_module = Path(__file__).parent.parent / "src" / "bess" / "optimizer" / "lp.py"
    allowed = {"numpy", "highspy", "bess.models", "logging", "__future__"}

    imports = _top_level_import_modules(lp_module)

    assert imports <= allowed
    assert {"numpy", "highspy", "bess.models"} <= imports

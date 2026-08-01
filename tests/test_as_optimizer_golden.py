"""Golden-value tests for optimize_dispatch_as (acceptance criteria 1-5).

Each test constructs a tiny synthetic price series, or a masked/degenerate
variant of a random one, with a hand-derivable (or exactly known) optimum and
asserts the objective to 1e-6. No fixtures, no network.
"""

from __future__ import annotations

import numpy as np
import pytest

from bess.models import DEFAULT_AS_PRODUCTS, AsProduct, BatterySpec
from bess.optimizer.as_lp import optimize_dispatch_as
from bess.optimizer.lp import optimize_dispatch


def _default_battery() -> BatterySpec:
    """The config.toml default battery, matching test_optimizer_properties.py."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _synthetic_prices(seed: int, horizon: int = 168) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-20.0, 150.0, size=horizon)


def test_masked_unavailable_awards_reproduces_energy_only_objective() -> None:
    """AC-1: as_available all False reproduces optimize_dispatch exactly, awards zero.

    With every award column pinned to a zero upper bound, the co-optimization
    LP degenerates to exactly the M1 energy-only problem: the objective must
    match optimize_dispatch on the same prices/battery within 1e-6, and
    awards_mw must be identically zero everywhere (not just revenue-equal).
    """
    prices = _synthetic_prices(seed=0)
    battery = _default_battery()
    products = DEFAULT_AS_PRODUCTS
    horizon = prices.shape[0]
    as_prices = np.random.default_rng(1).uniform(0.0, 50.0, size=(len(products), horizon))
    as_available = np.zeros((len(products), horizon), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)
    baseline = optimize_dispatch(prices, 1.0, battery)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(baseline.objective_value, abs=1e-6)
    assert np.all(result.awards_mw == 0.0)


def test_zero_price_availability_reproduces_energy_only_objective() -> None:
    """AC-2: as_available all True, as_prices all zero reproduces the M1 objective.

    Awards cost nothing and pay nothing at zero MCPC, so the objective must
    still match optimize_dispatch within 1e-6. Awards themselves are
    degenerate here (any feasible split earns the same $0 AS revenue) and are
    deliberately not asserted (memory: lp-optimizer-degeneracy-in-tests).
    """
    prices = _synthetic_prices(seed=0)
    battery = _default_battery()
    products = DEFAULT_AS_PRODUCTS
    horizon = prices.shape[0]
    as_prices = np.zeros((len(products), horizon))
    as_available = np.ones((len(products), horizon), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)
    baseline = optimize_dispatch(prices, 1.0, battery)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(baseline.objective_value, abs=1e-6)


def test_pure_reg_up_golden_equals_240() -> None:
    """AC-3: T=24, dt=1, energy prices all $0, battery 1 MW/1 MWh, eff 1.0/1.0.

    REG_UP only, sustain 1.0 h, MCPC $10 every hour. Optimal: charge 1 MW in
    hour 0 (free energy; SoC ends hour 0 full at 1.0 MWh, which backs an
    hour-0 award under the end-of-interval convention), then award 1 MW
    every hour (adequacy caps at SoC 1.0; idle coupling caps at power_mw).
    24 * 1 * $10 == 240.0.
    """
    horizon = 24
    prices = np.zeros(horizon)
    battery = BatterySpec(power_mw=1.0, energy_mwh=1.0, charge_eff=1.0, discharge_eff=1.0)
    products = (AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),)
    as_prices = np.full((1, horizon), 10.0)
    as_available = np.ones((1, horizon), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(240.0, abs=1e-6)
    assert result.as_revenue_usd == pytest.approx(240.0, abs=1e-6)
    assert result.energy_revenue_usd == pytest.approx(0.0, abs=1e-6)


def test_pure_reg_up_with_double_capacity_golden_equals_250() -> None:
    """AC-3 note: same setup with 2 MWh capacity reaches $250, not $240.

    The 1 MWh capacity in the primary golden is load-bearing: with 2 MWh the
    LP legitimately reaches $250 by charging again in hour 1, because
    charging raises the up-coupling headroom to 2 MW for that hour.
    """
    horizon = 24
    prices = np.zeros(horizon)
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=1.0, discharge_eff=1.0)
    products = (AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),)
    as_prices = np.full((1, horizon), 10.0)
    as_available = np.ones((1, horizon), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(250.0, abs=1e-6)


def test_additive_energy_and_reg_up_golden_equals_250() -> None:
    """AC-4: T=2, dt=1, energy prices [$0, $100], battery 1 MW/1 MWh, eff 1.0/1.0.

    REG_UP only, sustain 1.0 h, MCPC [$150, $0]. Optimal: hour 0 charge 1 MW
    (s_0 = 1, coupling (0 - 1) + a <= 1 allows a <= 2, adequacy allows
    a <= 1) and award 1 MW for $150; hour 1 discharge for $100. Objective ==
    250.0. Locks in both pinned conventions: end-of-interval adequacy AND
    awards-beyond-power while charging (a_0 could reach 2 by coupling alone,
    but adequacy caps it at 1).
    """
    prices = np.array([0.0, 100.0])
    battery = BatterySpec(power_mw=1.0, energy_mwh=1.0, charge_eff=1.0, discharge_eff=1.0)
    products = (AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),)
    as_prices = np.array([[150.0, 0.0]])
    as_available = np.ones((1, 2), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(250.0, abs=1e-6)
    assert result.energy_revenue_usd == pytest.approx(100.0, abs=1e-6)
    assert result.as_revenue_usd == pytest.approx(150.0, abs=1e-6)
    assert result.dispatch.charge_mw[0] == pytest.approx(1.0, abs=1e-6)
    assert result.dispatch.discharge_mw[1] == pytest.approx(1.0, abs=1e-6)
    assert result.awards_mw[0, 0] == pytest.approx(1.0, abs=1e-6)


def test_reg_down_room_golden_equals_150() -> None:
    """AC-5: T=2, dt=1, energy prices [$0, $0], battery 1 MW/2 MWh, eff 1.0/1.0.

    Initial SoC 2.0 (full). REG_DOWN only, sustain 1.0 h, MCPC [$50, $50].
    Optimal: discharge 1 MW each hour purely to open room; hour 0 award 1 MW
    (room 2 - s_0 = 1), hour 1 award 2 MW (room 2, coupling (0 - 1) + a <= 1
    allows a <= 2). 50 + 100 == 150.0. Locks in the down-room adequacy and
    the swing capability (hour 1's award of 2 MW exceeds power_mw == 1).
    """
    prices = np.array([0.0, 0.0])
    battery = BatterySpec(
        power_mw=1.0, energy_mwh=2.0, charge_eff=1.0, discharge_eff=1.0, initial_soc_mwh=2.0
    )
    products = (AsProduct(name="REG_DOWN", direction="down", sustain_hours=1.0),)
    as_prices = np.array([[50.0, 50.0]])
    as_available = np.ones((1, 2), dtype=bool)

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert result.dispatch.solver_status == "optimal"
    assert result.dispatch.objective_value == pytest.approx(150.0, abs=1e-6)
    assert result.as_revenue_usd == pytest.approx(150.0, abs=1e-6)
    assert result.awards_mw[0, 0] == pytest.approx(1.0, abs=1e-6)
    assert result.awards_mw[0, 1] == pytest.approx(2.0, abs=1e-6)

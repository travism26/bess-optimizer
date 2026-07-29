"""Golden-value tests for optimize_dispatch (acceptance criteria 1-4).

Each test constructs a tiny synthetic price series with a hand-derivable
optimum and asserts the objective to 1e-6. No fixtures, no network.
"""

from __future__ import annotations

import numpy as np
import pytest

from bess.models import BatterySpec
from bess.optimizer.lp import optimize_dispatch


def test_flat_prices_yield_zero_revenue() -> None:
    """AC-1: T=24, all prices $50, eff 0.9/0.9. Objective == 0.0, not zero dispatch."""
    prices = np.full(24, 50.0)
    battery = BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.9, discharge_eff=0.9)

    result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

    assert result.solver_status == "optimal"
    assert result.objective_value == pytest.approx(0.0, abs=1e-6)


def test_step_prices_lossless_charges_low_discharges_high() -> None:
    """AC-2: T=24, hours 0-11 at $10, 12-23 at $100. 1 MW/2 MWh, eff 1.0/1.0.

    Optimal: charge 2 MWh at $10 (cost $20), discharge 2 MWh at $100
    (revenue $200). Objective == 180.0.
    """
    prices = np.concatenate([np.full(12, 10.0), np.full(12, 100.0)])
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=1.0, discharge_eff=1.0)

    result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

    net_dispatch = result.discharge_mw - result.charge_mw

    assert result.solver_status == "optimal"
    assert result.objective_value == pytest.approx(180.0, abs=1e-6)
    # With eff 1.0/1.0 the LP is degenerate in gross throughput (a same-hour
    # charge/discharge pair is revenue-neutral), so only the net transfer per
    # window, not the raw charge/discharge split, is guaranteed by the optimum.
    assert net_dispatch[:12].sum() == pytest.approx(-2.0, abs=1e-6)
    assert net_dispatch[12:].sum() == pytest.approx(2.0, abs=1e-6)


def test_step_prices_lossy_charge_efficiency() -> None:
    """AC-3: same step prices, 1 MW/2 MWh, charge_eff 0.8, discharge_eff 1.0.

    Optimal: draw 2.5 MWh from the grid to fill 2 MWh of usable capacity,
    costing $25, then discharge 2 MWh for $200. Objective == 175.0.
    """
    prices = np.concatenate([np.full(12, 10.0), np.full(12, 100.0)])
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=0.8, discharge_eff=1.0)

    result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

    assert result.solver_status == "optimal"
    assert result.objective_value == pytest.approx(175.0, abs=1e-6)
    assert result.charge_mw[:12].sum() == pytest.approx(2.5, abs=1e-6)
    assert result.discharge_mw[12:].sum() == pytest.approx(2.0, abs=1e-6)


def test_negative_price_hour_is_paid_to_charge() -> None:
    """AC-4: T=24, one hour at -$50, all others $0. 1 MW/2 MWh, eff 0.9/0.9.

    Optimal: charge 1 MW during the negative hour, paid $50. Objective == 50.0.
    """
    prices = np.zeros(24)
    negative_hour = 7
    prices[negative_hour] = -50.0
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=0.9, discharge_eff=0.9)

    result = optimize_dispatch(prices, dt_hours=1.0, battery=battery)

    assert result.solver_status == "optimal"
    assert result.objective_value == pytest.approx(50.0, abs=1e-6)
    assert result.charge_mw[negative_hour] == pytest.approx(1.0, abs=1e-6)

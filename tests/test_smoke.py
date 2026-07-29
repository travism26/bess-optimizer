"""Smoke tests: the skeleton itself is importable and the contracts hold.

These are the only real tests in the scaffold; everything else is TODO
scaffolding for the acceptance criteria. They keep CI green from the first
commit and lock in the frozen-dataclass contract.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from bess.models import BacktestResult, BatterySpec, DispatchResult


def test_imports_resolve() -> None:
    import bess
    import bess.backtest.runner
    import bess.cli
    import bess.data.prices
    import bess.optimizer.lp
    import bess.viz.plots

    assert bess.__version__


def test_battery_spec_constructs_with_spec_defaults() -> None:
    spec = BatterySpec(
        power_mw=100.0,
        energy_mwh=200.0,
        charge_eff=0.927,
        discharge_eff=0.927,
    )
    assert spec.initial_soc_mwh == 0.0
    assert spec.max_cycles_per_day is None


def test_frozen_dataclasses_reject_mutation() -> None:
    battery = BatterySpec(power_mw=1.0, energy_mwh=2.0, charge_eff=0.9, discharge_eff=0.9)
    dispatch = DispatchResult(
        charge_mw=np.zeros(24),
        discharge_mw=np.zeros(24),
        soc_mwh=np.zeros(24),
        objective_value=0.0,
        solver_status="optimal",
        simultaneous_hours=0,
    )
    backtest = BacktestResult(
        location="HB_NORTH",
        total_revenue_usd=0.0,
        revenue_per_mw_year=0.0,
        revenue_per_mwh_discharged=0.0,
        total_discharged_mwh=0.0,
        equivalent_full_cycles=0.0,
        daily_revenue=pd.Series(dtype="float64"),
        simultaneous_hours=0,
        solve_time_seconds=0.0,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        battery.power_mw = 999.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        dispatch.objective_value = 999.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        backtest.total_revenue_usd = 999.0  # type: ignore[misc]

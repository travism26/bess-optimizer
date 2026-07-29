"""Frozen dataclasses shared across the whole project.

These are the frozen contracts from specs/M1_python_core.md. The M4 Rust engine
must produce and consume these exact shapes, so do not rename, reorder, or
retype fields without a spec change.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BatterySpec:
    """Physical and operational parameters of a battery energy storage system.

    Efficiencies are one-way fractions. The default config uses 0.927 each way,
    which is sqrt(0.86), for an 86 percent round trip.
    """

    power_mw: float  # symmetric charge/discharge limit
    energy_mwh: float  # usable capacity (SoC upper bound)
    charge_eff: float  # fraction, e.g. 0.927
    discharge_eff: float  # fraction, e.g. 0.927
    initial_soc_mwh: float = 0.0
    max_cycles_per_day: float | None = None  # None in M1 default config


@dataclass(frozen=True)
class DispatchResult:
    """Output of a single optimize_dispatch() solve over a T-interval horizon.

    simultaneous_hours counts intervals where the LP charges and discharges at
    once. That is expected, profitable behavior at negative prices (energy is
    burned through efficiency losses); it is reported and logged, never raised.
    """

    charge_mw: np.ndarray  # shape (T,), >= 0
    discharge_mw: np.ndarray  # shape (T,), >= 0
    soc_mwh: np.ndarray  # shape (T,), SoC at END of each interval
    objective_value: float  # $ revenue from the solver
    solver_status: str  # must be "optimal" for success
    simultaneous_hours: int  # count of t where both charge and discharge > 1e-3 MW


@dataclass(frozen=True)
class BacktestResult:
    """Revenue metrics for one location, per the spec's "Backtest metrics" section.

    Serialized to JSON per hub by the backtest CLI; daily_revenue is a
    date-indexed series of $ per day. solve_time_seconds records the wall-clock
    LP solve time required by acceptance criterion 7.
    """

    location: str  # e.g. "HB_NORTH"
    total_revenue_usd: float  # $ over the full backtest window
    revenue_per_mw_year: float  # $/MW-yr
    revenue_per_mwh_discharged: float  # $/MWh
    total_discharged_mwh: float
    equivalent_full_cycles: float  # discharged MWh / energy_mwh
    daily_revenue: pd.Series  # index: date, values: $ revenue per day
    simultaneous_hours: int  # summed over the horizon
    solve_time_seconds: float  # wall-clock time of the LP solve

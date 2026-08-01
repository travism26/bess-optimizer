"""Frozen dataclasses shared across the whole project.

These are the frozen contracts from specs/M1_python_core.md (BatterySpec,
DispatchResult, BacktestResult) plus the additive M3 ancillary-service
contracts from specs/M3_ancillary_services.md (AsProduct, DEFAULT_AS_PRODUCTS,
AsDispatchResult). The M4 Rust engine must produce and consume these exact
shapes, so do not rename, reorder, or retype fields without a spec change.
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


@dataclass(frozen=True)
class AsProduct:
    """One ERCOT ancillary-service product's identity and adequacy duration.

    sustain_hours is the energy adequacy duration backing an award (the
    master spec's "LP formulation" section): how many hours of full-power
    energy an award of 1 MW must be backed by in the SoC adequacy
    constraints. It is a modeling assumption approximating ERCOT duration
    rules, not a tariff citation (specs/M3_ancillary_services.md, "Modeling
    assumptions").
    """

    name: str  # canonical product name, e.g. "REG_UP"
    direction: str  # "up" | "down"
    sustain_hours: float  # energy adequacy duration backing an award


# The five ERCOT DAM AS products with their default sustain hours
# (specs/M3_ancillary_services.md, "Config additions", [ancillary.sustain_hours]).
# REG_UP, RRS, ECRS, and NONSPIN are "up" products (capacity to increase net
# output); REG_DOWN is the sole "down" product (capacity to decrease net
# output / absorb more energy).
DEFAULT_AS_PRODUCTS: tuple[AsProduct, ...] = (
    AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),
    AsProduct(name="REG_DOWN", direction="down", sustain_hours=1.0),
    AsProduct(name="RRS", direction="up", sustain_hours=1.0),
    AsProduct(name="ECRS", direction="up", sustain_hours=2.0),
    AsProduct(name="NONSPIN", direction="up", sustain_hours=4.0),
)


@dataclass(frozen=True)
class AsDispatchResult:
    """Output of a single optimize_dispatch_as() energy + AS co-optimization solve.

    dispatch.objective_value is the FULL co-optimized dollar figure (energy
    plus AS), not energy alone. products gives the row order for awards_mw
    and is echoed back from the caller's input, never re-sorted, so it is the
    key downstream code (e.g. M3c's per-product revenue breakdown) must use
    to interpret awards_mw's rows.
    """

    dispatch: DispatchResult  # objective_value is the FULL co-optimized $
    products: tuple[AsProduct, ...]  # row order for awards_mw and as_prices
    awards_mw: np.ndarray  # shape (P, T), >= 0
    energy_revenue_usd: float  # sum_t p_t * (d_t - c_t) * dt
    as_revenue_usd: float  # sum_{p,t} q_pt * a_pt * dt

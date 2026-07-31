"""Pure parameter-sweep analytics: duration and round-trip efficiency.

specs/M2_rolling_and_benchmarks.md, "Config additions" and spec item 4.
Builds BatterySpec variants and scores each with the existing perfect- and
rolling-horizon entry points; returns plain JSON-serializable dicts. No file
I/O here (spec gotcha 3): bess.cli owns paths, JSON, and the plot.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from bess.backtest.rolling import RollingConfig, run_backtest_rolling
from bess.backtest.runner import run_backtest
from bess.models import BacktestResult, BatterySpec, DispatchResult
from bess.optimizer.lp import optimize_dispatch

# Documents the efficiency sweep's sqrt-per-side split (spec gotcha 2),
# echoed verbatim into the sweep JSON so a reader never has to guess why
# round_trip_efficiency=0.86 shows charge_eff=discharge_eff=0.9273618...
EFFICIENCY_CONVENTION_NOTE = (
    "round_trip_efficiency is split into charge_eff = discharge_eff = "
    "sqrt(round_trip_efficiency), matching optimize_dispatch's default "
    "0.927-per-side / 86 percent round-trip convention (specs/M1_python_core.md)."
)


@dataclass(frozen=True)
class SweepConfig:
    """The [sweep] config.toml table (specs/M2_rolling_and_benchmarks.md)."""

    durations_h: tuple[float, ...] = (1.0, 2.0, 4.0)
    round_trip_efficiencies: tuple[float, ...] = (0.80, 0.86, 0.92)


def duration_variants(
    battery: BatterySpec, durations_h: Sequence[float]
) -> list[tuple[float, BatterySpec]]:
    """One BatterySpec variant per duration, energy_mwh = power_mw x duration_h.

    power_mw and both efficiencies are held at battery's own values; only
    energy_mwh (and therefore duration) varies.
    """
    return [
        (duration_h, replace(battery, energy_mwh=battery.power_mw * duration_h))
        for duration_h in durations_h
    ]


def efficiency_variants(
    battery: BatterySpec, round_trip_efficiencies: Sequence[float]
) -> list[tuple[float, BatterySpec]]:
    """One BatterySpec variant per round-trip efficiency, split sqrt() per side.

    power_mw and energy_mwh are held at battery's own values; only
    charge_eff and discharge_eff vary, both set to sqrt(round_trip_efficiency)
    (spec gotcha 2, EFFICIENCY_CONVENTION_NOTE).
    """
    variants = []
    for round_trip_efficiency in round_trip_efficiencies:
        one_way_eff = math.sqrt(round_trip_efficiency)
        variants.append(
            (
                round_trip_efficiency,
                replace(battery, charge_eff=one_way_eff, discharge_eff=one_way_eff),
            )
        )
    return variants


def _scalar_metrics(result: BacktestResult) -> dict[str, Any]:
    """JSON-serializable scalar fields of a BacktestResult (no daily_revenue).

    Deliberately not imported from bess.cli._comparison_row: this module has
    no dependency on the Typer CLI layer, keeping analytics pure and
    independently testable (spec gotcha 3).
    """
    return {
        "location": result.location,
        "total_revenue_usd": result.total_revenue_usd,
        "revenue_per_mw_year": result.revenue_per_mw_year,
        "revenue_per_mwh_discharged": result.revenue_per_mwh_discharged,
        "total_discharged_mwh": result.total_discharged_mwh,
        "equivalent_full_cycles": result.equivalent_full_cycles,
        "simultaneous_hours": result.simultaneous_hours,
        "solve_time_seconds": result.solve_time_seconds,
    }


def run_sweep(
    prices_df: pd.DataFrame,
    battery: BatterySpec,
    sweep_config: SweepConfig,
    rolling_config: RollingConfig,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> dict[str, Any]:
    """Run both 1-D sweeps (duration, round-trip efficiency) in both modes.

    For each variant battery, solves the full-horizon perfect-foresight
    backtest (bess.backtest.runner.run_backtest) and the rolling-horizon
    backtest (bess.backtest.rolling.run_backtest_rolling, using
    rolling_config) on the same prices_df (one location), and records both
    BacktestResults' scalar metrics. optimizer is injected into both, same
    seam as run_backtest/run_backtest_rolling, so the M4 Rust engine drops
    into sweeps unchanged.

    Returns a plain dict (no file I/O):
    {
      "duration": [{"duration_h", "energy_mwh", "perfect": {...}, "rolling": {...}}, ...],
      "efficiency": [{"round_trip_efficiency", "charge_eff", "discharge_eff",
                       "perfect": {...}, "rolling": {...}}, ...],
    }
    """
    duration: list[dict[str, Any]] = []
    for duration_h, variant in duration_variants(battery, sweep_config.durations_h):
        perfect = run_backtest(prices_df, variant, optimizer=optimizer)
        rolling = run_backtest_rolling(prices_df, variant, rolling_config, optimizer=optimizer)
        duration.append(
            {
                "duration_h": duration_h,
                "energy_mwh": variant.energy_mwh,
                "perfect": _scalar_metrics(perfect),
                "rolling": _scalar_metrics(rolling),
            }
        )

    efficiency: list[dict[str, Any]] = []
    for round_trip_efficiency, variant in efficiency_variants(
        battery, sweep_config.round_trip_efficiencies
    ):
        perfect = run_backtest(prices_df, variant, optimizer=optimizer)
        rolling = run_backtest_rolling(prices_df, variant, rolling_config, optimizer=optimizer)
        efficiency.append(
            {
                "round_trip_efficiency": round_trip_efficiency,
                "charge_eff": variant.charge_eff,
                "discharge_eff": variant.discharge_eff,
                "perfect": _scalar_metrics(perfect),
                "rolling": _scalar_metrics(rolling),
            }
        )

    return {"duration": duration, "efficiency": efficiency}

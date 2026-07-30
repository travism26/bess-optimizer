"""Matplotlib plots for the M1 backtest.

The spec requires two plots: a 7-day dispatch detail (price, charge/discharge,
SoC on a twin axis) and cumulative revenue by hub. Signatures here are not
spec-frozen; keep them stable anyway so the CLI and tests do not churn.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: CI and tests never have a display

import matplotlib.pyplot as plt
import pandas as pd

from bess.models import DispatchResult

# Bar width in matplotlib's date units (days) for the charge/discharge bars,
# tuned for hourly settlement intervals (the only cadence this project uses):
# slightly under 1/24 of a day so adjacent hourly bars sit close but distinct.
_BAR_WIDTH_DAYS = 0.8 / 24


def plot_dispatch_detail(
    prices_df: pd.DataFrame,
    result: DispatchResult,
    output_path: Path,
    window_start: date | None = None,
    window_days: int = 7,
) -> Path:
    """Render the 7-day dispatch detail plot and return the written PNG path.

    Two aligned panels over a window_days window starting at window_start
    (default: the UTC calendar day of the first row): price ($/MWh) on top,
    and charge/discharge bars (MW) with SoC (MWh) on a twin y-axis below.
    result's arrays must be positionally aligned with prices_df's rows (as
    returned by bess.backtest.runner.solve_dispatch for the same prices_df).
    """
    start_ts = (
        pd.Timestamp(window_start, tz="UTC")
        if window_start is not None
        else pd.Timestamp(prices_df["interval_start_utc"].iloc[0]).floor("D")
    )
    end_ts = start_ts + pd.Timedelta(window_days, unit="D")
    mask = (
        (prices_df["interval_start_utc"] >= start_ts) & (prices_df["interval_start_utc"] < end_ts)
    ).to_numpy()

    times = prices_df.loc[mask, "interval_start_utc"]
    prices = prices_df.loc[mask, "price"]
    charge_mw = result.charge_mw[mask]
    discharge_mw = result.discharge_mw[mask]
    soc_mwh = result.soc_mwh[mask]
    location = str(prices_df["location"].iloc[0])

    fig, (ax_price, ax_dispatch) = plt.subplots(2, 1, sharex=True, figsize=(12, 7))

    ax_price.plot(times, prices, color="tab:blue")
    ax_price.axhline(0.0, color="black", linewidth=0.5)
    ax_price.set_ylabel("Price ($/MWh)")
    ax_price.set_title(
        f"{location} dispatch detail: {start_ts.date()} to "
        f"{(end_ts - pd.Timedelta(1, unit='h')).date()} (UTC)"
    )

    ax_dispatch.bar(
        times, discharge_mw, width=_BAR_WIDTH_DAYS, color="tab:green", label="Discharge (MW)"
    )
    ax_dispatch.bar(times, -charge_mw, width=_BAR_WIDTH_DAYS, color="tab:red", label="Charge (MW)")
    ax_dispatch.axhline(0.0, color="black", linewidth=0.5)
    ax_dispatch.set_ylabel("Dispatch (MW)")
    ax_dispatch.set_xlabel("Time (UTC)")

    ax_soc = ax_dispatch.twinx()
    ax_soc.plot(times, soc_mwh, color="tab:purple", label="SoC (MWh)")
    ax_soc.set_ylabel("State of charge (MWh)")

    dispatch_handles, dispatch_labels = ax_dispatch.get_legend_handles_labels()
    soc_handles, soc_labels = ax_soc.get_legend_handles_labels()
    ax_dispatch.legend(
        dispatch_handles + soc_handles, dispatch_labels + soc_labels, loc="upper right"
    )

    fig.autofmt_xdate()
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
    return output_path


def plot_sweep_duration(
    sweep_results_by_hub: dict[str, dict[str, Any]],
    output_path: Path,
) -> Path:
    """Revenue per MW-year vs duration, one line per hub, solid rolling / dashed perfect.

    sweep_results_by_hub maps hub -> the dict bess.analytics.sweep.run_sweep
    returns for that hub; only its "duration" entry (a list of
    {"duration_h", "perfect": {...}, "rolling": {...}}) is used. Each hub
    gets one color, shared between its solid (rolling) and dashed (perfect)
    lines, so the two modes are visually paired per hub. Saved as PNG.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    for hub, sweep_result in sweep_results_by_hub.items():
        duration_points = sweep_result["duration"]
        durations_h = [point["duration_h"] for point in duration_points]
        rolling_revenue = [point["rolling"]["revenue_per_mw_year"] for point in duration_points]
        perfect_revenue = [point["perfect"]["revenue_per_mw_year"] for point in duration_points]

        (rolling_line,) = ax.plot(
            durations_h, rolling_revenue, linestyle="-", marker="o", label=f"{hub} (rolling)"
        )
        ax.plot(
            durations_h,
            perfect_revenue,
            linestyle="--",
            marker="o",
            color=rolling_line.get_color(),
            label=f"{hub} (perfect)",
        )

    ax.set_xlabel("Duration (h); energy_mwh = power_mw x duration_h")
    ax.set_ylabel("Revenue ($/MW-yr)")
    ax.set_title("Duration sweep: revenue per MW-year vs battery duration")
    ax.legend(loc="upper left")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
    return output_path


def plot_cumulative_revenue(
    daily_revenue_by_hub: dict[str, pd.Series],
    output_path: Path,
) -> Path:
    """Render cumulative revenue by hub over time and return the written PNG path.

    One line per hub: the running cumulative sum of that hub's daily_revenue
    series (BacktestResult.daily_revenue, UTC-day grouped) over the full
    backtest window, with a labeled legend. Saved as PNG.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    for hub, daily_revenue in daily_revenue_by_hub.items():
        cumulative = daily_revenue.sort_index().cumsum()
        ax.plot(cumulative.index, cumulative.to_numpy(), label=hub)

    ax.axhline(0.0, color="black", linewidth=0.5)
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("Cumulative revenue ($)")
    ax.set_title("Cumulative day-ahead arbitrage revenue")
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
    return output_path

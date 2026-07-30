"""Typer CLI: `bess fetch`, `bess backtest`, `bess plot`.

All commands read the TOML config (spec section "Default config") for battery
parameters, locations, and the date window. `bess fetch` is the only code path
that touches the network; backtest and plot run entirely from the parquet cache.
"""

from __future__ import annotations

import json
import tomllib
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

import pandas as pd
import typer

from bess.backtest.rolling import RollingConfig, run_backtest_rolling
from bess.backtest.runner import metrics_from_dispatch, solve_dispatch
from bess.data.prices import fetch_da_prices
from bess.models import BacktestResult, BatterySpec
from bess.viz.plots import plot_cumulative_revenue, plot_dispatch_detail

app = typer.Typer(help="BESS day-ahead energy arbitrage optimizer and backtester.")


class BacktestMode(StrEnum):
    """`bess backtest --mode`: perfect (M1, default) or rolling (M2)."""

    perfect = "perfect"
    rolling = "rolling"


ConfigOption = Annotated[
    Path,
    typer.Option("--config", help="Path to the TOML config file."),
]
OutputDirOption = Annotated[
    Path | None,
    typer.Option(
        "--output-dir", help="Directory for metrics JSON and PNG plots. Overrides config.toml."
    ),
]

# Not part of the master spec's frozen config.toml key list; used only as a
# fallback when config.toml has no cache_dir/output_dir key and no override
# flag is given.
_DEFAULT_CACHE_DIR = Path("data")
_DEFAULT_OUTPUT_DIR = Path("output")


def _load_settings(config: Path) -> dict[str, Any]:
    with config.open("rb") as f:
        return tomllib.load(f)


def _battery_from_settings(settings: dict[str, Any]) -> BatterySpec:
    return BatterySpec(
        power_mw=settings["power_mw"],
        energy_mwh=settings["energy_mwh"],
        charge_eff=settings["charge_eff"],
        discharge_eff=settings["discharge_eff"],
        initial_soc_mwh=settings.get("initial_soc_mwh", 0.0),
        max_cycles_per_day=settings.get("max_cycles_per_day"),
    )


def _metrics_dict(result: BacktestResult) -> dict[str, Any]:
    """Full JSON-serializable view of a BacktestResult, including daily_revenue."""
    return {
        "location": result.location,
        "total_revenue_usd": result.total_revenue_usd,
        "revenue_per_mw_year": result.revenue_per_mw_year,
        "revenue_per_mwh_discharged": result.revenue_per_mwh_discharged,
        "total_discharged_mwh": result.total_discharged_mwh,
        "equivalent_full_cycles": result.equivalent_full_cycles,
        "daily_revenue": {
            cast(date, day).isoformat(): revenue for day, revenue in result.daily_revenue.items()
        },
        "simultaneous_hours": result.simultaneous_hours,
        "solve_time_seconds": result.solve_time_seconds,
    }


def _comparison_row(result: BacktestResult) -> dict[str, Any]:
    """One row of the combined comparison table: scalar metrics, no daily series."""
    row = _metrics_dict(result)
    del row["daily_revenue"]
    return row


def _rolling_config_from_settings(settings: dict[str, Any]) -> RollingConfig:
    """The [rolling] config.toml table, falling back to RollingConfig's defaults."""
    rolling_settings = settings.get("rolling", {})
    return RollingConfig(
        lookahead_days=rolling_settings.get("lookahead_days", RollingConfig.lookahead_days),
        forecast=rolling_settings.get("forecast", RollingConfig.forecast),
    )


def _mode_block(rolling_config: RollingConfig | None) -> dict[str, Any]:
    """The additive `mode` block in metrics JSON (specs/M2_rolling_and_benchmarks.md).

    rolling_config is None for a perfect-foresight run, which emits only
    {"mode": "perfect"}; a rolling run also echoes lookahead_days and forecast.
    """
    if rolling_config is None:
        return {"mode": "perfect"}
    return {
        "mode": "rolling",
        "lookahead_days": rolling_config.lookahead_days,
        "forecast": rolling_config.forecast,
    }


def _run_location(
    location: str,
    start: date,
    end: date,
    cache_dir: Path,
    battery: BatterySpec,
    output_dir: Path,
    rolling_config: RollingConfig | None = None,
) -> BacktestResult:
    """Load cached prices, solve once, write the dispatch-detail PNG, return metrics.

    Shared by `backtest` and `plot` so a single command invocation solves each
    location's LP exactly once even though both commands need the
    dispatch-detail plot. rolling_config selects M2 rolling-horizon mode; the
    dispatch-detail plot is a per-interval view of one full-horizon LP solve
    (M2b's concern), so it is only produced in the default perfect mode.
    """
    prices_df = fetch_da_prices(location, start, end, cache_dir)
    if rolling_config is not None:
        return run_backtest_rolling(prices_df, battery, rolling_config)
    dispatch, solve_time_seconds = solve_dispatch(prices_df, battery)
    result = metrics_from_dispatch(location, prices_df, battery, dispatch, solve_time_seconds)
    plot_dispatch_detail(prices_df, dispatch, output_dir / f"{location}_dispatch_detail.png")
    return result


@app.command()
def fetch(
    config: ConfigOption = Path("config.toml"),
    locations: Annotated[
        list[str] | None,
        typer.Option("--location", help="Hub to fetch. Repeatable; overrides config.toml."),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="Window start date (YYYY-MM-DD). Overrides config.toml."),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help="Window end date (YYYY-MM-DD). Overrides config.toml."),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Parquet cache directory. Overrides config.toml."),
    ] = None,
) -> None:
    """Fetch DA hub prices via gridstatus into the local parquet cache.

    For each configured location, calls bess.data.prices.fetch_da_prices over
    the configured window and reports what was cached. This is the only
    command that touches the network (acceptance criterion 9: CI never runs
    it).
    """
    settings = _load_settings(config)

    resolved_locations = locations if locations else settings["locations"]
    resolved_start = date.fromisoformat(start) if start else settings["start"]
    resolved_end = date.fromisoformat(end) if end else settings["end"]
    resolved_cache_dir = cache_dir or Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))

    for location in resolved_locations:
        df = fetch_da_prices(location, resolved_start, resolved_end, resolved_cache_dir)
        typer.echo(
            f"{location}: {len(df)} rows for [{resolved_start}, {resolved_end}] "
            f"cached under {resolved_cache_dir}"
        )


@app.command()
def backtest(
    config: ConfigOption = Path("config.toml"),
    output_dir: OutputDirOption = None,
    mode: Annotated[
        BacktestMode,
        typer.Option(
            "--mode",
            help="'perfect' (default, full horizon) or 'rolling' (M2, one market day at a time).",
        ),
    ] = BacktestMode.perfect,
) -> None:
    """Run the backtest for every configured location.

    Loads cached prices (never touches the network itself; run `bess fetch`
    first) and writes one {location}_metrics.json plus a combined
    comparison.json under the output directory. In the default perfect mode,
    solves the LP once per location via bess.backtest.runner and also writes
    the 7-day dispatch-detail PNG per location; in rolling mode (M2), solves
    via bess.backtest.rolling using the [rolling] config.toml table
    (lookahead_days, forecast). Every metrics JSON gains an additive `mode`
    block regardless of mode. Both modes write the cumulative-revenue PNG
    across all locations.

    Covered by acceptance criterion 8 (M1): `bess backtest --config
    config.toml` against cached fixtures produces metrics JSON and both PNG
    plots. Covered by acceptance criterion 9 (M2a): `--mode rolling` writes
    metrics JSON containing the `mode` block plus every M1 metric field.
    """
    settings = _load_settings(config)
    battery = _battery_from_settings(settings)
    cache_dir = Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))
    resolved_output_dir = output_dir or Path(settings.get("output_dir", _DEFAULT_OUTPUT_DIR))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    rolling_config = (
        _rolling_config_from_settings(settings) if mode == BacktestMode.rolling else None
    )

    comparison: list[dict[str, Any]] = []
    daily_revenue_by_location: dict[str, pd.Series] = {}
    for location in settings["locations"]:
        result = _run_location(
            location,
            settings["start"],
            settings["end"],
            cache_dir,
            battery,
            resolved_output_dir,
            rolling_config=rolling_config,
        )

        metrics = _metrics_dict(result)
        metrics["mode"] = _mode_block(rolling_config)
        metrics_path = resolved_output_dir / f"{location}_metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True))
        typer.echo(f"{location}: revenue=${result.total_revenue_usd:,.2f} -> {metrics_path}")

        comparison.append({k: v for k, v in metrics.items() if k != "daily_revenue"})
        daily_revenue_by_location[location] = result.daily_revenue

    comparison_path = resolved_output_dir / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2, sort_keys=True))
    typer.echo(f"Comparison table -> {comparison_path}")

    revenue_plot_path = resolved_output_dir / "cumulative_revenue.png"
    plot_cumulative_revenue(daily_revenue_by_location, revenue_plot_path)
    typer.echo(f"Cumulative revenue plot -> {revenue_plot_path}")


@app.command()
def plot(config: ConfigOption = Path("config.toml"), output_dir: OutputDirOption = None) -> None:
    """Generate the 7-day dispatch detail and cumulative revenue PNGs.

    Runs the same per-location pipeline as `backtest` (load cached prices,
    solve once) but writes only the two plots, not the metrics JSON: useful
    for regenerating plots without rewriting already-published metrics.
    """
    settings = _load_settings(config)
    battery = _battery_from_settings(settings)
    cache_dir = Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))
    resolved_output_dir = output_dir or Path(settings.get("output_dir", _DEFAULT_OUTPUT_DIR))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    daily_revenue_by_location: dict[str, pd.Series] = {}
    for location in settings["locations"]:
        result = _run_location(
            location, settings["start"], settings["end"], cache_dir, battery, resolved_output_dir
        )
        dispatch_plot_path = resolved_output_dir / f"{location}_dispatch_detail.png"
        typer.echo(f"{location}: dispatch detail -> {dispatch_plot_path}")
        daily_revenue_by_location[location] = result.daily_revenue

    revenue_plot_path = resolved_output_dir / "cumulative_revenue.png"
    plot_cumulative_revenue(daily_revenue_by_location, revenue_plot_path)
    typer.echo(f"Cumulative revenue plot -> {revenue_plot_path}")


if __name__ == "__main__":
    app()

"""Typer CLI: `bess fetch`, `bess backtest`, `bess plot`.

All commands read the TOML config (spec section "Default config") for battery
parameters, locations, and the date window. `bess fetch` is the only code path
that touches the network; backtest and plot run entirely from the parquet cache.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import replace
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

import pandas as pd
import typer

from bess.analytics.benchmarks import (
    as_uplift,
    daily_tbk,
    foresight_capture_rate,
    revenue_mix,
    tb4_capture,
    tbk_summary,
)
from bess.analytics.sweep import EFFICIENCY_CONVENTION_NOTE, SweepConfig, run_sweep
from bess.backtest.as_runner import run_backtest_as
from bess.backtest.rolling import RollingConfig, run_backtest_rolling
from bess.backtest.runner import metrics_from_dispatch, solve_dispatch
from bess.data.as_prices import fetch_as_prices
from bess.data.prices import fetch_da_prices
from bess.models import (
    DEFAULT_AS_PRODUCTS,
    AsBacktestResult,
    AsProduct,
    BacktestResult,
    BatterySpec,
)
from bess.viz.plots import plot_cumulative_revenue, plot_dispatch_detail, plot_sweep_duration

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


def _sweep_config_from_settings(settings: dict[str, Any]) -> SweepConfig:
    """The [sweep] config.toml table, falling back to SweepConfig's defaults."""
    sweep_settings = settings.get("sweep", {})
    return SweepConfig(
        durations_h=tuple(sweep_settings.get("durations_h", SweepConfig.durations_h)),
        round_trip_efficiencies=tuple(
            sweep_settings.get("round_trip_efficiencies", SweepConfig.round_trip_efficiencies)
        ),
    )


def _mode_metrics_path(output_dir: Path, location: str, mode: str) -> Path:
    """The mode-qualified metrics JSON path for one location and mode value.

    Distinct from the plain {location}_metrics.json that `backtest` also
    always writes (M1 behavior, unchanged): both perfect and rolling runs
    write that same unqualified filename, so it alone cannot hold both modes
    at once. This mode-qualified path is what lets `bess benchmark` find both
    a perfect- and a rolling-mode metrics file simultaneously.
    """
    return output_dir / f"{location}_metrics_{mode}.json"


def _read_mode_metrics(output_dir: Path, location: str, mode: str) -> dict[str, Any] | None:
    """Read _mode_metrics_path's file if present, else None.

    Cross-checks the file's own `mode` block against the requested mode, so a
    stale or hand-edited file under the expected name cannot silently
    masquerade as the wrong mode.
    """
    path = _mode_metrics_path(output_dir, location, mode)
    if not path.exists():
        return None
    metrics = cast(dict[str, Any], json.loads(path.read_text()))
    actual_mode = metrics.get("mode", {}).get("mode")
    if actual_mode != mode:
        raise ValueError(f"{path} has mode={actual_mode!r}, expected mode={mode!r}")
    return metrics


def _ancillary_enabled_from_settings(settings: dict[str, Any]) -> bool:
    """Whether `[ancillary].enabled` requests the co-opt backtest without `--ancillary`."""
    return bool(settings.get("ancillary", {}).get("enabled", False))


def _ancillary_products_from_settings(settings: dict[str, Any]) -> tuple[AsProduct, ...]:
    """The `[ancillary]` config.toml table's products, defaulting to DEFAULT_AS_PRODUCTS.

    Product names and directions are anchored to DEFAULT_AS_PRODUCTS (the five
    ERCOT products this project models, specs/M3_ancillary_services.md):
    config.toml can reorder, subset, or override sustain_hours per product via
    `[ancillary.sustain_hours]`, but cannot introduce an unknown product name.
    """
    ancillary_settings = settings.get("ancillary", {})
    default_by_name = {product.name: product for product in DEFAULT_AS_PRODUCTS}
    names = ancillary_settings.get("products", list(default_by_name))
    sustain_overrides = ancillary_settings.get("sustain_hours", {})

    products: list[AsProduct] = []
    for name in names:
        if name not in default_by_name:
            raise ValueError(
                f"Unknown AS product {name!r} in [ancillary].products; must be one of "
                f"{sorted(default_by_name)}"
            )
        default_product = default_by_name[name]
        sustain_hours = sustain_overrides.get(name, default_product.sustain_hours)
        products.append(replace(default_product, sustain_hours=sustain_hours))
    return tuple(products)


def _ancillary_block(result: AsBacktestResult, products: tuple[AsProduct, ...]) -> dict[str, Any]:
    """The additive `ancillary` block written into an ancillary-mode metrics JSON.

    specs/M3c_as_backtest_cli.md item 2: products, sustain hours,
    energy_revenue_usd, as_revenue_usd, revenue_by_product, award_mw_hours,
    total_revenue_usd (energy leg + AS leg, the M3 uplift headline's numerator).
    """
    return {
        "products": [product.name for product in products],
        "sustain_hours": {product.name: product.sustain_hours for product in products},
        "energy_revenue_usd": result.energy.total_revenue_usd,
        "as_revenue_usd": result.as_revenue_usd,
        "revenue_by_product": result.revenue_by_product.to_dict(),
        "award_mw_hours": result.award_mw_hours.to_dict(),
        "total_revenue_usd": result.total_revenue_usd,
    }


def _ancillary_metrics_path(output_dir: Path, location: str, mode: str) -> Path:
    """The mode- and ancillary-qualified metrics JSON path for one location.

    Distinct from `_mode_metrics_path`'s filename (memory:
    metrics-json-unqualified-filename-collision): both an energy-only and an
    ancillary run of the same mode must be able to coexist under one output
    directory so `bess benchmark` can read both at once.
    """
    return output_dir / f"{location}_metrics_{mode}_ancillary.json"


def _read_ancillary_metrics(output_dir: Path, location: str, mode: str) -> dict[str, Any] | None:
    """Read `_ancillary_metrics_path`'s file if present, else None.

    Mirrors `_read_mode_metrics`'s defensive mode cross-check.
    """
    path = _ancillary_metrics_path(output_dir, location, mode)
    if not path.exists():
        return None
    metrics = cast(dict[str, Any], json.loads(path.read_text()))
    actual_mode = metrics.get("mode", {}).get("mode")
    if actual_mode != mode:
        raise ValueError(f"{path} has mode={actual_mode!r}, expected mode={mode!r}")
    return metrics


def _same_window(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Whether two metrics JSONs' daily_revenue blocks span the same date range.

    Neither metrics JSON carries an explicit start/end field, so the window is
    read off the daily_revenue keys instead (gotcha 4: guards AS uplift
    against silently dividing a July co-opt total by a full-year energy-only
    total, or vice versa).
    """
    a_days = a["daily_revenue"]
    b_days = b["daily_revenue"]
    return (min(a_days), max(a_days)) == (min(b_days), max(b_days))


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
    """Fetch DA hub prices and AS clearing prices via gridstatus into the local parquet cache.

    For each configured location, calls bess.data.prices.fetch_da_prices over
    the configured window and reports what was cached. Then, once per
    invocation (ancillary MCPCs are system-wide, not per hub; spec item 4),
    calls bess.data.as_prices.fetch_as_prices over the same window. This is
    the only command that touches the network (acceptance criterion 9: CI
    never runs it).
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

    as_df = fetch_as_prices(resolved_start, resolved_end, resolved_cache_dir)
    typer.echo(
        f"AS MCPC: {len(as_df)} rows for [{resolved_start}, {resolved_end}] "
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
    ancillary: Annotated[
        bool,
        typer.Option(
            "--ancillary",
            help="Also run the M3 energy + AS co-optimized backtest (perfect mode only).",
        ),
    ] = False,
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

    `--ancillary` (or `[ancillary].enabled` in config.toml) additionally runs
    the M3 energy + AS co-optimizer (bess.backtest.as_runner.run_backtest_as)
    per location and writes {location}_metrics_{mode}_ancillary.json with the
    additive `ancillary` block (products, sustain hours, energy_revenue_usd,
    as_revenue_usd, revenue_by_product, award_mw_hours, total_revenue_usd).
    The energy-only pipeline above runs completely unchanged either way, so
    its output files are byte-identical to a run without `--ancillary`.
    Perfect mode only: `--ancillary --mode rolling` exits nonzero (M3 is
    perfect-foresight only, specs/M3_ancillary_services.md "Out of scope").

    Covered by acceptance criterion 8 (M1): `bess backtest --config
    config.toml` against cached fixtures produces metrics JSON and both PNG
    plots. Covered by acceptance criterion 9 (M2a): `--mode rolling` writes
    metrics JSON containing the `mode` block plus every M1 metric field.

    solve_time_seconds is the single intentionally non-deterministic field in
    every metrics JSON this writes (wall-clock LP solve time); every other
    field is byte-identical across repeated runs on the same inputs (closes
    the T3 review note, specs/review_issues/review-27b2b22d.md).
    """
    settings = _load_settings(config)
    ancillary_enabled = ancillary or _ancillary_enabled_from_settings(settings)
    if ancillary_enabled and mode == BacktestMode.rolling:
        typer.echo(
            "--ancillary is not supported with --mode rolling: M3 ancillary-service "
            "co-optimization is perfect-foresight only (specs/M3_ancillary_services.md, "
            "'Out of scope'). Run in --mode perfect (the default), or drop --ancillary."
        )
        raise typer.Exit(code=1)

    battery = _battery_from_settings(settings)
    cache_dir = Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))
    resolved_output_dir = output_dir or Path(settings.get("output_dir", _DEFAULT_OUTPUT_DIR))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    rolling_config = (
        _rolling_config_from_settings(settings) if mode == BacktestMode.rolling else None
    )

    ancillary_products: tuple[AsProduct, ...] | None = None
    ancillary_prices_df: pd.DataFrame | None = None
    if ancillary_enabled:
        ancillary_products = _ancillary_products_from_settings(settings)
        ancillary_prices_df = fetch_as_prices(settings["start"], settings["end"], cache_dir)

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
        # solve_time_seconds is the one intentionally non-deterministic field
        # in this JSON (wall-clock LP solve time); every other field is
        # expected to be byte-identical across repeated runs on the same
        # inputs (closes the T3 review note, specs/review_issues/review-27b2b22d.md).
        metrics_json = json.dumps(metrics, indent=2, sort_keys=True)
        metrics_path = resolved_output_dir / f"{location}_metrics.json"
        metrics_path.write_text(metrics_json)
        # Also written under a mode-qualified name (identical content) so
        # `bess benchmark` can find both a perfect- and a rolling-mode
        # metrics file at once; the unqualified name above is written by
        # both modes and would otherwise collide.
        _mode_metrics_path(resolved_output_dir, location, mode.value).write_text(metrics_json)
        typer.echo(f"{location}: revenue=${result.total_revenue_usd:,.2f} -> {metrics_path}")

        comparison.append({k: v for k, v in metrics.items() if k != "daily_revenue"})
        daily_revenue_by_location[location] = result.daily_revenue

        if ancillary_products is not None and ancillary_prices_df is not None:
            prices_df = fetch_da_prices(location, settings["start"], settings["end"], cache_dir)
            as_result = run_backtest_as(prices_df, ancillary_prices_df, battery, ancillary_products)
            ancillary_metrics = _metrics_dict(as_result.energy)
            ancillary_metrics["mode"] = _mode_block(None)
            ancillary_metrics["ancillary"] = _ancillary_block(as_result, ancillary_products)
            ancillary_json = json.dumps(ancillary_metrics, indent=2, sort_keys=True)
            ancillary_path = _ancillary_metrics_path(resolved_output_dir, location, mode.value)
            ancillary_path.write_text(ancillary_json)
            typer.echo(
                f"{location}: AS co-opt total=${as_result.total_revenue_usd:,.2f} "
                f"-> {ancillary_path}"
            )

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


@app.command()
def benchmark(
    config: ConfigOption = Path("config.toml"), output_dir: OutputDirOption = None
) -> None:
    """Compute TB2/TB4 daily-spread benchmarks and, when available, capture rates and AS uplift.

    Loads cached prices (never touches the network itself; run `bess fetch`
    first) for every configured location and computes daily TB2/TB4
    (bess.analytics.benchmarks.daily_tbk: raw prices, no efficiency
    adjustment, local America/Chicago market days) plus the mean per calendar
    year and for the requested window. When both {location}_metrics_perfect.json
    and {location}_metrics_rolling.json already exist under the output
    directory (written by a prior `bess backtest --mode perfect|rolling`),
    also computes the foresight capture rate and TB4 capture for each mode
    and includes them. When both {location}_metrics_perfect.json and
    {location}_metrics_perfect_ancillary.json exist (written by a prior `bess
    backtest --ancillary`), also computes the M3 AS uplift (co-optimized
    total revenue / energy-only revenue) and revenue mix by product. Either
    pair missing skips that section for that location with a printed notice,
    never an error, and the command still exits 0. Writes output/benchmarks.json.
    """
    settings = _load_settings(config)
    battery = _battery_from_settings(settings)
    cache_dir = Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))
    resolved_output_dir = output_dir or Path(settings.get("output_dir", _DEFAULT_OUTPUT_DIR))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    hubs: dict[str, Any] = {}
    for location in settings["locations"]:
        prices_df = fetch_da_prices(location, settings["start"], settings["end"], cache_dir)
        daily_tb2 = daily_tbk(prices_df, k=2)
        daily_tb4 = daily_tbk(prices_df, k=4)

        hub_benchmarks: dict[str, Any] = {
            "tb2": tbk_summary(daily_tb2),
            "tb4": tbk_summary(daily_tb4),
        }

        mode_metrics = {
            mode: _read_mode_metrics(resolved_output_dir, location, mode)
            for mode in ("perfect", "rolling")
        }
        missing_modes = [mode for mode, metrics in mode_metrics.items() if metrics is None]
        if missing_modes:
            typer.echo(
                f"{location}: skipping capture rates, missing {missing_modes} metrics JSON "
                "(run `bess backtest --mode ...` first)"
            )
        else:
            perfect_metrics = cast(dict[str, Any], mode_metrics["perfect"])
            rolling_metrics = cast(dict[str, Any], mode_metrics["rolling"])
            hub_benchmarks["capture"] = {
                "foresight_capture_rate": foresight_capture_rate(
                    rolling_metrics["total_revenue_usd"], perfect_metrics["total_revenue_usd"]
                ),
                "tb4_capture_perfect": tb4_capture(
                    perfect_metrics["total_revenue_usd"], daily_tb4, battery.power_mw
                ),
                "tb4_capture_rolling": tb4_capture(
                    rolling_metrics["total_revenue_usd"], daily_tb4, battery.power_mw
                ),
            }

        energy_only_metrics = mode_metrics["perfect"]
        ancillary_metrics = _read_ancillary_metrics(resolved_output_dir, location, "perfect")
        if energy_only_metrics is None or ancillary_metrics is None:
            missing = [
                f"{location}_metrics_perfect.json" if energy_only_metrics is None else None,
                f"{location}_metrics_perfect_ancillary.json" if ancillary_metrics is None else None,
            ]
            typer.echo(
                f"{location}: skipping AS uplift, missing {[m for m in missing if m]} "
                "(run `bess backtest --ancillary` first)"
            )
        else:
            if not _same_window(energy_only_metrics, ancillary_metrics):
                raise ValueError(
                    f"{location}: {location}_metrics_perfect.json and "
                    f"{location}_metrics_perfect_ancillary.json cover different windows; "
                    "AS uplift requires both from the same backtest window"
                )
            ancillary_block = cast(dict[str, Any], ancillary_metrics["ancillary"])
            hub_benchmarks["ancillary"] = {
                "as_uplift": as_uplift(
                    ancillary_block["total_revenue_usd"], energy_only_metrics["total_revenue_usd"]
                ),
                "revenue_mix": revenue_mix(ancillary_block["revenue_by_product"]),
            }

        hubs[location] = hub_benchmarks

    benchmarks_path = resolved_output_dir / "benchmarks.json"
    benchmarks_path.write_text(json.dumps(hubs, indent=2, sort_keys=True))
    typer.echo(f"Benchmarks -> {benchmarks_path}")


@app.command()
def sweep(config: ConfigOption = Path("config.toml"), output_dir: OutputDirOption = None) -> None:
    """Run the duration and round-trip-efficiency sweeps for every configured location.

    Two 1-D sweeps per hub (bess.analytics.sweep.run_sweep, the [sweep]
    config.toml table): duration over energy_mwh = power_mw x durations_h,
    and round-trip efficiency over round_trip_efficiencies split sqrt() per
    side (matching optimize_dispatch's 0.927-per-side default), each run in
    both perfect and rolling ([rolling] config defaults) mode. Writes
    output/sweep.json plus output/sweep_duration.png (revenue per MW-year vs
    duration, one line per hub, solid rolling / dashed perfect).
    """
    settings = _load_settings(config)
    battery = _battery_from_settings(settings)
    cache_dir = Path(settings.get("cache_dir", _DEFAULT_CACHE_DIR))
    resolved_output_dir = output_dir or Path(settings.get("output_dir", _DEFAULT_OUTPUT_DIR))
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    sweep_config = _sweep_config_from_settings(settings)
    rolling_config = _rolling_config_from_settings(settings)

    hubs: dict[str, Any] = {}
    for location in settings["locations"]:
        prices_df = fetch_da_prices(location, settings["start"], settings["end"], cache_dir)
        hubs[location] = run_sweep(prices_df, battery, sweep_config, rolling_config)

    sweep_results = {
        "efficiency_convention": EFFICIENCY_CONVENTION_NOTE,
        "rolling_config": _mode_block(rolling_config),
        "hubs": hubs,
    }
    sweep_path = resolved_output_dir / "sweep.json"
    sweep_path.write_text(json.dumps(sweep_results, indent=2, sort_keys=True))
    typer.echo(f"Sweep results -> {sweep_path}")

    plot_path = resolved_output_dir / "sweep_duration.png"
    plot_sweep_duration(hubs, plot_path)
    typer.echo(f"Sweep duration plot -> {plot_path}")


if __name__ == "__main__":
    app()

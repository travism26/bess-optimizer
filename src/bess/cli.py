"""Typer CLI: `bess fetch`, `bess backtest`, `bess plot`.

All commands read the TOML config (spec section "Default config") for battery
parameters, locations, and the date window. `bess fetch` is the only code path
that touches the network; backtest and plot run entirely from the parquet cache.
"""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from bess.data.prices import fetch_da_prices

app = typer.Typer(help="BESS day-ahead energy arbitrage optimizer and backtester.")

ConfigOption = Annotated[
    Path,
    typer.Option("--config", help="Path to the TOML config file."),
]

# Not part of the master spec's frozen config.toml key list; used only as a
# fallback when config.toml has no cache_dir key and --cache-dir is not given.
_DEFAULT_CACHE_DIR = Path("data")


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
    with config.open("rb") as f:
        settings = tomllib.load(f)

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
def backtest(config: ConfigOption = Path("config.toml")) -> None:
    """Run the perfect-foresight backtest for every configured location.

    Intended behavior: load cached prices, run bess.backtest.runner.run_backtest
    per hub, and emit metrics JSON per hub plus a combined comparison table.

    Covered by acceptance criterion 8: `bess backtest --config config.toml`
    against cached fixtures produces metrics JSON and both PNG plots.
    """
    raise NotImplementedError


@app.command()
def plot(config: ConfigOption = Path("config.toml")) -> None:
    """Generate the 7-day dispatch detail and cumulative revenue PNGs.

    Intended behavior: from cached prices and backtest output, write both plots
    via bess.viz.plots with nonzero content (acceptance criterion 8).
    """
    raise NotImplementedError


if __name__ == "__main__":
    app()

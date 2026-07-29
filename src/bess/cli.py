"""Typer CLI: `bess fetch`, `bess backtest`, `bess plot`.

All commands read the TOML config (spec section "Default config") for battery
parameters, locations, and the date window. `bess fetch` is the only code path
that touches the network; backtest and plot run entirely from the parquet cache.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="BESS day-ahead energy arbitrage optimizer and backtester.")

ConfigOption = Annotated[
    Path,
    typer.Option("--config", help="Path to the TOML config file."),
]


@app.command()
def fetch(config: ConfigOption = Path("config.toml")) -> None:
    """Fetch DA hub prices via gridstatus into the local parquet cache.

    Intended behavior: for each configured location, call
    bess.data.prices.fetch_da_prices over the configured window and report what
    was cached. This is the only command that touches the network (acceptance
    criterion 9: CI never runs it).
    """
    raise NotImplementedError


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

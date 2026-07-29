"""Matplotlib plots for the M1 backtest.

The spec requires two plots: a 7-day dispatch detail (price, charge/discharge,
SoC) and cumulative revenue by hub. Signatures here are not spec-frozen; keep
them stable anyway so the CLI and tests do not churn.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from bess.models import DispatchResult


def plot_dispatch_detail(
    prices_df: pd.DataFrame,
    result: DispatchResult,
    output_path: Path,
    window_start: date | None = None,
    window_days: int = 7,
) -> Path:
    """Render the 7-day dispatch detail plot and return the written PNG path.

    Intended behavior: three aligned panels over a window_days window starting
    at window_start (default: first day of the horizon): price ($/MWh),
    charge/discharge (MW, signed or paired), and SoC (MWh). Saved as PNG with
    nonzero content.

    Covered by acceptance criterion 8 (CLI end-to-end produces both PNG plots),
    tested in tests/test_backtest_integration.py.
    """
    raise NotImplementedError


def plot_cumulative_revenue(
    daily_revenue_by_hub: dict[str, pd.Series],
    output_path: Path,
) -> Path:
    """Render cumulative revenue by hub over time and return the written PNG path.

    Intended behavior: one line per hub, cumulative sum of the daily revenue
    series, labeled legend, saved as PNG with nonzero content.

    Covered by acceptance criterion 8 (CLI end-to-end produces both PNG plots),
    tested in tests/test_backtest_integration.py.
    """
    raise NotImplementedError

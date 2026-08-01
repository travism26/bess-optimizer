"""Pure benchmark analytics: daily TBk spreads and capture rates.

specs/M2_rolling_and_benchmarks.md, "Benchmark definitions" section, exact
and reproducible. Every function here takes and returns plain values (a
canonical-schema price frame, a pandas Series, floats): no file I/O and no
CLI concerns (spec gotcha 3). bess.cli owns paths, JSON, and reading the
two mode-qualified metrics files that feed the capture-rate functions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bess.backtest.rolling import _day_blocks, _local_market_day


def daily_tbk(prices_df: pd.DataFrame, k: int) -> pd.Series:
    """Daily TBk ($/MW-day) per local market day (America/Chicago).

    TBk is the sum of the k highest hourly prices minus the sum of the k
    lowest, on raw prices with no efficiency adjustment (specs/M2_rolling_
    and_benchmarks.md, "Benchmark definitions"). Day-slicing reuses
    bess.backtest.rolling's local-market-day helpers (spec gotcha 1) instead
    of a fresh groupby, so this function agrees with the rolling engine's DST
    handling by construction: a spring-forward day contributes all 23 hours,
    a fall-back day all 25, never a hardcoded 24.

    Returns a Series indexed by local market date (one row per day present in
    prices_df), named "tbk".

    Raises:
        ValueError: if a market day has fewer than 2*k hourly intervals, so
            the top-k and bottom-k selections would overlap and double-count
            (this cannot happen on a canonical-schema frame produced by
            fetch_da_prices, but a truncated or hand-built frame fails loudly
            here rather than silently returning a wrong number).
    """
    market_day = _local_market_day(prices_df["interval_start_utc"])
    prices = prices_df["price"].to_numpy(dtype=np.float64)
    days, block_starts, block_ends = _day_blocks(market_day)

    values = np.empty(len(days), dtype=np.float64)
    for i in range(len(days)):
        block = np.sort(prices[block_starts[i] : block_ends[i]])
        if block.shape[0] < 2 * k:
            raise ValueError(
                f"Market day {days[i]} has only {block.shape[0]} hourly interval(s), "
                f"fewer than 2*k={2 * k} required for TB{k}"
            )
        values[i] = block[-k:].sum() - block[:k].sum()

    return pd.Series(values, index=pd.Index(days, name="date"), name=f"tb{k}")


def tbk_summary(daily: pd.Series) -> dict[str, object]:
    """Mean daily TBk for the requested window and per calendar year.

    daily is daily_tbk's output (index: local market date, values: $/MW-day).
    Returns {"window_mean": float, "by_year": {"<year>": float, ...}}, the
    two aggregations spec item 1 asks for. Computed with plain numpy indexing
    over the index years rather than a pandas groupby().apply(), which under
    mypy's strict warn_return_any would type as Any.
    """
    years = np.fromiter((d.year for d in daily.index), dtype=np.int64, count=len(daily))
    values = daily.to_numpy(dtype=np.float64)

    by_year: dict[str, object] = {
        str(year): float(values[years == year].mean()) for year in sorted(set(years.tolist()))
    }
    return {"window_mean": float(values.mean()), "by_year": by_year}


def foresight_capture_rate(rolling_revenue_usd: float, perfect_revenue_usd: float) -> float:
    """Rolling total revenue / perfect-foresight total revenue.

    Same battery, same window, same hub for both inputs (specs/M2_rolling_
    and_benchmarks.md, "Benchmark definitions"). This is the M2 headline
    number: how much of the perfect-foresight upper bound a one-day-lookahead
    operator actually captures.
    """
    return rolling_revenue_usd / perfect_revenue_usd


def tb4_capture(total_revenue_usd: float, daily_tb4: pd.Series, power_mw: float) -> float:
    """Actual revenue / (sum of daily TB4 x power_mw), for one mode.

    Reported for both perfect and rolling total_revenue_usd (specs/M2_
    rolling_and_benchmarks.md, "Benchmark definitions"). daily_tb4 must cover
    the same window and hub as total_revenue_usd. A battery whose duration is
    short relative to the daily TB4 spread structurally cannot reach 1.0: the
    default 2-hour battery captures only part of each day's 4-hour spread by
    construction.
    """
    return total_revenue_usd / (float(daily_tb4.sum()) * power_mw)


def as_uplift(coopt_total_revenue_usd: float, energy_only_revenue_usd: float) -> float:
    """AS uplift: co-optimized total revenue / energy-only revenue, the M3 headline.

    Both figures must come from the same battery, window, and hub
    (specs/M3_ancillary_services.md, "Objective"); bess.cli's benchmark
    command enforces this by comparing the two source metrics JSONs'
    daily_revenue date ranges before calling this function. A value outside
    the [1.0, 8.0] sanity corridor documented in specs/M3c_as_backtest_cli.md
    signals a units or alignment bug, not a market finding.
    """
    return coopt_total_revenue_usd / energy_only_revenue_usd


def revenue_mix(revenue_by_product: dict[str, float]) -> dict[str, float]:
    """Each AS product's share of total AS revenue, product name -> fraction of the whole.

    revenue_by_product is the ancillary metrics JSON's revenue_by_product
    block (dollars per product over the window); fractions sum to 1.0. Per-
    product dollar figures themselves can be degenerate under LP ties (memory:
    lp-optimizer-degeneracy-in-tests), so this mix is reported as a fixture
    illustration, not asserted against a per-product golden value.
    """
    total = sum(revenue_by_product.values())
    return {name: value / total for name, value in revenue_by_product.items()}

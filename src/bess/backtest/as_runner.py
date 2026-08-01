"""Backtest runner wiring the M3b energy + AS co-optimizer into M1 metrics.

`run_backtest_as` is the frozen entry point (specs/M3_ancillary_services.md,
"Frozen interfaces"). It aligns the long canonical AS price frame to the (P,
T) matrices `optimize_dispatch_as` expects, runs exactly one co-opt solve,
and scores the energy leg of that solve with the same
`bess.backtest.runner.metrics_from_dispatch` code path M1/M2 use, so an
ancillary-mode BacktestResult stays comparable field by field with a
perfect-foresight one (spec gotcha 1).

Design note (the one real decision this module makes): `AsDispatchResult
.dispatch.objective_value` is the FULL co-optimized dollar figure (energy
plus AS), but `metrics_from_dispatch` treats `dispatch.objective_value` as
total_revenue_usd and separately recomputes `daily_revenue` from
`prices * (discharge - charge) * dt`, which is the ENERGY leg only. Feeding
the raw co-opt DispatchResult straight in would make total_revenue_usd
disagree with daily_revenue.sum() (an M1 invariant) and would break this
module's own energy_revenue_usd + as_revenue_usd == total_revenue_usd
identity. So the DispatchResult handed to metrics_from_dispatch has its
objective_value replaced with AsDispatchResult.energy_revenue_usd first
(dataclasses.replace), making `energy` a genuine energy-only BacktestResult.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pandas as pd

from bess.backtest.runner import _price_series_and_dt, _single_location, metrics_from_dispatch
from bess.data.as_prices import PRODUCT_LAUNCH
from bess.models import (
    DEFAULT_AS_PRODUCTS,
    AsBacktestResult,
    AsDispatchResult,
    AsProduct,
    BatterySpec,
)
from bess.optimizer.as_lp import optimize_dispatch_as

# Matches bess.data.as_prices's own alias for the same zone (ERCOT publishes
# ancillary MCPCs in prevailing Central Time); duplicated rather than
# imported so the launch-date UTC conversion here stays self-contained and
# uses the exact convention PRODUCT_LAUNCH's dates are defined against.
_CENTRAL_TZ = "US/Central"


def _align_as_matrices(
    prices_df: pd.DataFrame,
    as_prices_df: pd.DataFrame,
    products: tuple[AsProduct, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Align the long canonical AS frame to (P, T) price and availability matrices.

    T follows prices_df's own interval order exactly (the energy timeline is
    the backtest's clock). A product-hour absent from as_prices_df becomes
    price 0.0 and availability False; whether that absence is legitimate
    (before the product's PRODUCT_LAUNCH date) or a genuine gap is decided
    per interval: absence at or after the product's effective launch raises,
    listing every offending (product, interval) pair, while absence before
    launch is masked silently, exactly mirroring bess.data.as_prices's own
    per-product launch rule (specs/M3_ancillary_services.md, "Canonical AS
    price schema").
    """
    names = [product.name for product in products]
    pivot = as_prices_df.pivot(index="interval_start_utc", columns="product", values="price")
    pivot = pivot.reindex(index=prices_df["interval_start_utc"], columns=names)

    horizon = len(prices_df)
    as_prices = np.zeros((len(products), horizon), dtype=np.float64)
    as_available = np.zeros((len(products), horizon), dtype=bool)
    missing_pairs: list[tuple[str, pd.Timestamp]] = []

    for i, product in enumerate(products):
        column = pivot[product.name]
        available = column.notna().to_numpy()

        launch = PRODUCT_LAUNCH.get(product.name)
        if launch is None:
            expected = np.ones(horizon, dtype=bool)
        else:
            launch_utc = pd.Timestamp(launch, tz=_CENTRAL_TZ).tz_convert("UTC")
            expected = (prices_df["interval_start_utc"] >= launch_utc).to_numpy()

        gap = expected & ~available
        if gap.any():
            gap_timestamps = prices_df.loc[gap, "interval_start_utc"]
            missing_pairs.extend((product.name, ts) for ts in gap_timestamps)

        as_prices[i] = column.fillna(0.0).to_numpy(dtype=np.float64)
        as_available[i] = available

    if missing_pairs:
        raise ValueError(
            f"Missing {len(missing_pairs)} (product, interval) pair(s) in the AS price "
            f"frame: {[(name, ts.isoformat()) for name, ts in missing_pairs]}"
        )

    return as_prices, as_available


def run_backtest_as(
    prices_df: pd.DataFrame,
    as_prices_df: pd.DataFrame,
    battery: BatterySpec,
    products: tuple[AsProduct, ...] = DEFAULT_AS_PRODUCTS,
    optimizer: Callable[..., AsDispatchResult] = optimize_dispatch_as,
) -> AsBacktestResult:
    """Run a full-horizon perfect-foresight energy + AS co-optimized backtest.

    prices_df must be canonical energy schema for exactly one location;
    as_prices_df must be canonical AS schema over the same window (both
    already validated by their producers, not re-validated here). Aligns the
    AS frame to (P, T) matrices (`_align_as_matrices`), runs one co-opt solve
    via `optimizer`, scores the energy leg with
    `bess.backtest.runner.metrics_from_dispatch` (see module docstring for
    why objective_value is swapped first), and rolls up per-product revenue
    and award MW-hours in `products`' order (gotcha 3: this is what keeps
    pd.Series-keyed JSON serialization deterministic).

    optimizer is injectable, the same seam run_backtest and
    run_backtest_rolling use, so the M4 Rust engine (or a test stub) drops in
    unchanged.
    """
    location = _single_location(prices_df)
    prices, dt_hours = _price_series_and_dt(prices_df)
    as_prices, as_available = _align_as_matrices(prices_df, as_prices_df, products)

    started = time.perf_counter()
    as_dispatch = optimizer(prices, as_prices, as_available, dt_hours, battery, products)
    solve_time_seconds = time.perf_counter() - started

    energy_dispatch = replace(as_dispatch.dispatch, objective_value=as_dispatch.energy_revenue_usd)
    energy = metrics_from_dispatch(
        location, prices_df, battery, energy_dispatch, solve_time_seconds
    )

    names = [product.name for product in products]
    product_index = pd.Index(names, name="product")
    revenue_by_product = pd.Series(
        (as_prices * as_dispatch.awards_mw * dt_hours).sum(axis=1), index=product_index
    )
    award_mw_hours = pd.Series((as_dispatch.awards_mw * dt_hours).sum(axis=1), index=product_index)

    return AsBacktestResult(
        energy=energy,
        total_revenue_usd=energy.total_revenue_usd + as_dispatch.as_revenue_usd,
        as_revenue_usd=as_dispatch.as_revenue_usd,
        revenue_by_product=revenue_by_product,
        award_mw_hours=award_mw_hours,
    )

"""Property and behavior tests for optimize_dispatch_as (acceptance criteria 6-10).

Properties run on the real July 2023 HB_NORTH energy fixture (committed by
M1a) paired with the July 2023 AS MCPC fixture (committed by M3a), default
battery, DEFAULT_AS_PRODUCTS. Per specs/M3b_as_cooptimizer.md, this module
does not depend on M3a code: the (P, T) AS matrices are read straight from
the parquet fixture with pandas and pivoted inline, never through
bess.data.as_prices.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bess.models import DEFAULT_AS_PRODUCTS, AsProduct, BatterySpec
from bess.optimizer.as_lp import optimize_dispatch_as
from bess.optimizer.lp import optimize_dispatch

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_ENERGY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
JULY_AS_FIXTURE = FIXTURES_DIR / "as_mcpc_2023_07.parquet"

_RESIDUAL_TOL = 1e-6


def _default_battery() -> BatterySpec:
    """The config.toml default battery (specs/M1_python_core.md "Default config")."""
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def _load_july_energy_prices() -> np.ndarray:
    df = pd.read_parquet(JULY_ENERGY_FIXTURE).sort_values("interval_start_utc")
    return df["price"].to_numpy(dtype=np.float64)


def _load_july_as_prices(products: tuple[AsProduct, ...]) -> np.ndarray:
    """Pivot the long AS fixture to a (P, T) matrix, rows ordered by `products`."""
    df = pd.read_parquet(JULY_AS_FIXTURE)
    pivot = df.pivot(index="interval_start_utc", columns="product", values="price").sort_index()
    return np.stack([pivot[product.name].to_numpy(dtype=np.float64) for product in products])


def _synthetic_prices(seed: int, horizon: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-20.0, 150.0, size=horizon)


def _constraint_slacks(
    result_awards_mw: np.ndarray,
    soc_mwh: np.ndarray,
    net_dispatch: np.ndarray,
    battery: BatterySpec,
    products: tuple[AsProduct, ...],
) -> dict[str, np.ndarray]:
    """Slack (RHS - LHS) for each of the four AS constraint families, every t.

    Non-negative (within tolerance) everywhere the LP is respected.
    """
    up_idx = [i for i, product in enumerate(products) if product.direction == "up"]
    down_idx = [i for i, product in enumerate(products) if product.direction == "down"]
    sustain = np.array([product.sustain_hours for product in products])

    up_award_total = result_awards_mw[up_idx].sum(axis=0)
    down_award_total = result_awards_mw[down_idx].sum(axis=0)
    up_adequacy_lhs = (sustain[up_idx, None] * result_awards_mw[up_idx]).sum(axis=0)
    down_room_lhs = (battery.charge_eff * sustain[down_idx, None] * result_awards_mw[down_idx]).sum(
        axis=0
    )

    return {
        "up_coupling": battery.power_mw - (net_dispatch + up_award_total),
        "down_coupling": battery.power_mw - (-net_dispatch + down_award_total),
        "up_adequacy": soc_mwh * battery.discharge_eff - up_adequacy_lhs,
        "down_room": (battery.energy_mwh - soc_mwh) - down_room_lhs,
    }


def test_solver_reaches_optimal_on_july_fixture() -> None:
    """AC-6: solver_status == 'optimal' on the real July fixture co-optimized."""
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert result.dispatch.solver_status == "optimal"


def test_soc_stays_within_battery_bounds_on_fixture() -> None:
    """AC-6: every M1 SoC-bounds property still holds on the co-optimized dispatch."""
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    soc = result.dispatch.soc_mwh
    assert np.all(soc >= -_RESIDUAL_TOL)
    assert np.all(soc <= battery.energy_mwh + _RESIDUAL_TOL)


def test_soc_dynamics_residual_is_negligible_on_fixture() -> None:
    """AC-6: SoC recomputed from charge/discharge arrays matches soc_mwh, < 1e-6."""
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()
    dt_hours = 1.0

    result = optimize_dispatch_as(prices, as_prices, as_available, dt_hours, battery, products)

    deltas = (
        battery.charge_eff * result.dispatch.charge_mw * dt_hours
        - (result.dispatch.discharge_mw * dt_hours) / battery.discharge_eff
    )
    recomputed_soc = battery.initial_soc_mwh + np.cumsum(deltas)

    assert np.max(np.abs(recomputed_soc - result.dispatch.soc_mwh)) < _RESIDUAL_TOL


def test_charge_and_discharge_respect_power_limit_on_fixture() -> None:
    """AC-6: charge_mw <= power_mw and discharge_mw <= power_mw everywhere.

    Awards are explicitly allowed to exceed power_mw (pinned convention 2);
    only the underlying charge/discharge columns are bounded by it.
    """
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert np.all(result.dispatch.charge_mw <= battery.power_mw + _RESIDUAL_TOL)
    assert np.all(result.dispatch.discharge_mw <= battery.power_mw + _RESIDUAL_TOL)


def test_constraint_residuals_within_tolerance_on_fixture() -> None:
    """AC-7: up/down coupling and adequacy residuals within 1e-6; awards >= 0."""
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)
    net_dispatch = result.dispatch.discharge_mw - result.dispatch.charge_mw

    slacks = _constraint_slacks(
        result.awards_mw, result.dispatch.soc_mwh, net_dispatch, battery, products
    )
    for name, slack in slacks.items():
        assert np.all(slack >= -_RESIDUAL_TOL), f"{name} constraint violated beyond tolerance"

    assert np.all(result.awards_mw >= -_RESIDUAL_TOL)


def test_masked_awards_are_exactly_zero_on_fixture() -> None:
    """AC-7: masked awards exactly 0, even amid an otherwise fully available fixture.

    Half of the July fixture is masked unavailable for REG_UP; the awards
    for those masked (product, interval) pairs must be exactly 0.0, not just
    revenue-equivalent, since the zero upper bound pins the variable.
    """
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    reg_up_index = next(i for i, product in enumerate(products) if product.name == "REG_UP")
    horizon = prices.shape[0]
    as_available[reg_up_index, : horizon // 2] = False
    battery = _default_battery()

    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)

    assert np.all(result.awards_mw[reg_up_index, : horizon // 2] == 0.0)


def test_revenue_decomposition_matches_objective_on_fixture() -> None:
    """AC-8: energy_revenue_usd + as_revenue_usd == objective_value within 1e-4.

    Each component also independently recomputes from the raw (prices,
    as_prices, dispatch, awards) arrays within 1e-4.
    """
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()
    dt_hours = 1.0

    result = optimize_dispatch_as(prices, as_prices, as_available, dt_hours, battery, products)

    assert result.energy_revenue_usd + result.as_revenue_usd == pytest.approx(
        result.dispatch.objective_value, abs=1e-4
    )

    recomputed_energy_revenue = float(
        np.sum(prices * (result.dispatch.discharge_mw - result.dispatch.charge_mw) * dt_hours)
    )
    recomputed_as_revenue = float(np.sum(as_prices * result.awards_mw * dt_hours))
    assert recomputed_energy_revenue == pytest.approx(result.energy_revenue_usd, abs=1e-4)
    assert recomputed_as_revenue == pytest.approx(result.as_revenue_usd, abs=1e-4)


def test_co_optimized_objective_dominates_energy_only_on_fixture() -> None:
    """AC-9: co-opt objective >= energy-only objective on the same prices, minus 1e-6.

    Awards are optional (a_pt >= 0 with no minimum), so adding the AS market
    to the same energy prices can never make the optimum worse.
    """
    products = DEFAULT_AS_PRODUCTS
    prices = _load_july_energy_prices()
    as_prices = _load_july_as_prices(products)
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    co_opt = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)
    energy_only = optimize_dispatch(prices, 1.0, battery)

    assert co_opt.dispatch.objective_value >= energy_only.objective_value - 1e-6


def test_product_order_shuffle_preserves_aggregate_totals() -> None:
    """Gotcha 4: shuffling the products tuple must not change the objective or total AS revenue.

    Per-product revenue attribution is degenerate under a shuffle (ties
    between products at identical marginal adequacy/coupling value can
    reassign which product 'wins' a dollar), so only the aggregate objective
    and total as_revenue_usd are asserted equal, never a per-product split
    (memory: lp-optimizer-degeneracy-in-tests). `result.products` must echo
    back the caller's order exactly, confirming rows are never re-sorted.
    """
    prices = _load_july_energy_prices()
    battery = _default_battery()

    original_products = DEFAULT_AS_PRODUCTS
    original_as_prices = _load_july_as_prices(original_products)
    original_as_available = np.ones_like(original_as_prices, dtype=bool)
    original = optimize_dispatch_as(
        prices, original_as_prices, original_as_available, 1.0, battery, original_products
    )

    permutation = [3, 0, 4, 1, 2]
    shuffled_products = tuple(original_products[i] for i in permutation)
    shuffled_as_prices = original_as_prices[permutation]
    shuffled_as_available = original_as_available[permutation]
    shuffled = optimize_dispatch_as(
        prices, shuffled_as_prices, shuffled_as_available, 1.0, battery, shuffled_products
    )

    assert shuffled.dispatch.objective_value == pytest.approx(
        original.dispatch.objective_value, abs=1e-4
    )
    assert shuffled.as_revenue_usd == pytest.approx(original.as_revenue_usd, abs=1e-4)
    assert shuffled.products == shuffled_products


def test_full_two_year_five_product_horizon_solves_within_runtime_budget() -> None:
    """AC-10: T=17,520 (2 hourly years), P=5 (~122k variables) solves in under 60 seconds."""
    horizon = 17_520
    products = DEFAULT_AS_PRODUCTS
    prices = _synthetic_prices(seed=2024, horizon=horizon)
    as_prices = np.stack(
        [_synthetic_prices(seed=100 + i, horizon=horizon) for i in range(len(products))]
    )
    as_available = np.ones_like(as_prices, dtype=bool)
    battery = _default_battery()

    start = time.perf_counter()
    result = optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)
    elapsed = time.perf_counter() - start

    print(f"optimize_dispatch_as T={horizon} P={len(products)} wall time: {elapsed:.3f}s")
    assert result.dispatch.solver_status == "optimal"
    assert elapsed < 60.0


def test_unavailable_product_direction_raises() -> None:
    """AC-3 (validation): an unknown direction string raises ValueError."""
    prices = np.zeros(4)
    battery = _default_battery()
    products = (AsProduct(name="MYSTERY", direction="sideways", sustain_hours=1.0),)
    as_prices = np.zeros((1, 4))
    as_available = np.ones((1, 4), dtype=bool)

    with pytest.raises(ValueError, match="direction"):
        optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)


def test_as_prices_shape_mismatch_raises() -> None:
    """AC-3 (validation): as_prices shape disagreeing with (len(products), T) raises."""
    prices = np.zeros(4)
    battery = _default_battery()
    products = (AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),)
    as_prices = np.zeros((2, 4))  # wrong product count
    as_available = np.ones((1, 4), dtype=bool)

    with pytest.raises(ValueError, match="as_prices"):
        optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)


def test_as_available_shape_mismatch_raises() -> None:
    """AC-3 (validation): as_available shape disagreeing with (len(products), T) raises."""
    prices = np.zeros(4)
    battery = _default_battery()
    products = (AsProduct(name="REG_UP", direction="up", sustain_hours=1.0),)
    as_prices = np.zeros((1, 4))
    as_available = np.ones((1, 3), dtype=bool)  # wrong horizon

    with pytest.raises(ValueError, match="as_available"):
        optimize_dispatch_as(prices, as_prices, as_available, 1.0, battery, products)


def _top_level_import_modules(path: Path) -> set[str]:
    """Root module names from every top-level import statement in `path`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_as_lp_module_imports_are_restricted_to_the_purity_allowlist() -> None:
    """Hard purity rule, mirroring M1b: as_lp.py imports only numpy, highspy, bess.models.

    logging is allowed too (a module-level logger is explicitly fine, same
    as optimizer/lp.py); anything else, in particular pandas, would violate
    the "no I/O, no DataFrames, no timezone logic" contract that keeps this
    module a pure, arrays-in-arrays-out function (memory:
    ast-based-import-confinement-guard).
    """
    as_lp_module = Path(__file__).parent.parent / "src" / "bess" / "optimizer" / "as_lp.py"
    allowed = {"numpy", "highspy", "bess.models", "logging", "__future__"}

    imports = _top_level_import_modules(as_lp_module)

    assert imports <= allowed
    assert {"numpy", "highspy", "bess.models"} <= imports

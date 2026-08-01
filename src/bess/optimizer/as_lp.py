"""Full-horizon, perfect-foresight energy + ancillary-service co-optimization LP.

Companion to optimizer/lp.py, not a replacement: optimize_dispatch remains the
frozen M4 Rust engine target, untouched here. This module adds a second pure
function, optimize_dispatch_as, that co-optimizes energy dispatch with
per-product AS capacity awards in a single HiGHS solve
(specs/M3_ancillary_services.md, "LP formulation").

Hard purity rule, mirroring M1b: this module imports only numpy, highspy, and
bess.models (plus stdlib logging for the module-level logger).
tests/test_as_optimizer_properties.py asserts this import list.
"""

from __future__ import annotations

import logging

import highspy
import numpy as np

from bess.models import AsDispatchResult, AsProduct, BatterySpec, DispatchResult

logger = logging.getLogger(__name__)

# Threshold (MW) above which charge and discharge are both considered "on" in
# the same interval, matching optimizer/lp.py's simultaneous_hours definition.
# Duplicated rather than imported so this module's purity allowlist never has
# to include optimizer/lp.py (memory: highspy-untyped-mypy).
_SIMULTANEOUS_THRESHOLD_MW = 1e-3

_VALID_DIRECTIONS = frozenset({"up", "down"})


def optimize_dispatch_as(
    prices: np.ndarray,
    as_prices: np.ndarray,
    as_available: np.ndarray,
    dt_hours: float,
    battery: BatterySpec,
    products: tuple[AsProduct, ...],
) -> AsDispatchResult:
    """Solve the revenue-maximizing energy + AS capacity award schedule for one horizon.

    LP formulation (specs/M3_ancillary_services.md, "LP formulation",
    implemented exactly): all M1 decision variables, dynamics, and bounds
    (charge c_t, discharge d_t, SoC s_t) are unchanged from optimize_dispatch.
    Add award variables a_pt >= 0 for each product p (row of `products`,
    matching the row order of `as_prices` and `as_available`) and interval t.
    Let UP be the products with direction "up" and DOWN be the products with
    direction "down"; q_pt is as_prices[p, t]. Maximize

        sum_t [ p_t * (d_t - c_t) * dt + sum_p q_pt * a_pt * dt ]

    subject to, for every t, all M1 constraints plus:

        up coupling:    (d_t - c_t) + sum_{p in UP} a_pt   <= power_mw
        down coupling:  (c_t - d_t) + sum_{p in DOWN} a_pt <= power_mw
        up adequacy:    sum_{p in UP} sustain_p * a_pt        <= s_t * discharge_eff
        down room:      sum_{p in DOWN} charge_eff * sustain_p * a_pt <= energy_mwh - s_t

    and a_pt = 0 wherever as_available[p, t] is False, implemented as a zero
    upper bound on that column rather than a constraint row.

    Three pinned conventions (deliberate, not open design questions):

    1. Adequacy uses END-OF-INTERVAL SoC s_t, consistent with the frozen
       DispatchResult convention (start-of-interval would be equally
       defensible; this choice is what the module's golden tests are derived
       from).
    2. Awards MAY EXCEED power_mw while the battery is charging: curtailing a
       charge is real up capability, and the up coupling constraint captures
       the full swing ((d_t - c_t) can be as negative as -power_mw, leaving
       room for an award up to 2 * power_mw). This is correct LP behavior;
       do not cap a_pt at power_mw.
    3. CAPACITY PAYMENTS ONLY: awards never move SoC. Deployment energy,
       performance, and mileage payments are out of scope (README M3
       section states this).

    battery.max_cycles_per_day is accepted but ignored, exactly as in
    optimize_dispatch: cycle-cap enforcement is out of scope.

    Degenerate awards: at zero MCPC (or whenever multiple products tie on
    marginal adequacy/coupling value), the LP may return any of several
    award splits that share the same total revenue. Callers and tests should
    rely on energy_revenue_usd, as_revenue_usd, and dispatch.objective_value,
    never on a specific per-(product, interval) award value, except where the
    optimum is provably strict (memory: lp-optimizer-degeneracy-in-tests).

    Args:
        prices: shape (T,), $/MWh, may contain negatives.
        as_prices: shape (P, T), MCPC $/MW-h, rows ordered as `products`.
        as_available: shape (P, T), bool; False forces that award to 0.
        dt_hours: length of one interval in hours.
        battery: physical/operational battery parameters.
        products: AS products, row order shared with as_prices/as_available.

    Returns:
        AsDispatchResult with dispatch.objective_value set to the FULL
        co-optimized dollar figure (energy plus AS), products echoed back in
        the caller's order, and awards_mw of shape (P, T).

    Raises:
        ValueError: if as_prices or as_available disagree in shape with
            (len(products), len(prices)), or any product's direction is not
            "up" or "down".
        RuntimeError: if HiGHS does not reach an optimal solution; the status
            is included in the message.
    """
    _validate_as_inputs(prices, as_prices, as_available, products)

    lp = _build_as_lp(prices, as_prices, as_available, dt_hours, battery, products)

    solver = highspy.Highs()
    solver.silent()
    solver.passModel(lp)
    solver.run()

    status = solver.getModelStatus()
    if status != highspy.HighsModelStatus.kOptimal:
        raise RuntimeError(
            f"HiGHS did not reach an optimal solution: status={solver.modelStatusToString(status)}"
        )

    horizon = prices.shape[0]
    num_products = len(products)
    solution = np.asarray(solver.getSolution().col_value, dtype=np.float64)
    charge_mw = solution[:horizon]
    discharge_mw = solution[horizon : 2 * horizon]
    soc_mwh = solution[2 * horizon : 3 * horizon]
    awards_mw = solution[3 * horizon :].reshape(num_products, horizon)

    simultaneous_mask = (charge_mw > _SIMULTANEOUS_THRESHOLD_MW) & (
        discharge_mw > _SIMULTANEOUS_THRESHOLD_MW
    )
    simultaneous_hours = int(np.count_nonzero(simultaneous_mask))
    if simultaneous_hours:
        logger.warning(
            "optimize_dispatch_as: %d interval(s) charge and discharge simultaneously. "
            "This is expected LP behavior at deeply negative prices (burning energy "
            "through efficiency losses is profitable); the MILP exclusivity fix is "
            "deferred.",
            simultaneous_hours,
        )

    energy_revenue_usd = float(np.sum(prices * (discharge_mw - charge_mw) * dt_hours))
    as_revenue_usd = float(np.sum(as_prices * awards_mw * dt_hours))

    dispatch = DispatchResult(
        charge_mw=charge_mw,
        discharge_mw=discharge_mw,
        soc_mwh=soc_mwh,
        objective_value=float(solver.getObjectiveValue()),
        solver_status="optimal",
        simultaneous_hours=simultaneous_hours,
    )

    return AsDispatchResult(
        dispatch=dispatch,
        products=products,
        awards_mw=awards_mw,
        energy_revenue_usd=energy_revenue_usd,
        as_revenue_usd=as_revenue_usd,
    )


def _validate_as_inputs(
    prices: np.ndarray,
    as_prices: np.ndarray,
    as_available: np.ndarray,
    products: tuple[AsProduct, ...],
) -> None:
    """Shape agreement between as_prices/as_available and products; direction check.

    Per acceptance criterion 3: unknown direction strings raise, and
    as_prices/as_available must both be shaped (len(products), len(prices)).
    """
    horizon = prices.shape[0]
    expected_shape = (len(products), horizon)
    if as_prices.shape != expected_shape:
        raise ValueError(
            f"as_prices shape {as_prices.shape} does not match (len(products), len(prices)) "
            f"= {expected_shape}"
        )
    if as_available.shape != expected_shape:
        raise ValueError(
            f"as_available shape {as_available.shape} does not match (len(products), len(prices)) "
            f"= {expected_shape}"
        )
    for product in products:
        if product.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"Unknown AS product direction {product.direction!r} for product "
                f"{product.name!r}; must be one of {sorted(_VALID_DIRECTIONS)}"
            )


def _build_as_lp(
    prices: np.ndarray,
    as_prices: np.ndarray,
    as_available: np.ndarray,
    dt_hours: float,
    battery: BatterySpec,
    products: tuple[AsProduct, ...],
) -> highspy.HighsLp:
    """Build the column-wise sparse HighsLp for one optimize_dispatch_as() solve.

    Columns: [c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}, a_0_0..a_0_{T-1},
    a_1_0..a_1_{T-1}, ..., a_{P-1}_0..a_{P-1}_{T-1}] (award columns grouped by
    product, row-ordered by `products`). Rows: [dynamics(T), up coupling(T),
    down coupling(T), up adequacy(T), down room adequacy(T)]. The dynamics
    block is byte-for-byte the same recursion as optimizer/lp.py's
    _build_lp; award columns carry a zero coefficient there, so they never
    move SoC (pinned convention 3). Building the CSC arrays directly with
    numpy, rather than the high-level Highs() API, is what keeps a
    T=17,520 / P=5 solve well inside the 60-second runtime budget (AC 10).
    """
    horizon = prices.shape[0]
    num_products = len(products)
    t = np.arange(horizon)

    up_mask = np.array([product.direction == "up" for product in products], dtype=bool)
    sustain_hours = np.array([product.sustain_hours for product in products], dtype=np.float64)

    num_col = (3 + num_products) * horizon
    num_row = 5 * horizon

    col_nnz = np.full(num_col, 2, dtype=np.int64)  # default: award columns
    col_nnz[:horizon] = 3  # charge: dynamics, up coupling, down coupling
    col_nnz[horizon : 2 * horizon] = 3  # discharge: same three rows
    col_nnz[2 * horizon : 3 * horizon] = 4  # soc: dynamics x2, up adequacy, down room
    col_nnz[3 * horizon - 1] = 3  # last soc column has no following-interval row

    start = np.zeros(num_col + 1, dtype=np.int64)
    start[1:] = np.cumsum(col_nnz)
    index = np.zeros(int(start[-1]), dtype=np.int32)
    value = np.zeros(int(start[-1]), dtype=np.float64)

    # Charge columns: dynamics row, up coupling row, down coupling row.
    charge_slot = start[:horizon]
    index[charge_slot] = t
    value[charge_slot] = -battery.charge_eff * dt_hours
    index[charge_slot + 1] = horizon + t
    value[charge_slot + 1] = -1.0
    index[charge_slot + 2] = 2 * horizon + t
    value[charge_slot + 2] = 1.0

    # Discharge columns: dynamics row, up coupling row, down coupling row.
    discharge_slot = start[horizon : 2 * horizon]
    index[discharge_slot] = t
    value[discharge_slot] = dt_hours / battery.discharge_eff
    index[discharge_slot + 1] = horizon + t
    value[discharge_slot + 1] = 1.0
    index[discharge_slot + 2] = 2 * horizon + t
    value[discharge_slot + 2] = -1.0

    # SoC columns: own dynamics row, next-interval dynamics row (if any), up
    # adequacy row, down room adequacy row.
    soc_slot = start[2 * horizon : 3 * horizon]
    index[soc_slot] = t
    value[soc_slot] = 1.0
    has_next = t < horizon - 1
    next_dynamics_slot = soc_slot[has_next] + 1
    index[next_dynamics_slot] = t[has_next] + 1
    value[next_dynamics_slot] = -1.0
    adequacy_slot = np.where(has_next, soc_slot + 2, soc_slot + 1)
    index[adequacy_slot] = 3 * horizon + t
    value[adequacy_slot] = -battery.discharge_eff
    room_slot = adequacy_slot + 1
    index[room_slot] = 4 * horizon + t
    value[room_slot] = 1.0

    # Award columns, one block of `horizon` columns per product: up products
    # hit the up coupling and up adequacy rows, down products hit the down
    # coupling and down room adequacy rows.
    award_start = start[3 * horizon : num_col]
    for p in range(num_products):
        block = award_start[p * horizon : (p + 1) * horizon]
        if up_mask[p]:
            index[block] = horizon + t
            value[block] = 1.0
            index[block + 1] = 3 * horizon + t
            value[block + 1] = sustain_hours[p]
        else:
            index[block] = 2 * horizon + t
            value[block] = 1.0
            index[block + 1] = 4 * horizon + t
            value[block + 1] = battery.charge_eff * sustain_hours[p]

    row_lower = np.full(num_row, -highspy.kHighsInf)
    row_upper = np.zeros(num_row)
    row_lower[:horizon] = 0.0  # dynamics: equality, tightened to initial SoC below
    row_upper[:horizon] = 0.0
    row_lower[0] = battery.initial_soc_mwh
    row_upper[0] = battery.initial_soc_mwh
    row_upper[horizon : 2 * horizon] = battery.power_mw  # up coupling
    row_upper[2 * horizon : 3 * horizon] = battery.power_mw  # down coupling
    row_upper[3 * horizon : 4 * horizon] = 0.0  # up adequacy
    row_upper[4 * horizon : 5 * horizon] = battery.energy_mwh  # down room adequacy

    col_lower = np.zeros(num_col)
    col_upper = np.concatenate(
        [
            np.full(horizon, battery.power_mw),
            np.full(horizon, battery.power_mw),
            np.full(horizon, battery.energy_mwh),
            np.where(as_available.reshape(-1), highspy.kHighsInf, 0.0),
        ]
    )
    col_cost = np.concatenate(
        [
            -prices * dt_hours,
            prices * dt_hours,
            np.zeros(horizon),
            (as_prices * dt_hours).reshape(-1),
        ]
    )

    lp = highspy.HighsLp()
    lp.num_col_ = num_col
    lp.num_row_ = num_row
    lp.col_cost_ = col_cost
    lp.col_lower_ = col_lower
    lp.col_upper_ = col_upper
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    lp.sense_ = highspy.ObjSense.kMaximize

    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.num_col_ = num_col
    lp.a_matrix_.num_row_ = num_row
    lp.a_matrix_.start_ = start
    lp.a_matrix_.index_ = index
    lp.a_matrix_.value_ = value

    return lp

"""Full-horizon, perfect-foresight LP dispatch via HiGHS (highspy).

This is the correctness oracle for the M4 Rust engine. The interface is frozen:
arrays in, DispatchResult out. No I/O, no DataFrames, no timezone logic in this
module; all data messiness is handled in bess.data.prices.

Hard purity rule (specs/M1b_optimizer.md): this module imports only numpy,
highspy, and bess.models (plus stdlib logging for the module-level logger).
tests/test_optimizer_properties.py asserts this import list.
"""

from __future__ import annotations

import logging

import highspy
import numpy as np

from bess.models import BatterySpec, DispatchResult

logger = logging.getLogger(__name__)

# Threshold (MW) above which charge and discharge are both considered "on" in
# the same interval, per the spec's simultaneous_hours definition.
_SIMULTANEOUS_THRESHOLD_MW = 1e-3


def optimize_dispatch(
    prices: np.ndarray,
    dt_hours: float,
    battery: BatterySpec,
) -> DispatchResult:
    """Solve the revenue-maximizing charge/discharge schedule for one horizon.

    LP formulation (specs/M1_python_core.md, "LP formulation", implemented
    exactly): decision variables per interval t are charge c_t (MW), discharge
    d_t (MW), and state of charge s_t (MWh, end of interval t). Maximize
    sum_t p_t * (d_t - c_t) * dt_hours subject to the SoC recursion
    s_t = s_{t-1} + charge_eff * c_t * dt_hours - (d_t * dt_hours) / discharge_eff
    (with s_{-1} = battery.initial_soc_mwh), 0 <= c_t, d_t <= power_mw, and
    0 <= s_t <= energy_mwh.

    There is deliberately no terminal SoC constraint: with the default initial
    SoC of 0, an unconstrained final SoC lets the optimizer capture the full
    value of any energy still stored at the end of the horizon rather than
    stranding it, and a rolling-horizon caller (M2) is expected to re-solve
    with a fresh initial_soc_mwh rather than rely on a terminal target here.

    battery.max_cycles_per_day is accepted but ignored: cycle-cap enforcement
    is out of scope for M1 (see specs/M1b_optimizer.md, "Out of scope") and is
    deferred to a later milestone.

    Prices may be negative; that is valid data, never clipped or filtered. At
    deeply negative prices, charging and discharging in the same interval to
    burn energy through round-trip efficiency losses is genuinely profitable
    and is correct LP behavior, not a bug: it is counted in
    simultaneous_hours (threshold 1e-3 MW) and logged as a WARNING, never
    raised. The MILP fix that would force charge/discharge mutual exclusivity
    is explicitly deferred.

    Raises:
        RuntimeError: if HiGHS does not reach an optimal solution; the status
            is included in the message.
    """
    lp = _build_lp(prices, dt_hours, battery)

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
    solution = np.asarray(solver.getSolution().col_value, dtype=np.float64)
    charge_mw = solution[:horizon]
    discharge_mw = solution[horizon : 2 * horizon]
    soc_mwh = solution[2 * horizon : 3 * horizon]

    simultaneous_mask = (charge_mw > _SIMULTANEOUS_THRESHOLD_MW) & (
        discharge_mw > _SIMULTANEOUS_THRESHOLD_MW
    )
    simultaneous_hours = int(np.count_nonzero(simultaneous_mask))
    if simultaneous_hours:
        logger.warning(
            "optimize_dispatch: %d interval(s) charge and discharge simultaneously. "
            "This is expected LP behavior at deeply negative prices (burning energy "
            "through efficiency losses is profitable); the MILP exclusivity fix is "
            "deferred.",
            simultaneous_hours,
        )

    return DispatchResult(
        charge_mw=charge_mw,
        discharge_mw=discharge_mw,
        soc_mwh=soc_mwh,
        objective_value=solver.getObjectiveValue(),
        solver_status="optimal",
        simultaneous_hours=simultaneous_hours,
    )


def _build_lp(prices: np.ndarray, dt_hours: float, battery: BatterySpec) -> highspy.HighsLp:
    """Build the column-wise sparse HighsLp for one optimize_dispatch() solve.

    Columns are laid out as [c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]. Each
    charge or discharge column has exactly one nonzero (its own SoC row); each
    SoC column has one or two nonzeros (its own row, and the next interval's
    row where it appears as the "previous SoC" term). Building the CSC arrays
    directly with numpy, rather than adding one row/column at a time through
    the high-level Highs() API, is what keeps a T=17,520 solve well inside the
    30-second runtime budget (see acceptance criterion 11).
    """
    horizon = prices.shape[0]
    num_col = 3 * horizon
    t = np.arange(horizon)

    col_nnz = np.ones(num_col, dtype=np.int64)
    col_nnz[2 * horizon : 3 * horizon] = 2
    col_nnz[num_col - 1] = 1  # last SoC column has no following-interval row

    start = np.zeros(num_col + 1, dtype=np.int64)
    start[1:] = np.cumsum(col_nnz)
    index = np.zeros(int(start[-1]), dtype=np.int32)
    value = np.zeros(int(start[-1]), dtype=np.float64)

    charge_slot = start[:horizon]
    index[charge_slot] = t
    value[charge_slot] = -battery.charge_eff * dt_hours

    discharge_slot = start[horizon : 2 * horizon]
    index[discharge_slot] = t
    value[discharge_slot] = dt_hours / battery.discharge_eff

    soc_slot = start[2 * horizon : 3 * horizon]
    index[soc_slot] = t
    value[soc_slot] = 1.0
    has_next = t < horizon - 1
    next_slot = soc_slot[has_next] + 1
    index[next_slot] = t[has_next] + 1
    value[next_slot] = -1.0

    row_lower = np.zeros(horizon)
    row_upper = np.zeros(horizon)
    row_lower[0] = battery.initial_soc_mwh
    row_upper[0] = battery.initial_soc_mwh

    col_lower = np.zeros(num_col)
    col_upper = np.concatenate(
        [
            np.full(horizon, battery.power_mw),
            np.full(horizon, battery.power_mw),
            np.full(horizon, battery.energy_mwh),
        ]
    )
    col_cost = np.concatenate([-prices * dt_hours, prices * dt_hours, np.zeros(horizon)])

    lp = highspy.HighsLp()
    lp.num_col_ = num_col
    lp.num_row_ = horizon
    lp.col_cost_ = col_cost
    lp.col_lower_ = col_lower
    lp.col_upper_ = col_upper
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    lp.sense_ = highspy.ObjSense.kMaximize

    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.num_col_ = num_col
    lp.a_matrix_.num_row_ = horizon
    lp.a_matrix_.start_ = start
    lp.a_matrix_.index_ = index
    lp.a_matrix_.value_ = value

    return lp

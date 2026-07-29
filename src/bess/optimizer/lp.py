"""Full-horizon, perfect-foresight LP dispatch via HiGHS (highspy).

This is the correctness oracle for the M4 Rust engine. The interface is frozen:
arrays in, DispatchResult out. No I/O, no DataFrames, no timezone logic in this
module; all data messiness is handled in bess.data.prices.
"""

from __future__ import annotations

import numpy as np

from bess.models import BatterySpec, DispatchResult


def optimize_dispatch(
    prices: np.ndarray,
    dt_hours: float,
    battery: BatterySpec,
) -> DispatchResult:
    """Solve the revenue-maximizing charge/discharge schedule for one horizon.

    Intended behavior (spec section "LP formulation", implement exactly):
    - Decision variables per interval t: charge c_t (MW), discharge d_t (MW),
      state of charge s_t (MWh at end of t).
    - Maximize sum_t p_t * (d_t - c_t) * dt.
    - SoC dynamics: s_t = s_{t-1} + eta_c * c_t * dt - (d_t * dt) / eta_d, with
      s_{-1} = battery.initial_soc_mwh.
    - Bounds: 0 <= c_t <= power_mw, 0 <= d_t <= power_mw, 0 <= s_t <= energy_mwh.
    - No terminal SoC constraint: with the default initial SoC of 0 the optimizer
      will not strand valuable energy.
    - Prices may be negative; that is valid data. Simultaneous charge/discharge
      at negative prices is expected LP behavior: count it in
      simultaneous_hours (threshold 1e-3 MW), log a WARNING, never raise.
    - Assert HiGHS model status is optimal; any other status raises.

    Covered by acceptance criteria: 1-4 (golden cases), 5 (properties on real
    fixture data), 6 (simultaneous charge/discharge reported not raised),
    7 (T=17,520 solves in under 30 s).
    """
    raise NotImplementedError

# ADW Feature Spec: M1b, LP Dispatch Optimizer

- **Repo:** bess-optimizer
- **Master spec:** specs/M1_python_core.md (frozen interfaces and LP formulation live there; on any conflict the master wins)
- **Depends on:** scaffold only (models.py). Independent of M1a; all tests use
  synthetic price arrays, no market data.
- **Implements:** src/bess/optimizer/lp.py, tests/test_optimizer_golden.py,
  tests/test_optimizer_properties.py

## Objective

Implement `optimize_dispatch` with highspy, solving the exact LP formulation in
the master spec: perfect-foresight battery arbitrage maximizing
sum of p_t * (d_t - c_t) * dt subject to SoC dynamics with split
charge/discharge efficiency, power limits, and SoC bounds. This function is the
correctness oracle for a later Rust engine, so exactness and purity matter more
than speed.

## In scope

1. `optimize_dispatch(prices, dt_hours, battery) -> DispatchResult` exactly as
   signed in the master spec. Populate every DispatchResult field, including
   simultaneous_hours (count of intervals where charge and discharge both
   exceed 1e-3 MW).
2. The LP formulation from the master spec, implemented exactly. No terminal
   SoC constraint. Solver is HiGHS via highspy.
3. Any solver status other than optimal raises with the status in the message.
4. Both golden and property test files.

## Out of scope

Rolling horizon, cycle caps (BatterySpec carries the field; the LP ignores it
in M1 and the docstring says so), MILP charge/discharge exclusivity, any I/O,
any pandas usage inside the module, performance tuning beyond the runtime
budget below.

## Hard purity rule

optimizer/lp.py imports numpy, highspy, and bess.models only. No pandas, no
file access, no timezone logic, no logging configuration (module-level logger
is fine). A test asserts the module's import list.

## Acceptance criteria

Golden cases, all asserted within 1e-6:

1. Flat prices: T=24 at $50, eff 0.9/0.9. Objective == 0.0. Assert zero
   revenue, not zero dispatch.
2. Step, lossless: T=24, hours 0-11 at $10, hours 12-23 at $100, battery
   1 MW / 2 MWh, eff 1.0/1.0, initial SoC 0. Objective == 180.0.
3. Step, lossy charge: same prices, eff 0.8 charge / 1.0 discharge.
   Grid draw 2.5 MWh costs $25, discharge 2 MWh earns $200. Objective == 175.0.
4. Negative hour: T=24, one hour at -$50, others at $0, battery 1 MW / 2 MWh,
   eff 0.9/0.9. Objective == 50.0.

Property tests, on 3 seeded random price series (T=168, uniform on
[-20, 150], fixed seeds) with the default 100 MW / 200 MWh config:

5. solver_status == "optimal" for all.
6. 0 <= soc_mwh <= energy_mwh everywhere, tolerance 1e-6.
7. SoC dynamics residual < 1e-6 at every t when recomputed from charge and
   discharge arrays.
8. Revenue recomputed independently from (prices, charge_mw, discharge_mw)
   equals objective_value within 1e-4.
9. charge_mw <= power_mw and discharge_mw <= power_mw everywhere.

Behavior and budget:

10. Simultaneous charge/discharge: construct a case with a deeply negative
    price and initial SoC at capacity. Assert simultaneous_hours > 0, a
    WARNING is logged, and no exception is raised. This is correct LP behavior
    (burning energy through efficiency losses is profitable at negative
    prices) and the MILP fix is explicitly deferred.
11. Runtime: T=17,520 synthetic series solves in under 30 seconds; wall time
    is included in the test output.

## Definition of done

All 11 criteria green in CI, ruff and mypy clean, the purity rule test passes,
docstring documents the no-terminal-SoC decision and the deferred cycle cap.

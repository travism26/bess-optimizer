# ADW Feature Spec: M3b, Energy + AS Co-optimization LP

- **Repo:** bess-optimizer
- **Master spec:** specs/M3_ancillary_services.md (formulation and frozen additions live there; on any conflict the master wins)
- **Depends on:** M2 merged. Independent of M3a technically (pure arrays); sequenced after it so PRs land one at a time.
- **Implements:** `AsProduct`, `DEFAULT_AS_PRODUCTS`, `AsDispatchResult` in src/bess/models.py, src/bess/optimizer/as_lp.py, tests/test_as_optimizer_golden.py, tests/test_as_optimizer_properties.py

## Objective

Implement `optimize_dispatch_as` exactly per the master's LP formulation:
one HiGHS solve that co-optimizes energy dispatch with per-product AS
capacity awards under perfect foresight. Pure function, arrays in, result
out, mirroring `optimize_dispatch`, which must remain byte-for-byte
untouched (it is the frozen M4 Rust target).

## In scope

1. Models additions per the master: `AsProduct`, `DEFAULT_AS_PRODUCTS`
   (five products with the master's default sustain hours),
   `AsDispatchResult`. Frozen dataclasses, additive only.
2. `optimize_dispatch_as(prices, as_prices, as_available, dt_hours,
   battery, products) -> AsDispatchResult`, signature exactly as frozen in
   the master, formulation exactly per the master's "LP formulation"
   section including the three pinned conventions (end-of-interval SoC
   adequacy, no award cap at power_mw, capacity-only).
3. Input validation: shape agreement between as_prices, as_available, and
   products; unknown direction strings raise.
4. Revenue decomposition on the result: energy_revenue_usd plus
   as_revenue_usd equals dispatch.objective_value (within LP tolerance).
5. Both test files below. No change to optimizer/lp.py or any frozen M1/M2
   interface.

## Out of scope

Data ingestion (M3a), backtest and CLI wiring (M3c), rolling-horizon AS,
deployment modeling, MILP exclusivity, any per-product offer logic.

## Acceptance criteria

Golden (exact, within 1e-6 unless stated):

1. **Masked equivalence.** Any price series with as_available all False:
   objective equals `optimize_dispatch` on the same inputs within 1e-6 and
   awards_mw is identically zero.
2. **Zero-price equivalence.** as_available all True, as_prices all zero:
   objective equals `optimize_dispatch` within 1e-6. Do NOT assert awards;
   they are degenerate at zero price (memory:
   lp-optimizer-degeneracy-in-tests).
3. **Pure REG_UP golden == 240.0.** T=24, dt=1, energy prices all $0,
   battery 1 MW / 1 MWh, eff 1.0/1.0, initial SoC 0. REG_UP only, sustain
   1.0 h, MCPC $10 every hour. Optimal: charge 1 MW in hour 0 (free
   energy, SoC ends hour 0 full at 1.0 MWh, which backs an hour-0 award
   under the end-of-interval convention), then award 1 MW every hour
   (adequacy caps at SoC 1.0; idle coupling caps at power_mw). 24 x 1 x
   $10 == 240.0. The 1 MWh capacity is load-bearing: with 2 MWh the LP
   legitimately reaches $250 by charging again in hour 1, because
   charging raises the up-coupling headroom to 2 MW for that hour.
4. **Additive golden == 250.0.** T=2, dt=1, energy prices [$0, $100],
   battery 1 MW / 1 MWh, eff 1.0/1.0, initial SoC 0. REG_UP only, sustain
   1.0 h, MCPC [$150, $0]. Optimal: hour 0 charge 1 MW (s_0 = 1, coupling
   (0 - 1) + a <= 1 allows a <= 2, adequacy allows a <= 1) and award 1 MW
   for $150; hour 1 discharge for $100. Objective == 250.0. This golden
   locks in both pinned conventions (end-of-interval adequacy AND
   awards-beyond-power while charging).
5. **REG_DOWN room golden == 150.0.** T=2, dt=1, energy prices [$0, $0],
   battery 1 MW / 2 MWh, eff 1.0/1.0, initial SoC 2.0 (full). REG_DOWN
   only, sustain 1.0 h, MCPC [$50, $50]. Optimal: discharge 1 MW each hour
   purely to open room; hour 0 award 1 MW (room 2 - s_0 = 1), hour 1 award
   2 MW (room 2, coupling (0 - 1) + a <= 1 allows a <= 2). 50 + 100 ==
   150.0. Locks in the down-room adequacy and the swing capability.

Properties, on the July 2023 energy fixture with the July AS fixture
matrices (build the (P, T) inputs inline in the test; M3a's fixture files
are committed by the time this slice runs, but do not depend on M3a code):

6. solver_status "optimal"; every M1 property from test_optimizer_properties
   still holds on the co-optimized dispatch (SoC bounds, dynamics residual
   < 1e-6, power bounds).
7. Constraint residuals within 1e-6 everywhere: up coupling, down
   coupling, up adequacy, down room adequacy; awards >= 0; masked awards
   exactly 0.
8. Decomposition: energy_revenue_usd + as_revenue_usd ==
   dispatch.objective_value within 1e-4, and each recomputes from the raw
   arrays within 1e-4.
9. Dominance: co-opt objective >= energy-only objective on the same prices
   minus 1e-6 (awards are optional, so co-opt can never lose).
10. **Runtime:** a synthetic 2-year, 5-product co-opt solve (T = 17,520,
    P = 5, about 122k variables) completes in under 60 seconds; record the
    wall time in the test output.

## Gotchas

1. Degeneracy: outside the strict goldens above, assert revenue and
   residuals, never raw award values.
2. Awards exceeding power_mw while charging is correct swing capability;
   do not "fix" it. Golden 4 and golden 5 both fail if someone caps a_pt.
3. highspy is untyped: explicit casts/annotations for anything read from
   the solver (memory: highspy-untyped-mypy).
4. Build the (P, T) matrices row-ordered by the products tuple; a mismatch
   between row order and product order is silent revenue misattribution.
   One property test shuffles product order and asserts identical totals.

## Definition of done

All 10 criteria green in CI, ruff and mypy clean, `optimize_dispatch_as`
docstring states the formulation, the three pinned conventions, and the
capacity-only caveat, optimizer/lp.py untouched, no frozen interface
changed.

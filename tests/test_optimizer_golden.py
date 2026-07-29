"""Golden-value tests for optimize_dispatch (acceptance criteria 1-4).

Each test constructs a tiny synthetic price series with a hand-derivable
optimum and asserts the objective to 1e-6. No fixtures, no network.
"""

# TODO(AC-1) Golden, flat prices: T=24, all prices $50, eff 0.9/0.9.
#   Objective == 0.0 within 1e-6. Assert zero revenue, NOT zero dispatch.

# TODO(AC-2) Golden, step prices, lossless: T=24, hours 0-11 at $10, hours
#   12-23 at $100. Battery 1 MW / 2 MWh, eff 1.0/1.0, initial SoC 0.
#   Charge 2 MWh at $10 (cost $20), discharge 2 MWh at $100 (revenue $200).
#   Objective == 180.0 within 1e-6.

# TODO(AC-3) Golden, step prices, lossy charge: same prices, 1 MW / 2 MWh,
#   charge_eff 0.8, discharge_eff 1.0. Draw 2.5 MWh from grid (1.0, 1.0,
#   0.5 MW hours) costing $25, discharge 2 MWh for $200.
#   Objective == 175.0 within 1e-6.

# TODO(AC-4) Golden, negative price: T=24, one hour at -$50, all others $0.
#   Battery 1 MW / 2 MWh, eff 0.9/0.9. Charge 1 MW during the negative hour,
#   paid $50. Objective == 50.0 within 1e-6.

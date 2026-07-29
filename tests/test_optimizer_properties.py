"""Property and behavior tests for optimize_dispatch (acceptance criteria 5-7).

Runs against a small frozen fixture (one month of HB_NORTH 2023 under
tests/fixtures/), never the network.
"""

# TODO(AC-5) Properties on the frozen HB_NORTH 2023 month fixture:
#   - solver_status == "optimal"
#   - 0 <= soc <= energy_mwh for all t (tolerance 1e-6)
#   - SoC dynamics residual < 1e-6 at every t when recomputed from c, d
#   - Revenue recomputed from (prices, c, d) equals objective_value within 1e-4
#   - c_t <= power_mw and d_t <= power_mw everywhere

# TODO(AC-6) Simultaneous charge/discharge detection: construct a case with a
#   deeply negative price and a full battery; assert simultaneous_hours > 0 and
#   that it is reported (with a WARNING logged), not raised. This is expected
#   LP behavior: burning energy through efficiency losses is genuinely
#   profitable at negative prices.

# TODO(AC-7) Runtime budget: full 2-year single-horizon solve (T=17,520)
#   completes in under 30 seconds on a laptop; the actual time is recorded in
#   the metrics JSON. Use synthetic prices so no large fixture is needed.

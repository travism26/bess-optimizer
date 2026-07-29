"""End-to-end backtest and CLI tests (acceptance criteria 7 and 8).

Runs run_backtest and the Typer CLI against cached fixtures only; the conftest
network guard enforces acceptance criterion 9.
"""

# TODO(AC-8) CLI end-to-end: `bess backtest --config config.toml` against
#   cached fixtures produces metrics JSON per hub, a combined comparison table,
#   and both PNG plots (dispatch detail, cumulative revenue) with nonzero
#   content. Use typer.testing.CliRunner and a tmp_path cache/output dir.

# TODO(metrics) BacktestResult correctness on a fixture month: total revenue,
#   revenue per MW-year, revenue per MWh discharged, total MWh discharged,
#   equivalent full cycles (discharged MWh / energy_mwh), daily revenue series,
#   and simultaneous_hours total are internally consistent.

# TODO(AC-7) solve_time_seconds is present in the metrics JSON and positive.

# TODO(oracle-hook) run_backtest accepts a custom `optimizer` callable and uses
#   it (this is the seam where the M4 Rust engine drops in unchanged).

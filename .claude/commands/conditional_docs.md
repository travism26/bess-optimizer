# Conditional Documentation Guide

This prompt helps you determine what documentation you should read based on the specific changes you need to make in the codebase. Review the conditions below and read the relevant documentation before proceeding with your task.

## Instructions

- Review the task you've been asked to perform
- Check each documentation path in the Conditional Documentation section
- For each path, evaluate if any of the listed conditions apply to your task
  - IMPORTANT: Only read the documentation if any one of the conditions match your task
- IMPORTANT: You don't want to excessively read documentation. Only read the documentation if it's relevant to your task.

## Conditional Documentation

- README.md

  - Conditions:
    - When first understanding the project structure
    - When you want to learn the commands to build or run the application
    - When understanding the overall architecture

- CLAUDE.md
- specs/M1_python_core.md

  - Conditions:
    - When understanding the overall application architecture
    - When adding new modules or packages
    - When implementing new features
    - When working with external integrations
    - IMPORTANT: Required reading before implementing any major feature

- app_docs/feature-3c648beb-data-layer.md

  - Conditions:
    - When working with `src/bess/data/prices.py` or `fetch_da_prices`
    - When touching the `bess fetch` CLI command
    - When adding tests that need DST-transition or raw gridstatus fixtures
    - When troubleshooting gridstatus DAM archive vs. recent-documents behavior
    - When adding a `pytest.mark.manual`-style network-touching test

- app_docs/feature-3b9cf1a9-lp-optimizer.md

  - Conditions:
    - When working with `src/bess/optimizer/lp.py` or `optimize_dispatch`
    - When modifying the HiGHS LP formulation, column layout, or SoC recursion
    - When adding golden or property tests for the optimizer
    - When troubleshooting simultaneous charge/discharge or non-optimal solver status
    - When touching the module's import list (purity rule enforcement)

- app_docs/feature-27b2b22d-backtest-cli-plots.md

  - Conditions:
    - When working with `src/bess/backtest/runner.py` or `run_backtest`
    - When touching the `bess backtest` or `bess plot` CLI commands
    - When modifying `src/bess/viz/plots.py` (dispatch detail or cumulative revenue plots)
    - When changing revenue/cycles metrics math or annualization logic
    - When troubleshooting metrics JSON determinism or output directory resolution
    - When adding tests to `tests/test_backtest_integration.py`

- adws/README.md

  - Conditions:
    - When you're operating in the `adws/` directory
    - When working with AI Developer Workflows

- .claude/commands/classify_adw.md

  - Conditions:
    - When adding or removing new `adws/adw_*.py` files

## Python Project Structure

The project follows the standard Python project layout:

```
```
bess/
├── config.toml            # battery + window defaults
├── pyproject.toml         # uv-managed; ruff/mypy/pytest config
├── specs/
│   └── M1_python_core.md  # authoritative master spec
├── ai_docs/               # project context + M1a/M1b/M1c feature specs
├── src/bess/
│   ├── models.py          # FROZEN dataclasses: BatterySpec, DispatchResult, BacktestResult
│   ├── data/prices.py     # gridstatus fetch + canonical schema + parquet cache (only module that may import gridstatus)
│   ├── optimizer/lp.py    # optimize_dispatch(), pure: numpy + highspy only
│   ├── backtest/runner.py # run_backtest(), optimizer injected as a callable
│   ├── viz/plots.py       # dispatch detail + cumulative revenue PNGs
│   └── cli.py             # Typer app: bess fetch | backtest | plot
├── tests/                 # golden, property, data, integration; conftest blocks sockets
│   └── fixtures/          # frozen parquet slices, committed
├── data/                  # price cache (gitignored)
└── rust/                  # M4 PyO3 engine (empty for now)
```
```

## Development Patterns

When working on this Python project:

- Frozen contracts live in `src/bess/models.py` and the signatures of `optimize_dispatch`, `fetch_da_prices`, `run_backtest`; never change them without a spec change (the M4 Rust engine drops in behind them)
- All data messiness (timezones, gaps, caching, gridstatus) belongs in `src/bess/data/prices.py`; nothing else may import gridstatus
- `optimize_dispatch` stays pure: numpy in, DispatchResult out; no pandas, no I/O, no timezone logic
- New CLI commands are Typer subcommands in `src/bess/cli.py`, defaults read from `config.toml`
- Every new behavior gets a test that runs from `tests/fixtures/` without network access

<!--
Replace with project-specific guidance, e.g.:
- **Adding new modules**: Look at `<dir>/` for existing patterns
- **Configuration**: Use `<config dir>/` for app configuration
- **Data models**: Define in `<models dir>/`
-->

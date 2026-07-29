# CLAUDE.md

Guidance for agents working in this repository. The authoritative spec is
`specs/M1_python_core.md`; read it before implementing anything.

## Commands

Python 3.12, managed with uv. All commands run from the repo root.

```
uv sync                 # install runtime + dev dependencies into .venv
uv run pytest           # run tests (never touch the network; see below)
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy             # type check (config in pyproject.toml)
uv run bess --help      # the Typer CLI: fetch, backtest, plot
uv run pre-commit run --all-files
```

CI (`.github/workflows/ci.yml`) runs ruff check, mypy, and pytest on every push
and PR. All three must be green.

## Frozen interfaces (do not change without a spec change)

`BatterySpec`, `DispatchResult`, and `BacktestResult` in `src/bess/models.py`,
plus the signatures of `optimize_dispatch`, `fetch_da_prices`, and
`run_backtest`, are frozen contracts. The M4 Rust engine must drop in behind
the same shapes.

`optimize_dispatch` is pure: numpy arrays in, `DispatchResult` out. No I/O, no
DataFrames, no timezone logic, no logging of data files inside it. All data
messiness (timezones, gaps, caching, gridstatus) lives in
`src/bess/data/prices.py`, which is the only module allowed to import
gridstatus.

## Canonical price schema

Parquet columns, this exact set and naming (it survives unchanged into
Snowflake in M5):

| column             | type                     | notes                     |
| ------------------ | ------------------------ | ------------------------- |
| interval_start_utc | timestamp[us, tz=UTC]    | strictly increasing       |
| interval_end_utc   | timestamp[us, tz=UTC]    |                           |
| iso                | string                   | "ERCOT"                   |
| market             | string                   | "DAY_AHEAD_HOURLY"        |
| location           | string                   | "HB_NORTH" etc.           |
| location_type      | string                   | "Trading Hub"             |
| price              | float64                  | $/MWh, negatives allowed  |

No duplicates, no gaps within the requested window. Gaps fail loudly with the
missing intervals listed; never silently interpolate.

## Known gotchas

1. **DST:** ERCOT publishes day-ahead prices in prevailing Central Time.
   Spring-forward days have 23 hours, fall-back days have 25. gridstatus
   returns tz-aware timestamps; convert to UTC immediately and never assume 24
   rows per calendar day.
2. **Negative prices are valid data,** not errors. Do not clip or filter them.
   Simultaneous charge/discharge at negative prices is expected LP behavior:
   report it via `simultaneous_hours` and log a WARNING, never raise. The MILP
   exclusivity fix is explicitly deferred; do not add it.

## Rules

- Tests must never touch the network. `tests/conftest.py` blocks socket
  connections; everything runs from fixtures under `tests/fixtures/`.
  gridstatus is exercised only by running `bess fetch` manually.
- Never commit secrets, API keys, or data files. `data/*.parquet` is
  gitignored; only the small frozen fixtures under `tests/fixtures/` are
  tracked.
- No em-dashes anywhere in docs or comments. Use commas, colons, or
  parentheses instead.

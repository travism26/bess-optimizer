# ADW Feature Spec: M1, BESS Optimizer Python Core

- **Project:** bess-optimizer (public repo, MIT license)
- **Milestone:** M1 of 6
- **Target pipeline:** ADW plan -> build -> validate -> test -> review -> document
- **Language:** Python 3.12
- **Estimated size:** ~1,200-1,800 LOC including tests

## Objective

A working, tested Python implementation of perfect-foresight battery energy arbitrage:
ingest ERCOT day-ahead hub prices, solve a linear program for the revenue-maximizing
charge/discharge schedule under real battery constraints, backtest over 2023-2024, and
emit plots plus a metrics report. This module is the correctness oracle for the later
Rust engine (M4), so interfaces defined here are frozen contracts.

## In scope

1. Price ingestion via gridstatus for ERCOT DA hourly settlement point prices,
   hubs HB_NORTH, HB_HOUSTON, HB_WEST, window 2023-01-01 through 2024-12-31,
   cached to local parquet.
2. LP dispatch optimizer (full-horizon, perfect foresight) via highspy.
3. Backtest runner producing revenue metrics per hub.
4. Matplotlib plots: 7-day dispatch detail (price, charge/discharge, SoC) and
   cumulative revenue by hub.
5. Typer CLI: `bess fetch`, `bess backtest`, `bess plot`.
6. Full test suite per Acceptance Criteria below.

## Out of scope (do not build)

Real-time market, ancillary services, forecasting, rolling-horizon mode (M2),
degradation models beyond throughput accounting, Rust (M4), Snowflake (M5),
AWS (M5), dashboard (M6), CAISO, MILP charge/discharge exclusivity.

## Repository layout

```
src/bess/
  models.py            # dataclasses: BatterySpec, DispatchResult, BacktestResult
  data/prices.py       # fetch + canonicalize + parquet cache
  optimizer/lp.py      # optimize_dispatch()
  backtest/runner.py   # run_backtest()
  viz/plots.py
  cli.py
tests/
  test_optimizer_golden.py
  test_optimizer_properties.py
  test_data.py
  test_backtest_integration.py
  fixtures/            # small frozen parquet slices, no network in CI
```

## Frozen interfaces

```python
@dataclass(frozen=True)
class BatterySpec:
    power_mw: float            # symmetric charge/discharge limit
    energy_mwh: float          # usable capacity (SoC upper bound)
    charge_eff: float          # fraction, e.g. 0.927
    discharge_eff: float       # fraction, e.g. 0.927
    initial_soc_mwh: float = 0.0
    max_cycles_per_day: float | None = None   # None in M1 default config

@dataclass(frozen=True)
class DispatchResult:
    charge_mw: np.ndarray      # shape (T,), >= 0
    discharge_mw: np.ndarray   # shape (T,), >= 0
    soc_mwh: np.ndarray        # shape (T,), SoC at END of each interval
    objective_value: float     # $ revenue from the solver
    solver_status: str         # must be "optimal" for success
    simultaneous_hours: int    # count of t where both charge and discharge > 1e-3 MW

def optimize_dispatch(
    prices: np.ndarray,        # $/MWh, shape (T,), may contain negatives
    dt_hours: float,           # 1.0 for hourly
    battery: BatterySpec,
) -> DispatchResult: ...

def fetch_da_prices(
    location: str,             # e.g. "HB_NORTH"
    start: date,
    end: date,
    cache_dir: Path,
) -> pd.DataFrame: ...         # canonical schema below, sorted, deduplicated

def run_backtest(
    prices_df: pd.DataFrame,   # canonical schema, single location
    battery: BatterySpec,
    optimizer: Callable[..., DispatchResult] = optimize_dispatch,
) -> BacktestResult: ...
```

`optimize_dispatch` is pure: no I/O, no DataFrames, no timezone logic. All data
messiness is handled in `data/prices.py`. The `optimizer` parameter on
`run_backtest` exists so the M4 Rust implementation drops in unchanged.

## Canonical price schema

Parquet columns, this exact set and naming (it survives unchanged into Snowflake in M5):

```
interval_start_utc  timestamp[us, tz=UTC]
interval_end_utc    timestamp[us, tz=UTC]
iso                 string   ("ERCOT")
market              string   ("DAY_AHEAD_HOURLY")
location            string   ("HB_NORTH" etc.)
location_type       string   ("Trading Hub")
price               float64  ($/MWh, negatives allowed)
```

Requirements: strictly increasing interval_start_utc per location, no duplicates,
no gaps within the requested window (fail loudly listing missing intervals rather
than silently interpolating).

## LP formulation (implement exactly this)

Decision variables for t = 0..T-1: charge c_t (MW), discharge d_t (MW),
state of charge s_t (MWh, end of interval t).

Maximize: sum_t [ p_t * (d_t - c_t) * dt ]

Subject to:
- s_0 = initial_soc + eta_c * c_0 * dt - (d_0 * dt) / eta_d
- s_t = s_{t-1} + eta_c * c_t * dt - (d_t * dt) / eta_d,  for t >= 1
- 0 <= c_t <= power_mw
- 0 <= d_t <= power_mw
- 0 <= s_t <= energy_mwh
- No terminal SoC constraint (with default initial SoC of 0 the optimizer will not
  strand valuable energy; document this).

Solver: HiGHS via highspy. Assert model status is optimal; any other status raises.

## Default config (config.toml)

```
power_mw = 100.0
energy_mwh = 200.0
charge_eff = 0.927        # sqrt(0.86) each way, 86% round trip
discharge_eff = 0.927
initial_soc_mwh = 0.0
locations = ["HB_NORTH", "HB_HOUSTON", "HB_WEST"]
start = 2023-01-01
end = 2024-12-31
```

## Backtest metrics (BacktestResult)

Total revenue ($), revenue per MW-year ($/MW-yr), revenue per MWh discharged,
total MWh discharged, equivalent full cycles (discharged MWh / energy_mwh),
daily revenue series, simultaneous_hours total. Emit as JSON per hub plus a
combined comparison table.

## Acceptance criteria (evals; all must pass)

1. **Golden, flat prices:** T=24, all prices $50, eff 0.9/0.9.
   Objective == 0.0 within 1e-6. (Do not assert zero dispatch; assert zero revenue.)
2. **Golden, step prices, lossless:** T=24, hours 0-11 at $10, hours 12-23 at $100.
   Battery 1 MW / 2 MWh, eff 1.0/1.0, initial SoC 0.
   Optimal: charge 2 MWh at $10 (cost $20), discharge 2 MWh at $100 (revenue $200).
   Objective == 180.0 within 1e-6.
3. **Golden, step prices, lossy charge:** same prices, 1 MW / 2 MWh,
   charge_eff 0.8, discharge_eff 1.0.
   Optimal: draw 2.5 MWh from grid (hours at 1.0, 1.0, 0.5 MW) costing $25,
   discharge 2 MWh for $200. Objective == 175.0 within 1e-6.
4. **Golden, negative price:** T=24, one hour at -$50, all others at $0.
   Battery 1 MW / 2 MWh, eff 0.9/0.9.
   Optimal: charge 1 MW during the negative hour, paid $50. Objective == 50.0
   within 1e-6.
5. **Properties on real fixture data** (one frozen month of HB_NORTH 2023):
   - solver_status == "optimal"
   - 0 <= soc <= energy_mwh for all t (tolerance 1e-6)
   - SoC dynamics residual < 1e-6 at every t when recomputed from c, d
   - Revenue recomputed from (prices, c, d) equals objective_value within 1e-4
   - c_t <= power_mw and d_t <= power_mw everywhere
6. **Simultaneous charge/discharge detection:** construct a case with a deeply
   negative price and a full battery; assert simultaneous_hours > 0 and that it is
   reported, not raised. This is expected LP behavior (burning energy through
   efficiency losses is genuinely profitable at negative prices). Log a WARNING.
7. **Runtime budget:** full 2-year single-horizon solve (T=17,520) completes in
   under 30 seconds on a laptop; record actual time in the metrics JSON.
8. **CLI end-to-end:** `bess backtest --config config.toml` against cached fixtures
   produces metrics JSON and both PNG plots with nonzero content.
9. **No network in CI:** all tests run from fixtures; gridstatus is only exercised
   by `bess fetch` manually.

## Known gotchas (build phase must handle these)

1. **DST:** ERCOT publishes DA in prevailing Central Time. Spring-forward days
   have 23 hours, fall-back days have 25. gridstatus returns tz-aware timestamps;
   convert to UTC immediately and never assume 24 rows per calendar day.
2. **Simultaneous charge/discharge:** see acceptance criterion 6. The MILP fix
   (binary mutual exclusivity) is explicitly deferred; do not add it.
3. **Negative prices are valid data**, not errors. Do not clip or filter.
4. **gridstatus API surface** changes between versions; pin the version in
   pyproject.toml and isolate all gridstatus calls inside data/prices.py.

## Definition of done

All 9 acceptance criteria green in CI, ruff + mypy clean, README section for M1
with a results table (revenue per MW-year by hub by year) and the two plots,
fixtures committed, no secrets or API keys anywhere in history.

# ADW Feature Spec: M3, Ancillary Service Co-optimization (master)

- **Project:** bess-optimizer (public repo, MIT license)
- **Milestone:** M3 of 6
- **Slices:** M3a (specs/M3a_as_data_layer.md), M3b (specs/M3b_as_cooptimizer.md), M3c (specs/M3c_as_backtest_cli.md); on any conflict this master wins
- **Language:** Python 3.12
- **Depends on:** M2 merged (perfect + rolling backtests, benchmarks, sweeps)

## Objective

The README has promised this since day one: the majority of real ERCOT BESS
revenue in recent years came from ancillary services, not energy arbitrage,
so every number the project reports so far understates the opportunity. M3
co-optimizes day-ahead energy with AS capacity awards (Reg Up, Reg Down,
RRS, ECRS, Non-Spin) in a single LP under perfect foresight. Headline
metric: **AS uplift**, co-optimized total revenue divided by energy-only
revenue, plus the revenue mix by product.

## In scope

1. AS clearing-price ingestion: ERCOT DAM MCPCs for the five products,
   2023-01-01 through 2024-12-31, canonical schema, parquet cache, frozen
   fixture slices.
2. Co-optimization LP: energy dispatch plus per-product capacity awards,
   capacity payments only, exact formulation below.
3. Backtest integration: `run_backtest_as`, CLI `bess backtest --ancillary`,
   metrics JSON gains an additive `ancillary` block.
4. Analytics: AS uplift and revenue mix, surfaced via `bess benchmark`
   alongside the M2 capture rates.
5. README M3 section with the uplift headline and an honest model
   assumptions note.

## Out of scope (do not build)

AS deployment energy and performance payments, offer curves or award
uncertainty (we are a price taker, see assumptions), rolling-horizon
combined with AS (perfect foresight only in M3), real-time AS (SCED),
AS demand curves and ORDC adders, CAISO, MILP exclusivity, Rust (M4),
Snowflake/AWS (M5), dashboard (M6).

## Frozen interfaces

Nothing in the M1 or M2 frozen sets changes. `optimize_dispatch` remains
the M4 Rust port target exactly as is; `optimize_dispatch_as` is a second
pure function and a candidate later port, not part of M4's initial scope.
M3 adds, and then freezes:

```python
@dataclass(frozen=True)
class AsProduct:
    name: str              # canonical product name, e.g. "REG_UP"
    direction: str         # "up" | "down"
    sustain_hours: float   # energy adequacy duration backing an award

DEFAULT_AS_PRODUCTS: tuple[AsProduct, ...]   # the five ERCOT products, defaults below

@dataclass(frozen=True)
class AsDispatchResult:
    dispatch: DispatchResult        # objective_value is the FULL co-optimized $
    products: tuple[AsProduct, ...] # row order for awards_mw and as_prices
    awards_mw: np.ndarray           # shape (P, T), >= 0
    energy_revenue_usd: float       # sum_t p_t * (d_t - c_t) * dt
    as_revenue_usd: float           # sum_{p,t} q_pt * a_pt * dt

def optimize_dispatch_as(
    prices: np.ndarray,             # (T,) $/MWh, may contain negatives
    as_prices: np.ndarray,          # (P, T) MCPC $/MW-h, rows ordered as products
    as_available: np.ndarray,       # (P, T) bool; False forces the award to 0
    dt_hours: float,
    battery: BatterySpec,
    products: tuple[AsProduct, ...],
) -> AsDispatchResult: ...

def fetch_as_prices(
    start: date,
    end: date,
    cache_dir: Path,
) -> pd.DataFrame: ...              # canonical AS schema below; MCPCs are system-wide, no location

@dataclass(frozen=True)
class AsBacktestResult:
    energy: BacktestResult          # M1 metrics computed on the co-optimized dispatch
    total_revenue_usd: float        # energy + AS
    as_revenue_usd: float
    revenue_by_product: pd.Series   # index: product name, values: $ over the window
    award_mw_hours: pd.Series       # index: product name, values: MW-h awarded

def run_backtest_as(
    prices_df: pd.DataFrame,        # canonical energy schema, single location
    as_prices_df: pd.DataFrame,     # canonical AS schema, same window
    battery: BatterySpec,
    products: tuple[AsProduct, ...] = DEFAULT_AS_PRODUCTS,
    optimizer: Callable[..., AsDispatchResult] = optimize_dispatch_as,
) -> AsBacktestResult: ...
```

`optimize_dispatch_as` is pure exactly like `optimize_dispatch`: arrays in,
result out, no I/O, no DataFrames, no timezone logic. The wide (P, T)
matrices are built in the backtest layer from the long canonical frame.

## Canonical AS price schema

Parquet columns, long format, one row per (interval, product). Mirrors the
energy schema so it lands in Snowflake unchanged in M5. ERCOT DAM MCPCs are
system-wide, so there is no location column.

```
interval_start_utc  timestamp[us, tz=UTC]
interval_end_utc    timestamp[us, tz=UTC]
iso                 string   ("ERCOT")
market              string   ("DAM_AS")
product             string   ("REG_UP" | "REG_DOWN" | "RRS" | "ECRS" | "NONSPIN")
price               float64  (MCPC, $ per MW per hour)
```

Requirements: per product, strictly increasing interval_start_utc, no
duplicates, no gaps within that product's validation window (fail loudly
listing missing (product, interval) pairs). **A product's validation window
starts at the later of the requested start and the product's market launch:
ECRS first cleared 2023-06-10. Absence before launch is structural, not a
data gap.** The build phase records the launch date as a named constant in
the data layer.

## LP formulation (implement exactly this)

All M1 variables, dynamics, and bounds are unchanged. Add award variables
a_pt >= 0 for each product p, interval t. Let UP be the up products
(REG_UP, RRS, ECRS, NONSPIN) and DOWN be {REG_DOWN}. q_pt is the MCPC.

Maximize: sum_t [ p_t * (d_t - c_t) * dt + sum_p q_pt * a_pt * dt ]

Subject to, for every t (in addition to all M1 constraints):

- Up coupling:    (d_t - c_t) + sum_{p in UP} a_pt <= power_mw
- Down coupling:  (c_t - d_t) + a_{REG_DOWN,t}     <= power_mw
- Up energy adequacy:   sum_{p in UP} sustain_p * a_pt <= s_t * discharge_eff
- Down room adequacy:   charge_eff * sustain_REG_DOWN * a_{REG_DOWN,t} <= energy_mwh - s_t
- Availability: a_pt = 0 wherever as_available[p, t] is False (implement as
  a zero upper bound, not a constraint row).

Conventions, pinned deliberately:

1. Adequacy uses **end-of-interval SoC s_t**, consistent with the frozen
   DispatchResult convention. Start-of-interval is equally defensible; this
   choice is documented in the docstring, and the goldens below are derived
   from it.
2. Awards MAY exceed power_mw while the battery is charging (curtailing a
   charge is real up capability; the coupling constraint captures the full
   swing). This is correct, not a bug; do not cap a_pt at power_mw.
3. Capacity payments only: awards never move SoC. Deployment energy is out
   of scope and the README must say so.

Solver: HiGHS via highspy, same status handling as M1 (anything but
optimal raises). Simultaneous charge/discharge stays report-and-warn.

## Modeling assumptions (document these verbatim in the README)

Price taker: our awards never move the MCPC. 100 percent clearing: every
offered MW is awarded at the clearing price. Capacity payments only: no
deployment energy, no performance or mileage payments, no failure-to-provide
risk. Sustain durations are modeling assumptions approximating ERCOT
duration rules, not tariff citations. Under these assumptions the co-opt
number OVERSTATES achievable AS revenue, the mirror image of the energy-only
understatement; the honest number lies between, and the README M3 section
must frame it exactly that way.

## Config additions (config.toml)

```
[ancillary]
enabled = false            # backtest co-opt off unless --ancillary or this flag
products = ["REG_UP", "REG_DOWN", "RRS", "ECRS", "NONSPIN"]

[ancillary.sustain_hours]  # defaults for DEFAULT_AS_PRODUCTS
REG_UP = 1.0
REG_DOWN = 1.0
RRS = 1.0
ECRS = 2.0
NONSPIN = 4.0
```

## Acceptance criteria (rollup; slices carry the detail)

M3a: canonical AS schema round trip, per-product gap validation with the
ECRS launch rule, DST day row counts (23/25 per product), July 2023 fixture
plus DST raw samples committed, `bess fetch` extended, no network in tests.

M3b: masked equivalence golden (all-unavailable mask reproduces the M1
objective exactly and awards are identically zero), zero-price equivalence
golden (objective only; awards are degenerate at zero price, do not assert
them), pure REG_UP golden (240.0), additive golden (250.0), REG_DOWN room
golden (150.0), constraint-residual and decomposition properties on the
fixture, dominance (co-opt >= energy-only), runtime (2-year, 5-product
co-opt solve under 60 s).

M3c: CLI end to end from fixtures (`--ancillary` writes the additive
ancillary metrics block to a qualified filename), uplift and revenue mix
via `bess benchmark` with clean skip when inputs are missing, determinism
excluding the documented wall-time field, uplift sanity corridor
[1.0, 8.0], README M3 section with real fixture-month numbers.

## Known gotchas

1. **gridstatus AS API surface:** `Ercot.get_as_prices(date, end)` exists in
   the pinned 0.36.0; `get_mcpc_dam` is the fallback. The M1a lesson applies
   (get_spp was unreliable for historical DAM; get_dam_spp(year) was the
   fix): the research phase must verify which call actually serves
   2023-2024 history and note column naming per product. All calls stay
   inside the data layer.
2. **ECRS launch (2023-06-10):** pre-launch absence is structural. The
   availability mask, not fabricated zero rows, represents it. The 2023
   March DST sample is pre-ECRS on purpose so the mask path stays tested.
3. **LP degeneracy:** at zero MCPC the solver may return arbitrary awards
   with identical revenue. Tests assert revenue and constraint residuals,
   never raw award values, except where the optimum is strict (memory:
   lp-optimizer-degeneracy-in-tests).
4. **Metrics filename collisions:** ancillary runs write to a filename
   qualified with the mode AND the ancillary flag (memory:
   metrics-json-unqualified-filename-collision).
5. **DST applies to AS frames too:** 23/25-hour local market days, same as
   energy. Reuse the M2a day-slicing helper; do not reimplement it.

## Definition of done

All three slices merged, all acceptance criteria green in CI, ruff and mypy
clean, README M3 section live with the uplift headline, revenue mix, and
the assumptions note, fixtures committed, no change to any M1 or M2 frozen
interface, no secrets or data files in history.

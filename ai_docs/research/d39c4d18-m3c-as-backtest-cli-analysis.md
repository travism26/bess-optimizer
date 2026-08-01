# Research: M3c, AS backtest runner, CLI `--ancillary`, benchmark uplift, README

## Metadata

adw_id: `d39c4d18`
prompt: `specs/M3c_as_backtest_cli.md`
date: `2026-08-01`

## Executive Summary

M3c is the integration slice: it has no new math, only wiring. Both
prerequisites (M3a data layer, M3b co-optimizer) are present on this branch
(cut from `d2c0d8f`, which is `origin/main`'s head), so the stale-worktree
pitfall that bit M3b does not apply here and no pre-merge is needed. Every
seam M3c needs already exists and is well-shaped: `metrics_from_dispatch` is
already factored out of `run_backtest` for exactly this kind of reuse,
`_mode_metrics_path` / `_read_mode_metrics` already implement the
qualified-filename and clean-skip patterns, and `bess fetch` already caches AS
MCPCs.

The one genuine design decision the build phase must get right is what
`AsBacktestResult.energy.total_revenue_usd` holds: the co-optimizer's
`dispatch.objective_value` is the FULL co-optimized dollar figure, so feeding
the raw co-opt `DispatchResult` into `metrics_from_dispatch` would break both
acceptance criterion 2's decomposition identity and M1's
`daily_revenue.sum() == total_revenue_usd` invariant. See "The one real design
decision" below.

Real numbers are already measured against the committed fixtures (not
estimates): **AS uplift = 2.7705x** for HB_NORTH / July 2023, energy-only
$970,937.15 vs co-optimized $2,689,961.68. That sits comfortably inside the
spec's [1.0, 8.0] sanity corridor, and the solve takes 0.02 s.

## Existing Architecture

### Relevant Documentation Found

| Document | What it carries for M3c |
| --- | --- |
| `specs/M3_ancillary_services.md` | Master. Frozen `AsBacktestResult` / `run_backtest_as` signatures, LP formulation, the "Modeling assumptions" paragraph that AC-10 says to copy verbatim into the README, ECRS launch rule, config `[ancillary]` table. Master wins on conflict. |
| `specs/M3c_as_backtest_cli.md` | This slice. 10 acceptance criteria, 4 gotchas. |
| `specs/M2b_benchmarks.md` | The pattern M3c mirrors for the "missing file skips cleanly" behavior. |
| `app_docs/feature-3034ec63-as-cooptimizer.md` | M3b's shipped behavior, degeneracy caveats. |
| `app_docs/feature-325296bb-benchmarks-sweeps.md` | M2b's capture-rate CLI wiring, the direct template for the uplift leg. |
| `ai_docs/memory/entries/` | Four entries bear directly on M3c: `lesson-backtest-shared-solve-for-metrics-and-plots`, `pitfall-metrics-json-unqualified-filename-collision`, `lesson-determinism-tests-exclude-wallclock-fields`, `lesson-lp-optimizer-degeneracy-in-tests`. |
| `README.md` | Has an M1 "Results" and an "M2 results" section; the scope note at line 9-18 is the paragraph AC-10 requires rewriting. |

`README.md` "Architecture" is still a TODO stub; M3c does not have to fix it.

### Component Map

```
config.toml [ancillary]  ──┐
                           v
bess.cli backtest --ancillary
   │
   ├── fetch_da_prices(location, start, end, cache)  ──> energy frame (744 rows)
   ├── fetch_as_prices(start, end, cache)            ──> AS long frame (3720 rows, 5 x 744)
   │        (system-wide, fetched once, NOT per hub)
   v
bess.backtest.as_runner.run_backtest_as          <-- NEW MODULE
   │   1. align long AS frame -> (P, T) price + availability matrices
   │      (launch-rule mask; genuine gaps raise)
   │   2. optimize_dispatch_as(...)  ONE solve            [M3b, existing]
   │   3. metrics_from_dispatch(...) on the energy leg    [M1c, existing]
   │   4. per-product revenue / MW-h rollup
   v
AsBacktestResult ──> cli writes {loc}_metrics_{mode}_ancillary.json
                                                   │
                                                   v
                        bess benchmark ──> bess.analytics.benchmarks
                                             as_uplift(), revenue_mix()   <-- NEW, pure
```

### Key Files and Modules

| File | Purpose / what M3c uses from it |
| --- | --- |
| `src/bess/models.py` | Frozen contracts. Has `AsProduct`, `DEFAULT_AS_PRODUCTS`, `AsDispatchResult` (M3b). Missing `AsBacktestResult`, which M3c adds (models.py:118 is the current end of file). |
| `src/bess/backtest/runner.py` | `solve_dispatch` (runner.py:54) and `metrics_from_dispatch` (runner.py:74) are already split out of `run_backtest` precisely so a caller with its own `DispatchResult` can score it without re-solving. This is the "same code path" gotcha 1 demands. |
| `src/bess/optimizer/as_lp.py` | `optimize_dispatch_as`. Pure, import-restricted to numpy/highspy/bess.models. M3c must not touch it. |
| `src/bess/data/as_prices.py` | `fetch_as_prices`, `AS_CANONICAL_COLUMNS`, `ECRS_LAUNCH = date(2023, 6, 10)` (as_prices.py:62), `_PRODUCT_LAUNCH` (as_prices.py:67), `_cache_path` (as_prices.py:235). |
| `src/bess/cli.py` | `_metrics_dict` (cli.py:73), `_mode_metrics_path` (cli.py:117), `_read_mode_metrics` (cli.py:129), `_mode_block` (cli.py:146), `_run_location` (cli.py:161), `backtest` (cli.py:237), `benchmark` (cli.py:350). |
| `src/bess/analytics/benchmarks.py` | Pure analytics, no I/O. `foresight_capture_rate` (benchmarks.py:74) is the one-line shape `as_uplift` should copy. |
| `src/bess/backtest/rolling.py` | `_local_market_day` (rolling.py:59), `_day_blocks` (rolling.py:77). Master gotcha 5 says reuse these, not reimplement, if day slicing is needed. |
| `tests/fixtures/as_mcpc_2023_07.parquet` | 3720 rows = 5 products x 744 hours, 2023-07-01T05:00Z to 2023-08-01T04:00Z. Exactly matches the energy fixture's window and length. |
| `tests/fixtures/as_2023_03_12_raw.parquet` | 23 rows, wide, `ECRS` column all NaN. The pre-launch mask fixture. |

## Affected Areas

### Files That Will Need Changes

| File | Change | Risk |
| --- | --- | --- |
| `src/bess/models.py` | Add frozen `AsBacktestResult` verbatim from the master. Additive only. | Low |
| `src/bess/backtest/as_runner.py` | NEW. `run_backtest_as` plus the private alignment helper. | Medium (alignment + launch mask is the only real logic) |
| `src/bess/analytics/benchmarks.py` | Add pure `as_uplift(coopt_total, energy_only_total)` and `revenue_mix(revenue_by_product)`. No I/O (spec item 4). | Low |
| `src/bess/cli.py` | `--ancillary` flag, rolling guard, ancillary metrics path helper + reader, benchmark uplift leg, `[ancillary]` config parsing. | Medium (largest diff) |
| `config.toml` | Add the `[ancillary]` and `[ancillary.sustain_hours]` tables exactly as in the master. | Low |
| `tests/test_as_backtest_integration.py` | NEW. Covers all 10 criteria. | Low |
| `README.md` | New "M3 results" section; rewrite the scope note at README.md:9-18. | Low |
| `app_docs/feature-d39c4d18-*.md` | Document phase output. | Low |

Nothing in `optimizer/`, `data/`, or `viz/` needs to change. AS plots are
explicitly out of scope.

### Dependencies

`as_runner.py` will import from `bess.models`, `bess.backtest.runner`
(`metrics_from_dispatch`), `bess.optimizer.as_lp` (`optimize_dispatch_as` as
the default injectable), and `bess.data.as_prices` (the launch-date map).
That last import is safe with respect to the AST import-confinement guard in
`tests/test_as_data.py`: the guard restricts who may import *gridstatus*, and
`as_prices.py` imports gridstatus lazily inside `_fetch_raw`, so importing
`as_prices` costs nothing and violates no rule.

### Integration Points

1. **Metrics JSON filename.** `_mode_metrics_path` yields
   `{location}_metrics_{mode}.json`. The ancillary variant must be a third
   distinct name, e.g. `{location}_metrics_{mode}_ancillary.json` (memory:
   `metrics-json-unqualified-filename-collision`).
2. **`_read_mode_metrics` mode cross-check.** It raises if the file's own
   `mode.mode` field disagrees with the requested mode (cli.py:141). An
   ancillary file written with `mode: "perfect"` under a different filename
   will not trip this, but any reader added for the ancillary file should
   apply the same defensive cross-check.
3. **`bess fetch`** already calls `fetch_as_prices` once per invocation
   (cli.py:230), so the cache the ancillary backtest reads is already
   populated by the existing command. No fetch changes needed.
4. **CLI test cache seeding.** Tests must copy the AS fixture to
   `bess.data.as_prices._cache_path(cache_dir, start, end)`, which resolves to
   `AS_MCPC_2023-07-01_2023-07-31.parquet`, alongside the existing energy
   fixture copy (`tests/test_backtest_integration.py:237` is the template).

## Impact Analysis

### Scope of Change

Moderate and well-bounded: one new module, one new test file, additive fields
on two existing modules, and the largest single diff in `cli.py`. No frozen M1
or M2 interface changes. No optimizer changes. Measured co-opt solve time on
the July fixture is 0.02 s, so runtime is a non-issue for CI.

### The one real design decision

`optimize_dispatch_as` sets `dispatch.objective_value` to the FULL
co-optimized figure (as_lp.py:152, and the `AsDispatchResult` docstring at
models.py:106 says so explicitly). `metrics_from_dispatch` takes
`total_revenue_usd = dispatch.objective_value` (runner.py:102) but computes
`daily_revenue` from `prices * (discharge - charge) * dt` (runner.py:116),
which is the ENERGY leg only.

So passing the raw co-opt `DispatchResult` straight into
`metrics_from_dispatch` breaks two things at once:

- AC-2's identity `energy_revenue_usd + as_revenue_usd == total_revenue_usd`
  becomes `total + as_revenue == total`, which is false.
- M1's invariant `daily_revenue.sum() == total_revenue_usd`
  (asserted at `tests/test_backtest_integration.py:113`) fails by the AS
  revenue, silently making the ancillary mode non-comparable field by field
  with the other modes, which is precisely what gotcha 1 forbids.

**Recommendation:** before calling `metrics_from_dispatch`, replace the
`DispatchResult`'s `objective_value` with `as_dispatch.energy_revenue_usd`
(`dataclasses.replace`, one line). Then `energy` is genuinely the energy leg,
`daily_revenue` sums to it exactly, every derived metric
(`revenue_per_mw_year`, `revenue_per_mwh_discharged`) is an energy-leg number
directly comparable to the M1/M2a runs, and
`AsBacktestResult.total_revenue_usd = energy.total_revenue_usd +
as_revenue_usd` matches the master's `# energy + AS` comment. Verified on the
fixture: the recomputed energy leg matches `energy_revenue_usd` to within
1e-6, and `energy + as` matches the objective to 2.8e-9.

The ancillary metrics block's `energy_revenue_usd` then reads straight off
`energy.total_revenue_usd`, and the block is internally consistent.

### Measured fixture numbers (HB_NORTH, July 2023, 100 MW / 200 MWh, 0.927 each way)

| Quantity | Value |
| --- | --- |
| Energy-only perfect revenue | $970,937.15 |
| Co-optimized total revenue | $2,689,961.68 |
| **AS uplift** | **2.7705x** |
| Co-opt energy leg | $567,376.46 |
| Co-opt AS leg | $2,122,585.22 |
| Co-opt solve time | 0.02 s |
| Simultaneous hours | 0 |

Revenue mix by product:

| Product | Revenue | Share | Award MW-h |
| --- | --- | --- | --- |
| ECRS | $1,275,151.46 | 60.1% | 14,623.9 |
| REG_UP | $447,668.83 | 21.1% | 38,163.4 |
| REG_DOWN | $268,920.72 | 12.7% | 52,581.9 |
| RRS | $130,844.21 | 6.2% | 1,837.4 |
| NONSPIN | $0.00 | 0.0% | 0.0 |

Two facts worth putting in the README rather than hiding:

1. The co-optimized **energy** leg ($567k) is *lower* than the energy-only run
   ($970k). The battery gives up arbitrage to sell capacity. AC-3's dominance
   claim therefore holds on the TOTAL only; a test asserting dominance on the
   energy leg would fail correctly.
2. NONSPIN earns exactly $0 because its 4-hour sustain assumption is
   structurally unaffordable for a 2-hour battery. That is a real modeling
   consequence, not a bug.

### Risks and Considerations

1. **AC-5 is ambiguous.** "the energy-only output files are byte-identical to
   a run without `--ancillary`" admits two readings: (a) the ancillary run
   also runs the energy-only pipeline and writes identical files, or (b) a
   prior no-flag run's files are left unperturbed. Recommendation below picks
   the reading that satisfies both.
2. **Gotcha 4 asks for a window check that the JSON cannot currently answer.**
   `_metrics_dict` (cli.py:73) emits no start/end field. The window is only
   implicit in the `daily_revenue` keys. Options: derive min/max of the
   `daily_revenue` keys from both JSONs and require equality (no schema
   change, zero byte-identity risk), or add an explicit window block. Prefer
   the former.
3. **Per-product mix is degeneracy-exposed.** Memory
   `lp-optimizer-degeneracy-in-tests` records that shuffling product order
   swapped $2,555 between REG_UP and ECRS on this exact fixture. Verified
   here that two runs at fixed product order are bit-identical in awards and
   objective, so AC-8 determinism is safe; but the README mix table is an
   artifact of one particular optimal vertex. Tests must assert aggregate AS
   revenue and the total, never a per-product dollar figure.
4. **The July fixture does not exercise the ECRS mask.** July 2023 is entirely
   post-launch (2023-06-10), so all 744 ECRS hours are present. AC-1's masked
   path needs a different input. Verified working recipe: canonicalize
   `hb_north_2023_03_12_raw.parquet` and `as_2023_03_12_raw.parquet` for
   2023-03-12, giving a 23-hour spring-forward day with only 4 live products
   and ECRS entirely absent; `run_backtest_as` on that pair solves cleanly
   with ECRS availability count 0 and ECRS awards identically 0. This covers
   the mask path and the DST path in one test.
5. **Timezone alias inconsistency.** `as_prices.py` uses `US/Central`;
   `rolling.py` uses `America/Chicago`. Same zone, but the launch-date mask
   boundary must be computed as a Central-local calendar date converted to
   UTC, not a naive UTC midnight. Pick one alias and note it.
6. **`_PRODUCT_LAUNCH` is private.** The mask needs a per-product launch
   lookup. Cleanest fix is promoting it to a public `PRODUCT_LAUNCH` in
   `as_prices.py` (additive, no frozen interface touched) rather than reaching
   into a private name from `as_runner.py`.
7. **Product row order.** Pivoting an AS frame yields alphabetical columns
   (`ECRS, NONSPIN, REG_DOWN, REG_UP, RRS`), which is NOT `DEFAULT_AS_PRODUCTS`
   order (`REG_UP, REG_DOWN, RRS, ECRS, NONSPIN`). Index by
   `pivot[product.name]` in the products tuple's order, matching the existing
   helper at `tests/test_as_optimizer_properties.py:46`. Gotcha 3's stable
   JSON ordering follows from the same rule.
8. **`.ports.env` is already dirty** on this branch (`git status` shows
   ` M .ports.env`). Memory `adw-worktree-port-file-cleanup` records this
   recurring five times. Restore or untrack it before the PR.

### Existing Patterns to Follow

- **Clean skip, never error** (`benchmark`, cli.py:389-394): collect the
  missing inputs, `typer.echo` a notice naming the command to run, continue,
  exit 0. AC-6 asks for exactly this shape.
- **Corridor assertions over goldens** for market-data-derived values
  (`tests/test_backtest_integration.py:82`, `tests/test_benchmarks.py:145`).
- **Determinism test excludes `solve_time_seconds`**
  (`tests/test_backtest_integration.py:128`) and documents why in the
  docstring. AC-8 is the same test one level up.
- **Pure analytics, CLI owns I/O** (`benchmarks.py` module docstring).
- **Injectable optimizer parameter** on every backtest entry point, so the M4
  Rust engine drops in. `run_backtest_as`'s frozen signature already carries
  it; test it with a stub the way
  `tests/test_backtest_integration.py:154` does.
- **Config table helpers** (`_rolling_config_from_settings`, cli.py:97) fall
  back to the dataclass defaults rather than requiring the table. Mirror this
  for `[ancillary]`.
- **Fixture-only tests, no network**; seed a tmp cache dir via the data
  layer's own `_cache_path`.

## Recommendations

1. **Merge order:** no pre-merge needed. The branch is current with
   `origin/main` (`d2c0d8f`), which contains both M3a and M3b. Confirmed by
   the fixtures and modules being present and importable.

2. **`run_backtest_as` shape.** Align, solve once, score with the shared code
   path, roll up per product:

   ```
   pivot = as_prices_df.pivot(index="interval_start_utc", columns="product", values="price")
   pivot = pivot.reindex(prices_df["interval_start_utc"])         # align to the energy timeline
   for each product in `products` (that order):
       available = pivot[name].notna()                            # missing column -> all False
       expected  = interval >= launch_utc(name)                   # PRODUCT_LAUNCH, Central date -> UTC
       raise listing (product, interval) where expected & ~available
       as_prices[p]    = pivot[name].fillna(0.0)
       as_available[p] = available
   as_dispatch = optimizer(prices, as_prices, as_available, dt_hours, battery, products)
   energy = metrics_from_dispatch(location, prices_df, battery,
                                  replace(as_dispatch.dispatch,
                                          objective_value=as_dispatch.energy_revenue_usd),
                                  solve_time_seconds)
   revenue_by_product = pd.Series((as_prices * awards_mw * dt).sum(axis=1), index=names)
   award_mw_hours     = pd.Series((awards_mw * dt).sum(axis=1),             index=names)
   ```

   Build the `pd.Series` indexes from `[p.name for p in products]` so the
   order is the products tuple's, satisfying gotcha 3.

3. **Resolve AC-5 by doing both.** Have `--ancillary` run the existing
   energy-only pipeline completely unchanged (same files, same content, same
   PNGs) and *additionally* solve the co-opt and write
   `{location}_metrics_{mode}_ancillary.json`. This satisfies both readings of
   AC-5, makes the byte-identity test a trivial file-hash comparison, and
   gives AC-3's dominance check both numbers from one invocation. The extra
   energy-only solve costs about 0.02 s.

4. **Rolling guard (AC-7).** Check `--ancillary and mode == rolling` at the
   top of `backtest`, before any file I/O, and `raise typer.Exit(code=1)`
   after echoing a message that names M3's perfect-foresight-only scope.
   Guard the config-driven `[ancillary].enabled` path identically.

5. **Benchmark uplift leg.** Read both `{loc}_metrics_perfect.json` and
   `{loc}_metrics_perfect_ancillary.json`. If either is absent, echo a notice
   naming both and skip (AC-6). If present, compare the `daily_revenue` key
   ranges for equality before dividing (gotcha 4), then emit
   `{"as_uplift": ..., "revenue_mix": {...}}` under the hub. Keep both
   computations in `analytics/benchmarks.py` as pure functions.

6. **Test plan**, one file, mapped to criteria:

   | Test | Criteria |
   | --- | --- |
   | doctored July frame, one REG_UP hour deleted, raises naming product + ISO timestamp | 1 |
   | March 12 energy + AS pair: solves, ECRS availability 0, ECRS awards 0 | 1 (mask), 9 |
   | decomposition + all M1 fields present and finite on July | 2 |
   | co-opt total >= `run_backtest` total, same battery/fixture | 3 |
   | uplift in [1.0, 8.0] (actual 2.77) | 4 |
   | CLI `--ancillary`: ancillary JSON has the full block; energy-only files hash-equal to a no-flag run | 5 |
   | CLI benchmark with and without the ancillary file present | 6 |
   | CLI `--ancillary --mode rolling` exit code nonzero, message mentions M3 | 7 |
   | two runs, JSON equal after dropping `solve_time_seconds` | 8 |
   | stub optimizer flows through unchanged (M4 seam) | contract |

7. **README.** New "## M3 results: ancillary service co-optimization" section
   after the M2 section, carrying the 2.77x headline, the mix table above, the
   "Modeling assumptions" paragraph copied verbatim from the master
   (`specs/M3_ancillary_services.md`, lines 156-165), and a note that the
   co-optimized energy leg falls to $567k because capacity outbids arbitrage.
   Rewrite README.md:9-18 so it says energy-only understates, capacity-only
   co-opt overstates, and the honest number lies between. Annualized figures
   must reuse `metrics_from_dispatch`'s actual-window-hours convention; never
   write 8760 as a divisor.

8. **Before finalizing:** `git status` and restore `.ports.env` (memory
   `adw-worktree-port-file-cleanup`, five prior occurrences).

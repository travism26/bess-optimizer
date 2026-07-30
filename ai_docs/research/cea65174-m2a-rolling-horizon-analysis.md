# Research: M2a Rolling-Horizon Dispatch

## Metadata

adw_id: `cea65174`
prompt: `specs/M2a_rolling_horizon.md`
date: `2026-07-30`

## Executive Summary

M2a is an additive slice: one new module (`src/bess/backtest/rolling.py`), a
`--mode` flag plus a `mode` block in the metrics JSON on the CLI side, a
`[rolling]` section in `config.toml`, and two new test files. Nothing frozen
changes, and the spec is explicit that `RollingConfig` may **not** go in
`models.py` (in-scope item 4 forbids touching it), so both the config
dataclass and the runner live in the new module. Baseline gates are green
today: ruff clean, mypy clean on 17 source files, 42 tests passing, 1
deselected (`manual`).

I prototyped `run_backtest_rolling` end to end against the real fixtures and
found three things the build phase needs to know before it writes code:

1. **AC-7's DST case has an undefined hole that crashes the solver.** The
   spec's persistence rule covers a 23/25-hour *lookahead* day but not a
   23-hour *source* day. Commit day 2023-03-12 has local hours
   `0,1,3,4,...,23` (no hour 2), so mapping it onto the 24-hour lookahead day
   2023-03-13 leaves local hour 2 unmapped. My first prototype emitted `NaN`
   there and HiGHS returned status `Unknown`, which `optimize_dispatch` turns
   into `RuntimeError: HiGHS did not reach an optimal solution`. A synthetic
   730-day run died on exactly this. The build must pick a fill rule (nearest
   local hour is what I prototyped) and document it. The mirror-image
   ambiguity also exists: a 25-hour source day has two prices for local hour 1
   (2023-11-05 gives 21.68 and 24.98), and the spec does not say which one
   maps onto a 24-hour lookahead day.
2. **AC-2 and AC-5 pass trivially on the July fixture.** The perfect-foresight
   July optimum is exactly day-separable: M1's SoC is 0.0 at every single
   Central day boundary. So rolling at `lookahead_days=1` reproduces M1
   revenue to the last bit ($970,937.1499523435, delta 0.0) for **both**
   forecast variants. The equivalence golden (AC-2) and dominance (AC-5) are
   therefore satisfied by a rolling implementation that ignores the forecast
   entirely. The two-day golden (AC-1) is the only acceptance criterion that
   actually discriminates persistence from perfect. This also means M2b's
   headline foresight capture rate on this fixture is 1.0000, which is worth
   flagging now rather than discovering in T5.
3. **The runtime budget is not close to binding.** My 730-day synthetic
   rolling run (17,520 intervals, 730 windows, persistence) finished in
   **0.63 s** wall, 0.24 s of it inside HiGHS, against a 60-second budget. A
   single full-horizon M1 solve over the same array takes 0.19 s.

All three goldens reproduce numerically: AC-1 perfect = 275.0, AC-1
persistence = 0.0, M1 cross-check = 275.0, AC-2 delta = 0.0.

## Existing Architecture

### Relevant Documentation Found

| Document | Contents relevant to M2a |
| -------- | ------------------------ |
| `specs/M2_rolling_and_benchmarks.md` | Master, wins on conflict. Frozen `RollingConfig` / `run_backtest_rolling` signatures, the "Rolling mechanics" numbered rules, the `mode` JSON block, the `[rolling]` config keys, gotchas (DST, zero-profit ties, annualization, wall-time determinism). |
| `specs/M2a_rolling_horizon.md` | The task spec. 10 acceptance criteria, in-scope list naming the exact files, out-of-scope list (benchmarks, capture rates, sweeps, plot changes are all M2b). |
| `specs/M2b_benchmarks.md` | Downstream sibling. Consumes rolling results for the capture rate; T5 depends on T4 merged. |
| `specs/M1_python_core.md` | Frozen `BacktestResult`, the canonical price schema, the LP formulation rolling re-solves per window. |
| `specs/TASKS.md` | T4 is this task. Notes the headline goldens: "two-day foresight case (perfect 275.0 vs persistence 0.0, exact) and the M1 equivalence test". |
| `CLAUDE.md` | Repo rules: frozen interfaces, optimizer purity, gridstatus confined to `data/prices.py`, no network in tests, no em-dashes, no AI-attribution trailer. |
| `specs/review_issues/review-27b2b22d.md` | The one open tech-debt item: `solve_time_seconds` is embedded in the on-disk metrics JSON and is not documented as the intentionally non-deterministic field. Master gotcha 4 assigns closing this to M2 (M2b's AC list names it explicitly). |
| `ai_docs/memory/entries/lesson-backtest-shared-solve-for-metrics-and-plots.md` | Directly applicable: the `solve_dispatch` / `metrics_from_dispatch` split exists so the CLI solves once and reuses the dispatch for plots. Rolling should mirror it. |
| `ai_docs/memory/entries/lesson-lp-optimizer-degeneracy-in-tests.md` | LP optima are non-unique. Assert net dispatch and revenue, not per-interval vertex values. |
| `ai_docs/memory/entries/lesson-determinism-tests-exclude-wallclock-fields.md` | AC-10's determinism comparison must exclude the wall-time field, exactly as `tests/test_backtest_integration.py` already does. |
| `ai_docs/memory/entries/pitfall-adw-worktree-port-file-cleanup.md` | `.ports.env` is dirty in this worktree right now (`M .ports.env`). Restore it before finalizing; it has leaked into three prior runs. |
| `app_docs/feature-27b2b22d-backtest-cli-plots.md` | The documentation format the document phase will mirror. |

### Component Map

```
config.toml  [rolling] lookahead_days, forecast        <- NEW section
     |
     v
bess/cli.py  backtest --mode perfect|rolling           <- MODIFIED
     |            _metrics_dict() gains the mode block  <- MODIFIED
     |            _run_location() branches on mode      <- MODIFIED
     |
     +--> bess/data/prices.py  fetch_da_prices()        (unchanged)
     |          canonical UTC frame, one location
     |
     +--> bess/backtest/runner.py                       (unchanged)
     |          solve_dispatch  -> DispatchResult, secs
     |          metrics_from_dispatch -> BacktestResult   <- REUSED by rolling
     |          run_backtest (frozen)
     |
     +--> bess/backtest/rolling.py                      <- NEW
                RollingConfig (frozen dataclass, lives here, not models.py)
                window construction on America/Chicago days
                persistence | perfect forecast for the lookahead days
                per-window optimizer call, commit day d, carry SoC
                stitch committed arrays -> synthetic DispatchResult
                        -> metrics_from_dispatch -> BacktestResult
                     |
                     v
                bess/optimizer/lp.py optimize_dispatch  (unchanged, injected)
```

### Key Files and Modules

| File | Purpose for M2a |
| ---- | --------------- |
| `src/bess/backtest/rolling.py` | New. All M2a library code. |
| `src/bess/backtest/runner.py` | Read-only dependency. `metrics_from_dispatch(location, prices_df, battery, dispatch, solve_time_seconds)` is the "do not re-implement metrics" seam (gotcha 3). `_price_series_and_dt` and `_single_location` are private but reusable. |
| `src/bess/models.py` | Read-only. `BatterySpec` is frozen, so per-window initial SoC requires constructing a new `BatterySpec` (or `dataclasses.replace`) each iteration. |
| `src/bess/optimizer/lp.py` | Read-only. Note it **raises** `RuntimeError` on any non-optimal status rather than returning one, which shapes how AC-3 must be tested. |
| `src/bess/cli.py` | `backtest()`, `_run_location()`, `_metrics_dict()`, `_comparison_row()` all touched. |
| `src/bess/data/prices.py` | Read-only. `_canonicalize` is what the DST tests will call on the raw fixtures (as `tests/test_data.py` already does). |
| `tests/fixtures/hb_north_2023_07.parquet` | 744 rows, Central 2023-07-01 00:00 through 2023-07-31 23:00, so exactly 31 clean 24-hour Central days. |
| `tests/fixtures/hb_north_2023_03_12_raw.parquet` | 23 raw rows, **single day only**. Canonicalizes to 23 rows, local hours 0,1,3..23. |
| `tests/fixtures/hb_north_2023_11_05_raw.parquet` | 25 raw rows, **single day only**. Canonicalizes to 25 rows, local hours 0,1,1,2..23. |

## Affected Areas

### Files That Will Need Changes

| File | Change |
| ---- | ------ |
| `src/bess/backtest/rolling.py` | New module: `RollingConfig`, `run_backtest_rolling`, and (recommended) a non-frozen `solve_rolling` helper returning the stitched committed `DispatchResult` plus summed solve seconds. |
| `src/bess/cli.py` | `--mode` option on `backtest`; read `[rolling]` when mode is rolling; build the `mode` block; route `_run_location` through rolling when selected so the dispatch-detail plot still gets a dispatch. |
| `config.toml` | Add the `[rolling]` table with `lookahead_days = 1` and `forecast = "persistence"`. |
| `tests/test_rolling_golden.py` | New: AC-1 (two-day golden, both variants, plus the M1 cross-check) and AC-2 (equivalence at `lookahead_days >= 31`). |
| `tests/test_rolling_properties.py` | New: AC-3 through AC-8 and AC-10. |
| `tests/test_backtest_integration.py` | Optional but likely: AC-9's CLI test could live here next to the existing CliRunner tests, or in the new properties file. Pick one and be consistent. |
| `specs/TASKS.md` | T4 checkbox, PR number, and log row at finalize time. |
| `README.md` | Not M2a. The M2 results section is M2b's deliverable. |

### Dependencies

**Rolling depends on:** `bess.models` (`BatterySpec`, `DispatchResult`,
`BacktestResult`), `bess.optimizer.lp.optimize_dispatch` (default argument
only), `bess.backtest.runner.metrics_from_dispatch`, pandas, numpy. No new
third-party packages: `zoneinfo` is stdlib and pandas already handles the
`US/Central` conversion used in `data/prices.py`.

**Depends on rolling:** `bess.cli` (this slice) and M2b's benchmark command
(next slice, which divides rolling revenue by perfect revenue). Keeping
`run_backtest_rolling`'s signature exactly as the master states matters
because T5 calls it directly.

### Integration Points

1. **`metrics_from_dispatch`** is the integration point that makes perfect and
   rolling comparable field by field. It reads `dispatch.objective_value` as
   total revenue, so the stitched committed `DispatchResult` must carry
   recomputed revenue (`sum(price * (discharge - charge) * dt)`) in that
   field, not a sum of per-window objectives (window objectives include
   lookahead-day revenue and would badly overstate the total).
2. **The injected optimizer seam.** Each window calls
   `optimizer(prices, dt_hours, battery_with_carried_soc)`. This is the exact
   contract the M4 Rust engine must satisfy, and `tests/test_backtest_integration.py`
   already demonstrates the stub-optimizer test pattern to copy.
3. **Timezone boundary.** `CLAUDE.md` says timezone logic lives in
   `data/prices.py`. Rolling necessarily converts UTC to `US/Central` to find
   market days. That is unavoidable for M2 (the master mandates local market
   days) but should be a single, named, documented helper in `rolling.py`, not
   scattered. Use the same `US/Central` string `data/prices.py` uses;
   `America/Chicago` in the master is the same zone but a different literal.

## Impact Analysis

### Scope of Change

Small and additive. About 150 to 200 lines of new library code, roughly 30
lines of CLI churn, two new test files. No frozen interface is touched, no
existing test should change behavior, no dependency changes.

### Risks and Considerations

**Risk 1 (highest): the DST persistence hole is undefined and crashes.**
Confirmed empirically. Canonical local hours for the two DST days:

```
2023-03-12 (23h): 0 1 3 4 5 ... 23        <- no local hour 2
2023-11-05 (25h): 0 1 1 2 3 ... 23        <- local hour 1 twice, prices 21.68 and 24.98
```

Two cases the spec does not cover:

- 23-hour source day mapped onto a 24- or 25-hour lookahead day: local hour 2
  has no source price. My prototype produced `NaN`, HiGHS returned `Unknown`,
  and the run died. In a 730-day synthetic backtest this fires once per year.
- 25-hour source day mapped onto a 24-hour lookahead day: two candidate prices
  for local hour 1.

Recommended resolution: build the hour map with first-occurrence-wins (which
resolves the 25-hour source ambiguity deterministically), then fill any
unmapped target hour from the nearest available source hour. Document both
rules in the `run_backtest_rolling` docstring, and assert them in a dedicated
DST test. Whatever rule is chosen, the invariant to guard is that the window
price vector contains no `NaN`.

**Risk 2: the July fixture cannot distinguish a correct forecast from no
forecast.** M1's committed SoC is exactly 0.0 at all 31 Central day
boundaries, so a 2-hour battery never carries energy overnight. Measured
capture rates on the fixture month:

| Battery | M1 perfect | rolling perfect (la=1) | rolling persistence (la=1) |
| ------- | ---------- | ---------------------- | -------------------------- |
| 100 MW / 200 MWh (default) | $970,937 | 1.0000 | 1.0000 |
| 100 MW / 800 MWh | $2,459,521 | 1.0000 | 0.9997 |
| 100 MW / 2400 MWh | $2,582,972 | 0.9975 | 0.9936 |
| 100 MW / 200 MWh, lossless | $1,086,383 | 1.0000 | 0.9983 |

Consequences: AC-2 and AC-5 do not discriminate, so do not treat them as
proof the forecast branch works. AC-1 is the real test. Also worth telling the
user now: the M2b headline capture rate is 1.0000 on this fixture, so the
blog-ready number needs either a longer window (winter volatility, a full
2023-2024 fetch) or an explicit note that a 2-hour battery on a calm summer
month has nothing to gain from foresight.

**Risk 3: the metrics `mode` block shape is ambiguous.** The master says the
JSON "gains a `mode` block: `{"mode": "rolling", "lookahead_days": N,
"forecast": ...}`". That reads either as a nested `"mode"` key holding that
object, or as those keys merged at the top level. AC-9 ("containing the `mode`
block with lookahead_days and forecast echoed") is satisfied by both. Nesting
keeps the addition purely additive and keeps `_comparison_row` from growing
mode-specific keys, at the cost of a literal `metrics["mode"]["mode"]`. Pick
one, state it in a docstring, and keep `comparison.json` consistent with
`{location}_metrics.json` (the existing CLI test asserts they match field for
field apart from `daily_revenue`).

**Risk 4: AC-3 cannot be triggered by the real optimizer.**
`optimize_dispatch` raises `RuntimeError` on any non-optimal HiGHS status
before returning, so `result.solver_status` is always `"optimal"` in practice.
Rolling still needs its own status check for injected optimizers, and AC-3
requires the window's date in the message. Test it with a stub optimizer that
returns `solver_status="infeasible"` on the Nth window and assert the date
string appears. Consider also wrapping the optimizer call so a raised
`RuntimeError` gets the window date attached.

**Risk 5: `BatterySpec` is frozen.** Per-window SoC carry means constructing a
new `BatterySpec` per window (or `dataclasses.replace`). Do not attempt to
mutate. `max_cycles_per_day` must be carried through unchanged even though the
optimizer ignores it.

**Risk 6: `simultaneous_hours` on the committed series.** The threshold
constant `_SIMULTANEOUS_THRESHOLD_MW = 1e-3` is private to `optimizer/lp.py`,
and per-window counts include lookahead intervals that are never committed, so
they cannot simply be summed. Recount from the stitched committed arrays.
Either import the private constant (it is a real coupling, but honest) or
define a local constant with a comment pointing at `lp.py`; do not silently
pick a different threshold.

**Risk 7: daily_revenue stays UTC-bucketed while windows are Central days.**
`metrics_from_dispatch` groups by UTC calendar date and the July fixture
therefore yields 32 buckets for 31 Central days. That is documented M1c
behavior and both modes share it, so comparability holds, but a reader
comparing "31 commit windows" to "32 daily_revenue rows" will trip. Say so in
the docstring.

**Risk 8: zero-profit ties.** Master gotcha 2. The goldens use lossy charge
efficiency so the optimum is strict. Do not add tie-breaking to library code,
and follow the remembered degeneracy lesson: assert net dispatch and revenue,
not per-interval gross values.

**Risk 9: `.ports.env` is already dirty** in this worktree. Restore or untrack
before the PR; it has leaked into three prior runs.

### Existing Patterns to Follow

- **Split solve from scoring.** `runner.py` exposes `solve_dispatch` plus
  `metrics_from_dispatch` under the frozen `run_backtest`. Mirror it:
  `solve_rolling(...) -> tuple[DispatchResult, float]` under the frozen
  `run_backtest_rolling`, so the CLI can plot the committed dispatch without
  re-running every window.
- **Module docstrings carry the "why".** Every module in `src/bess` opens with
  a docstring naming the spec section it implements and the gotchas it
  handles. The DoD explicitly requires the commit/carry rule and end-of-range
  truncation in the `run_backtest_rolling` docstring.
- **Tests are named after acceptance criteria** and their docstrings start
  with "AC-N:". Copy that.
- **Private helpers are imported by tests** where needed (`_canonicalize`,
  `_cache_path`, `_metrics_dict`), so the DST tests calling `_canonicalize` on
  the raw fixtures is an established pattern, not a new one.
- **AST-based guards** for import confinement (remembered lesson). Nothing new
  is required here, but if a guard is added, parse the AST rather than
  grepping.
- **No network in tests.** The autouse `block_network` fixture covers this;
  every new test must run from fixtures or synthetic frames.

## Recommendations

### 1. Module shape

```python
# src/bess/backtest/rolling.py
_CENTRAL_TZ = "US/Central"
_FORECASTS = ("persistence", "perfect")

@dataclass(frozen=True)
class RollingConfig:
    lookahead_days: int = 1
    forecast: str = "persistence"

def solve_rolling(prices_df, battery, config, optimizer=optimize_dispatch
                  ) -> tuple[DispatchResult, float]: ...

def run_backtest_rolling(prices_df, battery, config, optimizer=optimize_dispatch
                         ) -> BacktestResult:
    dispatch, solve_seconds = solve_rolling(...)
    return metrics_from_dispatch(location, prices_df, battery, dispatch, solve_seconds)
```

`RollingConfig` stays in `rolling.py`: M2a in-scope item 4 forbids changes to
`models.py`. Validate `config.forecast` against `_FORECASTS` with a clear
`ValueError`; the master's prose says "behind one enum" but the frozen
signature says `str`, and the frozen signature wins.

### 2. Window construction

Compute the Central local day per row once, then slice contiguous blocks (the
canonical frame is sorted and gap-free, so day blocks are contiguous and
`np.flatnonzero` on the day-change boundaries is enough). Never assume 24 rows.
The lookahead concatenates the next `lookahead_days` day blocks and stops at
the end of the frame for both forecast variants. Commit `len(day_block)`
intervals, carry `soc_mwh[len(day_block) - 1]`.

### 3. Persistence mapping

Map by local hour-of-day, never by array position. Build
`{local_hour: price}` from the commit day with first-occurrence-wins, then
index the lookahead day's local hours through it, filling any missing hour
from the nearest available source hour. Assert no `NaN` before calling the
optimizer, so a future mapping bug fails with a clear message instead of a
HiGHS `Unknown` status.

### 4. Stitching

Concatenate committed `charge_mw`, `discharge_mw`, `soc_mwh`; set
`objective_value` to revenue recomputed from the committed series against the
full `prices_df`; set `solver_status="optimal"`; recount
`simultaneous_hours`; sum per-window solve seconds into
`solve_time_seconds`. Then hand it to `metrics_from_dispatch` unchanged. This
is what makes AC-6 (committed series integrity) and gotcha 3 (do not
re-implement metrics) both hold.

### 5. Test construction notes

- **AC-1** needs a canonical 48-row frame starting at Central midnight. Verified:
  perfect = 275.0, persistence = 0.0, M1 cross-check = 275.0, all exact.
- **AC-2** at `lookahead_days=31` gives delta 0.0 against M1 on the July
  fixture. It will also pass at `lookahead_days=1`, so keep the spec's
  `>= 31` and do not read a pass as evidence the lookahead works.
- **AC-7** cannot be built from the raw DST fixtures alone: each contains a
  single day (23 and 25 rows). To get a 25-hour *lookahead* day you need a
  commit day of 2023-11-04, which is not in the fixture, so synthesize the
  neighbouring day at chosen prices and concatenate it with the canonicalized
  fixture day. Same for the 2023-03-12 spring-forward case, which is also the
  one that exercises the undefined-hole fix.
- **AC-8** is comfortable: 0.63 s wall, 0.24 s in HiGHS, for 730 days and
  17,520 intervals. Generate the synthetic frame with a tz-aware
  `pd.date_range(..., tz="US/Central", freq="h")` so it contains real DST
  transitions, which is exactly what caught the hole above. Keep the assertion
  loose (under 60 s) so CI hardware variance does not flake it.
- **AC-10** must exclude the wall-time field from the comparison, exactly as
  `test_backtest_metrics_json_is_deterministic_across_runs` already does.

### 6. CLI

Add `--mode` as a `str` option defaulting to `"perfect"` and validate it, or
use a `str` enum for Typer's built-in choice validation; either is fine as
long as the default preserves M1 behavior byte for byte. Read `[rolling]` only
when mode is rolling, with the master's defaults as fallbacks so a config
without the section still works. Thread the mode through `_run_location` so
the dispatch-detail plot renders committed rolling dispatch when rolling is
selected. Note `bess plot` has no `--mode` in scope; leave it on perfect.

Adding `[rolling]` to `config.toml` must go **after** all existing top-level
keys (TOML puts every key following a table header inside that table). The
current file has all scalars first, so appending is safe.

### 7. Out of scope, resist the pull

No capture rate, no TB2/TB4, no sweeps, no README results section, no plot
changes. Those are T5. The one gray area is master gotcha 4's "document the
wall-time field where it is written", which closes the open T3 review note;
M2b's acceptance criteria claim it, but M2a is already editing `_metrics_dict`
and a one-line docstring there is harmless and low-risk.

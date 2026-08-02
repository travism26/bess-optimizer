# Repo PR Study Guide: M1-M3

Prepared 2026-08-01 for Travis. Covers the 8 merged PRs that built bess-optimizer through
M3 (PRs #1, #2, #4, #5, #7, #8, #9, #10), built almost entirely through the ADW agentic
pipeline and merged fast. This guide is for going back and actually learning what shipped,
plus setting up a lighter-weight ritual so future PRs get read this deeply the first time.

Sources used for every PR below: `gh pr diff <n>` and `gh pr view <n>`, the matching spec
in `specs/`, the review notes in `specs/review_issues/` (present for 7 of 8 PRs, see the
PR #9 card), the pre-implementation research docs in `ai_docs/research/`, the codified
lessons in `ai_docs/memory/entries/`, and the current source under `src/bess/`.

## TLDR

- The two deep-dive PRs are #2 (M1b LP optimizer, the formulation itself) and #9 (M3b AS
  co-optimizer, the same formulation extended with per-product capacity constraints); both
  reward slow reading of the actual LP construction, not just the diff summary.
- Three domain rules recur across almost every PR and are worth memorizing once: DST days
  are 23 or 25 hours, never 24, and every timezone conversion happens at the data-ingest
  boundary and nowhere else; negative and zero prices are valid data, never clipped; LP
  optima are frequently non-unique (degenerate), so tests and reviewers must assert
  aggregate revenue and constraint residuals, never a specific per-interval or per-product
  dispatch value.
- Two engineering patterns were invented once and then reused for the rest of the project:
  the shared-solve pattern (`solve_dispatch`/`metrics_from_dispatch` split, born in PR #4,
  reused verbatim by PR #5's rolling engine and PR #10's AS backtest) and mode-qualified
  metrics filenames (born as a bug fix in PR #7, extended again in PR #10).
- Total study time for all 8 PRs is about 5 hours (300 minutes), front-loaded on PRs #2 and
  #9; the four data-layer and plumbing PRs (#1, #7, #8, #10) go faster once the patterns
  from #2/#4/#5 are internalized.
- The proposed going-forward ritual runs the installed `explain-diff-html` skill on every
  PR before the human reads the raw diff, and gates merge on passing its 5-question quiz
  cold; a single-line addition to `specs/TASKS.md`'s "How to run a task" section is proposed
  at the end of this doc (not applied, per instructions).

## How to use this document

Each PR card lists the spec and review-issue files it pairs with, 2-3 concepts worth
understanding cold, 3-5 comprehension questions with answers in collapsed `<details>`
blocks (try to answer before expanding), and a standalone study time estimate. Cards are in
merge order because later PRs assume the patterns from earlier ones. The recommended study
order and total time are in their own section after the cards; the review ritual is last.

---

## PR #1: M1a, Data Layer

**Spec:** `specs/M1a_data_layer.md` (master: `specs/M1_python_core.md`)
**Review:** `specs/review_issues/review-3c648beb.md` (PASSED, 4 tech-debt/skippable issues)
**Analysis:** `ai_docs/research/3c648beb-m1a-data-layer-analysis.md`
**Size:** +963/-19, merged 2026-07-29
**Density tier:** foundational domain rules (medium-high)

### Concepts worth knowing cold

1. **DST is a first-class concern, not an edge case.** ERCOT publishes in prevailing
   Central Time; a spring-forward day has 23 hours, a fall-back day has 25. The rule
   enforced throughout the codebase: convert to UTC immediately at the ingest boundary
   (`src/bess/data/prices.py`) and never build an hourly grid, a gap check, or a groupby
   assuming 24 rows per calendar day. AC-2 requires proving this from two tiny committed
   raw-format samples (`tests/fixtures/hb_north_2023_03_12_raw.parquet`,
   `..._11_05_raw.parquet`), not from the network, because the fixture month (July) never
   crosses a transition.
2. **The obvious gridstatus method silently returns nothing for historical data.**
   `Ercot.get_spp(market=DAY_AHEAD_HOURLY)` queries a document list that only retains
   recent postings; for a month like July 2023 it returns an empty DataFrame instead of
   raising. The fix, found during the research phase and used in `_fetch_raw`, is the
   yearly-archive method `Ercot.get_dam_spp(year=2023)`. This same "the obvious method name
   lies" lesson repeats, escalated, in PR #8.
3. **Engineering pattern: the four-piece module.** `_fetch_raw` (the only function allowed
   to touch gridstatus or the network) / `_canonicalize` (pure) / `_validate` (pure, fails
   loudly, never interpolates) / `fetch_da_prices` (orchestrates, caches). This shape,
   plus an AST-parsed (not text-grepped) import-confinement test, is the template every
   later data-layer and optimizer module in this repo copies.

### Comprehension questions

**Q1.** Why does M1a commit two tiny raw-format DST samples instead of deriving the DST
test cases from the committed July fixture or a live fetch?
<details><summary>Answer</summary>
The July fixture doesn't span a DST transition day, and tests may never touch the network
(AC-7), so the only way to prove 23/25-hour handling offline is to capture small
pre-canonicalization raw frames for 2023-03-12 and 2023-11-05 once, during the single
networked build step, and commit them.
</details>

**Q2.** What specifically goes wrong if you call `Ercot.get_spp(..., market=DAY_AHEAD_HOURLY)`
for July 2023, and what's the actual fix used in `_fetch_raw`?
<details><summary>Answer</summary>
It returns an empty DataFrame rather than raising, because the underlying document list
only retains recent postings and no documents match a 2023 date. The fix is
`Ercot.get_dam_spp(year=2023)`, the yearly historical archive method, filtered to the
requested location afterward.
</details>

**Q3.** Why is `bess.data.prices` the only module in `src/` allowed to import gridstatus,
and how is that enforced?
<details><summary>Answer</summary>
Isolating the volatile third-party surface into one module means an upstream gridstatus
change is a one-function fix (spec gotcha 2). It's enforced by an AST-parsed test (walking
the module's `import`/`import from` statements), not a text grep, so a docstring mentioning
"gridstatus" or "pandas" can't false-positive the guard.
</details>

**Q4.** Why must the expected-hourly-index used for gap detection be built in UTC rather
than Central local time?
<details><summary>Answer</summary>
Building it in Central time would reintroduce exactly the DST bug the spec warns against:
local calendar days are 23 or 25 hours on transition days, so an index built on local dates
would misalign. UTC hours are strictly, uniformly hourly across both transitions.
</details>

**Q5.** What happens to a negative price during canonicalization, and why does that choice
matter for PRs downstream (#2, #9)?
<details><summary>Answer</summary>
It passes through completely unmodified: no clipping, no filtering, no NaN coercion
(AC-5). This matters because PR #2's negative-price golden test and PR #9's
capacity-adequacy economics both depend on negative prices being real, untouched data, not
an artifact that got silently filtered upstream.
</details>

**Study time estimate:** 30 minutes.

---

## PR #2: M1b, LP Dispatch Optimizer

**Spec:** `specs/M1b_optimizer.md` (master: `specs/M1_python_core.md`)
**Review:** `specs/review_issues/review-3b9cf1a9.md` (PASSED, 1 skippable issue)
**Analysis:** `ai_docs/research/3b9cf1a9-m1b-lp-optimizer-analysis.md`
**Size:** +901/-67, merged 2026-07-29
**Density tier:** deep dive (this is the formulation everything else in the project extends)

### Concepts worth knowing cold

1. **The LP formulation itself.** Decision variables per interval `t`: charge `c_t` (MW),
   discharge `d_t` (MW), state of charge `s_t` (MWh, end of interval). Maximize
   `sum_t p_t * (d_t - c_t) * dt` subject to the SoC recursion with split
   charge/discharge efficiency, power bounds, and SoC bounds. There is **deliberately no
   terminal SoC constraint** (`src/bess/optimizer/lp.py:43-47`): with default initial SoC
   of 0, letting the final SoC float free lets the optimizer capture the value of energy
   still stored at the end of the horizon instead of stranding it. A rolling-horizon caller
   (PR #5) is expected to re-solve with a fresh `initial_soc_mwh`, not rely on a terminal
   target here.
2. **Purity as an enforced contract, not a convention.** `optimizer/lp.py` may import only
   `numpy`, `highspy`, and `bess.models` (plus stdlib `logging`), checked by an AST-parsed
   test. This module is the correctness oracle and drop-in target for the future M4 Rust
   port, so it stays arrays-in/arrays-out with zero I/O, zero pandas, zero timezone logic.
   The LP is built as raw CSC/column-wise numpy arrays passed straight into
   `highspy.HighsLp` (`_build_lp`, `src/bess/optimizer/lp.py:107-179`) rather than through
   the incremental `addVariable`/`addConstr` API; that choice is what keeps a T=17,520
   two-year solve to about 0.22s against a 30s budget (the incremental API would mean
   roughly 70,000 Python-level calls into the C++ extension).
3. **LP degeneracy: assert revenue and structure, never a specific vertex.** When multiple
   hours share the same price, any split of charge/discharge across them is equally
   optimal, so a test asserting an exact per-hour schedule can be brittle or simply wrong
   even when the solver is correct. This became a standing project lesson
   (`ai_docs/memory/entries/lesson-lp-optimizer-degeneracy-in-tests.md`) that resurfaces in
   PR #5 (committed SoC on flat-price ties) and PR #9 (per-product revenue attribution).

### Comprehension questions

**Q1.** Why does `optimize_dispatch` deliberately omit a terminal SoC constraint?
<details><summary>Answer</summary>
With the default initial SoC of 0, an unconstrained final SoC lets the optimizer capture
the full value of any energy still stored at the end of the horizon rather than stranding
it as worthless. A rolling-horizon caller is expected to re-solve per window with a fresh
initial SoC rather than rely on a terminal target inside this function
(`src/bess/optimizer/lp.py:43-47`).
</details>

**Q2.** AC-10 asks for a case where the LP charges and discharges in the same interval at a
deeply negative price. Why did the "obvious" construction (one very negative hour buried in
a horizon of zero-price hours) fail to produce that behavior, and what fixed it?
<details><summary>Answer</summary>
With zero-price hours available earlier in the horizon, the LP simply drains the battery
for free before the negative-price hour arrives, so it's empty and clean by the time the
bad price hits, no simultaneity needed. The fix is to put the negative price at `t=0` with
`initial_soc_mwh == energy_mwh` (already full, no opportunity to pre-drain), which makes
burning energy through the round-trip efficiency loss genuinely the profit-maximizing move.
</details>

**Q3.** Why is the LP built as raw column-wise (CSC) numpy arrays passed directly into
`highspy.HighsLp`, instead of using the high-level incremental `addVariable`/`addConstr`
API?
<details><summary>Answer</summary>
The incremental API would require on the order of 70,000 Python-level calls into the
HiGHS C++ extension for a T=17,520 two-year horizon, which is the one plausible way to
blow the 30-second runtime budget. Building the sparse matrix directly with numpy
vectorized operations keeps the same solve to about 0.22 seconds.
</details>

**Q4.** A golden test for the lossy-charge case (`specs/M1b_optimizer.md` AC-3) asserts
total grid draw and total discharge rather than a specific per-hour dispatch. Why?
<details><summary>Answer</summary>
With multiple hours sharing the same price (hours 0-11 all at $10), any split of the
required 2.5 MWh grid draw across those hours is an equally optimal LP vertex, so a
specific per-hour assertion could fail even for a correct solver. Asserting aggregate
totals and the objective value avoids depending on which particular optimal vertex HiGHS
returns.
</details>

**Q5.** What does the hard purity rule permit `optimizer/lp.py` to import, and what does
enforcing it buy the project beyond tidiness?
<details><summary>Answer</summary>
Only `numpy`, `highspy`, and `bess.models` (plus stdlib `logging`). Enforcing it (via an
AST-parsed import test, not source-text grep) keeps this module a pure arrays-in/result-out
function with no I/O, DataFrames, or timezone logic, which is exactly the shape the M4 Rust
port needs to reproduce and the shape `run_backtest`'s injected-optimizer seam depends on.
</details>

**Study time estimate:** 50 minutes. This is the PR to read the actual `_build_lp` source
alongside the master spec's "LP formulation" section, not just the summary.

---

## PR #4: M1c, Backtest, CLI, and Plots

**Spec:** `specs/M1c_backtest_cli.md` (master: `specs/M1_python_core.md`)
**Review:** `specs/review_issues/review-27b2b22d.md` (PASSED, 1 tech-debt issue)
**Analysis:** `ai_docs/research/27b2b22d-m1c-backtest-cli-plots-analysis.md`
**Size:** +1278/-72, merged 2026-07-29 (first attempt, adw `5dbaba17`, failed silently as a
no-op build and was closed as PR #3; the harness gained a no-op guard, commit `a1d9ac5`,
before the successful retry)
**Density tier:** integration, medium (this is where several patterns reused everywhere
downstream are born)

### Concepts worth knowing cold

1. **The shared-solve pattern is born here.** `run_backtest` (frozen) is built on two
   non-frozen helpers, `solve_dispatch` and `metrics_from_dispatch`
   (`src/bess/backtest/runner.py:54,74`), specifically so the CLI can solve the LP once and
   reuse the same `DispatchResult` for both the metrics JSON and the dispatch-detail plot,
   instead of re-solving. PR #5's rolling engine and PR #10's AS backtest both reuse
   `metrics_from_dispatch` directly rather than reimplementing scoring
   (`ai_docs/memory/entries/lesson-backtest-shared-solve-for-metrics-and-plots.md`).
2. **A documented, deliberate choice that overrides the "obvious" answer.**
   `daily_revenue` groups by **UTC** calendar date, not the market's local Central trading
   day, even though the July fixture is Central-day aligned and UTC grouping produces two
   partial edge days (19h and 5h) instead of 31 clean days. The reason, stated directly in
   the docstring (`src/bess/backtest/runner.py:94-98`): this keeps `backtest/runner.py`
   free of any ISO-specific timezone knowledge, which is meant to live only in
   `bess.data.prices`. Worth noting: the pre-implementation research doc actually
   recommended the opposite (Central grouping, for cleaner day boundaries); the build phase
   chose architectural separation of concerns over a locally tidier number.
3. **Determinism versus a genuinely non-deterministic required field.** AC-4 requires
   byte-identical metrics JSON across consecutive runs, but the metrics schema also
   requires `solve_time_seconds` (wall-clock, inherently different every run). The
   resolution, which becomes a standing pattern for every later mode (#5, #7, #10): the
   determinism test explicitly excludes that one field, and the exclusion is documented
   where the field is written, rather than quietly rounding the timer to fake a match.

### Comprehension questions

**Q1.** Why does `run_backtest` internally split into `solve_dispatch` and
`metrics_from_dispatch` instead of being one function, and which two later PRs reuse this
split directly?
<details><summary>Answer</summary>
So the CLI can solve the LP exactly once and reuse the resulting `DispatchResult` for both
the metrics JSON and the dispatch-detail plot. PR #5 (`run_backtest_rolling`, stitching
committed per-window dispatch into a synthetic `DispatchResult`) and PR #10
(`run_backtest_as`, replacing the co-opt result's objective value with the energy leg
before scoring) both feed their results through the same `metrics_from_dispatch` rather
than writing their own metrics logic.
</details>

**Q2.** `daily_revenue` groups by UTC calendar date, which produces a 19-hour and a 5-hour
partial day at the edges of the July fixture. Why wasn't Central local date used instead,
given it would produce 31 clean days?
<details><summary>Answer</summary>
The docstring at `src/bess/backtest/runner.py:94-98` states the reason explicitly: UTC
grouping keeps `backtest/runner.py` free of any ISO-specific timezone knowledge, which the
project confines to `bess.data.prices`. This is a deliberate architectural tradeoff
(cleaner module boundary over a locally tidier day count), not an oversight; the
pre-implementation research actually flagged Central grouping as the more natural read of
the fixture and the build phase chose differently anyway, for good reason.
</details>

**Q3.** AC-4 requires two consecutive backtest runs to produce byte-identical metrics JSON.
The metrics schema also requires `solve_time_seconds`, a wall-clock measurement that
differs every run. How is that contradiction resolved, and does the resolution touch the
actual bytes written to disk?
<details><summary>Answer</summary>
The determinism test compares the JSON with `solve_time_seconds` excluded from the
comparison, and that exclusion is documented in a docstring near where the field is
written. The literal on-disk file is NOT byte-identical run to run (the timing field really
does differ); only the documented deterministic subset is guaranteed to match, and the gap
is stated honestly rather than papered over (e.g. by rounding the timer to force a match).
</details>

**Q4.** Why does `bess backtest` persist a dispatch artifact rather than having `bess plot`
simply re-run the optimizer on demand?
<details><summary>Answer</summary>
The frozen `BacktestResult` carries only `daily_revenue`, not the per-interval
charge/discharge/SoC arrays `plot_dispatch_detail` needs. Re-solving inside `bess plot`
would work but wastes a full re-solve (especially over a multi-year window) and couples the
`plot` command to the optimizer, so `backtest` writes an uncommitted dispatch artifact that
`plot` reads instead.
</details>

**Q5.** What happened to the first attempt at this task (adw `5dbaba17`), and what did the
ADW harness change as a result?
<details><summary>Answer</summary>
It failed silently as a no-op build (opened as PR #3, then closed) and the harness gained a
no-op guard (commit `a1d9ac5`) before the successful retry that became this PR. Worth
remembering as a meta-lesson about the pipeline itself: a "build" phase completing without
error doesn't guarantee it actually built anything.
</details>

**Study time estimate:** 35 minutes.

---

## PR #5: M2a, Rolling-Horizon Dispatch

**Spec:** `specs/M2a_rolling_horizon.md` (master: `specs/M2_rolling_and_benchmarks.md`)
**Review:** `specs/review_issues/review-cea65174.md` (PASSED, 3 tech-debt/skippable issues)
**Analysis:** `ai_docs/research/cea65174-m2a-rolling-horizon-analysis.md`
**Size:** +1420/-32, merged 2026-07-30
**Density tier:** algorithmic, medium-high (real bug hunting happened here, not just wiring)

### Concepts worth knowing cold

1. **Rolling mechanics, and why only one acceptance criterion actually tests them.**
   Each local market day is solved with the real day's prices plus `lookahead_days` of
   forecast, only the commit day is kept, and SoC carries forward into the next window
   (`BatterySpec` is frozen, so this means `dataclasses.replace` per window, not mutation).
   On the July fixture, M1's perfect-foresight optimum happens to be day-separable
   (committed SoC returns to exactly 0.0 at every single Central day boundary), so rolling
   with `lookahead_days=1` reproduces the M1 total to the last bit for **both** persistence
   and perfect forecasting. That means the equivalence and dominance goldens (AC-2, AC-5)
   pass even with a rolling implementation that ignores the forecast entirely; the two-day
   synthetic golden (AC-1: perfect 275.0 vs persistence 0.0) is the only criterion that
   actually discriminates correct persistence-forecast logic from a no-op.
2. **Persistence forecasting maps by local hour-of-day, and a real bug was found doing
   it.** The spec's DST rule only described a 23/25-hour *lookahead* day; research found it
   didn't cover a 23-hour *source* (commit) day. Mapping 2023-03-12 (no local hour 2) onto
   a normal lookahead day left one hour unmapped, producing `NaN`, which made HiGHS return
   status `Unknown`, which made `optimize_dispatch` raise. A synthetic 730-day rolling run
   hit this once per year until the fix (fill any unmapped hour from the nearest available
   source hour) landed
   (`ai_docs/memory/entries/pitfall-dst-local-hour-mapping-both-directions.md`,
   `src/bess/backtest/rolling.py:64-101`).
3. **The shared-solve pattern (PR #4) is applied, not reinvented.** `solve_rolling_dispatch`
   stitches committed per-window arrays into a synthetic `DispatchResult` with
   `objective_value` set to revenue *recomputed from the committed series*, never a sum of
   each window's raw solver objective (which would include never-realized lookahead-day
   revenue), and hands that to the same `metrics_from_dispatch` M1 uses.

### Comprehension questions

**Q1.** Why does the persistence forecast map lookahead-day prices by local hour-of-day
instead of by array position?
<details><summary>Answer</summary>
A spring-forward day shifts every subsequent row's array position by one hour relative to a
normal day, so positional mapping would silently misalign the forecast across a DST
boundary. Mapping by local wall-clock hour keeps the correspondence correct regardless of
row count on either the source or target day (`src/bess/backtest/rolling.py:64-74`).
</details>

**Q2.** What DST bug did research find that the master spec's mechanics section didn't
cover, and what actually broke?
<details><summary>Answer</summary>
The spec's DST rule described only the lookahead/target day being 23 or 25 hours; it said
nothing about the source (commit) day also being a transition day. Mapping the 23-hour
2023-03-12 (no local hour 2) onto a normal 24-hour lookahead day left one target hour
unmapped, which produced a `NaN` price, which made HiGHS return status `Unknown`, which
made `optimize_dispatch` raise `RuntimeError`. A synthetic 730-day rolling backtest hit
this exactly once per year until fixed.
</details>

**Q3.** On the July 2023 fixture, the foresight capture rate comes out to exactly 1.0.
Is that a units or windowing bug?
<details><summary>Answer</summary>
No. M1's perfect-foresight optimal dispatch on this specific fixture and battery is
day-separable (committed SoC returns to exactly 0.0 at every Central day boundary), so a
one-day-lookahead operator loses nothing relative to full foresight. It's a property of
this particular month and 2-hour battery, not a general result; a 4-hour duration or lower
round-trip efficiency on the same fixture does show capture rates below 1.0
(`ai_docs/memory/entries/lesson-capture-rate-fixture-can-equal-one.md`).
</details>

**Q4.** Why does `run_backtest_rolling` route through the same `metrics_from_dispatch`
function M1 uses, instead of computing rolling-specific metrics directly?
<details><summary>Answer</summary>
To guarantee perfect-mode and rolling-mode results are comparable field by field using
literally the same scoring code path (the spec's "do not re-implement metrics" gotcha),
rather than risking a second implementation that could silently disagree, especially on
DST-affected days where a second day-slicing implementation is exactly the kind of thing
that drifts.
</details>

**Q5.** Why is the stitched dispatch's `objective_value` set to revenue recomputed from the
committed series, rather than the sum of each window's own solver objective?
<details><summary>Answer</summary>
Each window's raw objective includes revenue from the lookahead days, which are solved for
but never actually committed or realized. Summing window objectives would badly overstate
total revenue; recomputing from only the committed (prices, charge, discharge) series
scores exactly what was dispatched.
</details>

**Study time estimate:** 45 minutes.

---

## PR #7: M2b, Benchmarks and Parameter Sweeps

**Spec:** `specs/M2b_benchmarks.md` (master: `specs/M2_rolling_and_benchmarks.md`)
**Review:** `specs/review_issues/review-325296bb.md` (PASSED, 1 skippable issue)
**Analysis:** `ai_docs/research/325296bb-m2b-benchmarks-sweeps-analysis.md`
**Size:** +1546/-25, merged 2026-07-31 (first attempt, adw `cbd77524`, failed and was closed
as PR #6, superseded by this run)
**Density tier:** lightest of the eight, but contains a real data-corruption bug and fix

### Concepts worth knowing cold

1. **A real bug: two modes silently overwrote each other's output.** Before this PR,
   `bess backtest` wrote both perfect-mode and rolling-mode metrics to the same unqualified
   `{location}_metrics.json`, so running one mode after the other for the same location
   silently clobbered the first mode's file. This blocked the capture-rate feature, which
   needs both files present simultaneously. Fixed additively: the original filename keeps
   being written unchanged (so two already-committed tests asserting it stay green), and a
   new mode-qualified `{location}_metrics_{mode}.json` is written alongside it
   (`ai_docs/memory/entries/pitfall-metrics-json-unqualified-filename-collision.md`). This
   pattern gets extended a third level in PR #10.
2. **TBk benchmarks must reuse the day-slicing helper, not reimplement it.** TBk (the
   sum of the k highest hourly prices minus the k lowest, per local market day) is defined
   on local market days, exactly like rolling windows. `analytics/benchmarks.py` imports
   `_local_market_day`/`_day_blocks` from `backtest/rolling.py` rather than writing a fresh
   `groupby(dt.date)`, because a second independent implementation would silently disagree
   with the first on DST transition days.
3. **A documented, deliberate unit mismatch.** The efficiency sweep splits round-trip
   efficiency as `sqrt` per side (0.86 round-trip -> 0.9273618... per side), which is
   subtly different from the default config's literal `0.927`. This produces a real
   ~$500 revenue difference between the sweep's "0.86" data point and the README's headline
   number; the convention is documented in the sweep JSON rather than silently reconciled
   to match.

### Comprehension questions

**Q1.** What data-corruption bug did this PR's research phase discover in `bess backtest`,
and how was it fixed without breaking two already-passing tests?
<details><summary>Answer</summary>
Perfect-mode and rolling-mode runs for the same location both wrote to the same unqualified
`{location}_metrics.json`, so the second run silently overwrote the first mode's results,
making it impossible for both files to exist at once (which capture-rate calculation
requires). Fixed additively: keep writing the existing unqualified filename exactly as
before, and also write a new `{location}_metrics_{mode}.json` alongside it.
</details>

**Q2.** Why must TBk reuse `backtest/rolling.py`'s `_local_market_day`/`_day_blocks` helpers
instead of a fresh `groupby(interval_start_utc.dt.date)`?
<details><summary>Answer</summary>
TBk is defined on local market days, and a UTC-date groupby would silently disagree with
the rolling engine's local-day definition on DST transition days, the same class of bug
PR #5 already had to hunt down once. Reusing the single source of truth keeps both metrics
interpreting "one market day" identically.
</details>

**Q3.** The sweep's 0.86-round-trip-efficiency data point reports different revenue than
the config default (0.927 per side). Is that a bug?
<details><summary>Answer</summary>
No. The default config sets `charge_eff = discharge_eff = 0.927` directly, which
approximates but is not exactly `sqrt(0.86) = 0.9273618...`. The sweep derives its per-side
efficiency by literally taking the square root of each swept round-trip value, producing a
real (if small) revenue difference documented in the sweep JSON's convention note, not
quietly reconciled against the README headline.
</details>

**Q4.** Why does the capture rate on the July fixture read as exactly 1.0 again here (as it
did in PR #5), and what does that mean for the README headline?
<details><summary>Answer</summary>
Confirmed again at scale: the July fixture's perfect-foresight optimum is day-separable, so
a 1-day-lookahead rolling backtest matches perfect-foresight revenue bit for bit for the
default battery. The README needs to frame this honestly as a property of this month and
battery combination, not evidence the forecast logic does nothing; the duration and
efficiency sweep points on the same fixture do show capture below 1.0.
</details>

**Q5.** Why do `analytics/benchmarks.py` and `analytics/sweep.py` contain zero file I/O?
<details><summary>Answer</summary>
To preserve the pure-library / IO-owning-CLI split established in PR #4: analytics
functions take DataFrames or arrays and return plain data structures, and only the Typer
commands in `cli.py` own reading config files, writing JSON, and writing PNGs. This keeps
the analytics testable without touching a filesystem and keeps output-path decisions in one
place.
</details>

**Study time estimate:** 20 minutes.

---

## PR #8: M3a, AS Clearing-Price Data Layer

**Spec:** `specs/M3a_as_data_layer.md` (master: `specs/M3_ancillary_services.md`)
**Review:** `specs/review_issues/review-6f498150.md` (PASSED, 1 skippable issue)
**Analysis:** `ai_docs/research/6f498150-m3a-as-data-layer-analysis.md`
**Size:** +1705/-38, merged 2026-08-01
**Density tier:** domain rules v2, medium (mostly reapplies PR #1's patterns, but with a
genuinely new and gnarlier gridstatus discovery)

### Concepts worth knowing cold

1. **Both spec-named gridstatus methods are dead ends, escalating PR #1's lesson.**
   `Ercot.get_as_prices` and `Ercot.get_mcpc_dam` (the two methods the spec explicitly
   names) both read MIS report 12329, whose live document list was verified during
   research to retain only about 31 days. Neither serves 2023-2024. The working path,
   found and verified end to end, is MIS report **13091** ("Historical DAM Ancillary
   Service MCPCs"), reached via gridstatus's *private* `Ercot._get_document(...)` helper, a
   deeper and more fragile reach into the library than PR #1's `get_dam_spp(year)` fix
   (which was at least a public method).
2. **A wide-format archive with two silent-corruption traps.** The archive is one row per
   hour, one column per product (not long, unlike the rest of the schema), the `"REGUP "`
   column header carries a trailing space in both 2023 and 2024, and raw product codes
   (`REGDN`/`REGUP`/`RRS`/`NSPIN`/`ECRS`) don't match any canonical name used elsewhere in
   the schema (`REG_DOWN`/`REG_UP`/`RRS`/`NONSPIN`/`ECRS`). Column names are stripped
   immediately after `read_csv`, and product mapping is an explicit dict that raises on any
   unmapped column rather than passing it through
   (`ai_docs/memory/entries/pitfall-as-mcpc-archive-wide-format.md`).
3. **Structural absence versus a real gap, encoded the same way for two different
   meanings.** ECRS didn't exist before 2023-06-10; the wide-to-long melt naturally
   produces `NaN` for ECRS before launch, and dropping those rows means ECRS simply has no
   rows pre-launch. `_validate`'s per-product expected window starts at
   `max(requested_start, product_launch_date)`, so this is validated as expected, not an
   error. A genuine gap in a *live* product's data goes through the identical
   dropna-then-gap-check path but *is* an error there, raising and listing the exact
   missing `(product, interval)` pairs.

### Comprehension questions

**Q1.** Both methods the M3a spec named (`get_as_prices`, `get_mcpc_dam`) turned out not to
work for 2023-2024. What did research find instead, and why is it a "deeper reach" into
gridstatus than PR #1's fix?
<details><summary>Answer</summary>
Both spec-named methods read MIS report 12329, whose document list live-verified to only
retain roughly 31 days of recent postings. The working path is MIS report type 13091
("Historical DAM Ancillary Service MCPCs"), yearly zip archives, reached via gridstatus's
*private* `Ercot._get_document(report_type_id=..., constructed_name_contains=...)` helper.
Unlike PR #1's fix (`get_dam_spp(year)`, a public method), this reaches into a private
implementation detail of the library, which is more fragile to a future gridstatus upgrade.
</details>

**Q2.** Name the two silent-corruption traps in the raw MIS 13091 archive and how
`as_prices.py` defends against each.
<details><summary>Answer</summary>
(1) The "REGUP" column header carries a trailing space in both years' files, so column
names are stripped immediately after `read_csv`, before anything else touches them. (2) Raw
product codes (`REGDN`/`REGUP`/`RRS`/`NSPIN`/`ECRS`) don't match the canonical schema names,
so an explicit product-name map is applied and any unrecognized column raises rather than
silently passing through.
</details>

**Q3.** How is ECRS's pre-launch absence (before 2023-06-10) represented in the canonical
frame, and how is that different from a genuine post-launch data gap?
<details><summary>Answer</summary>
Pre-launch absence is structural: the wide-to-long melt naturally produces `NaN` for ECRS
before launch (the archive column is simply empty there), and after dropping those rows
ECRS just has no rows for that period; validation treats this as expected because the
per-product validation window starts at `max(requested_start, product_launch_date)`. A
genuine gap in a *live* product goes through the same dropna-plus-gap-check mechanism, but
because it falls inside the product's validation window, it raises and lists the exact
missing `(product, interval)` pairs rather than being silently accepted.
</details>

**Q4.** Why did the AST-based gridstatus import-confinement test need to change for this
PR, and why does it parse the AST instead of grepping source text?
<details><summary>Answer</summary>
It needed widening from a single-module allowlist (`{prices.py}`) to two modules
(`{prices.py, as_prices.py}`), since AS ingestion also legitimately needs gridstatus
access. Parsing the AST rather than grepping avoids false positives from comments or
docstrings that mention "gridstatus" without an actual import statement.
</details>

**Study time estimate:** 30 minutes.

---

## PR #9: M3b, Energy + AS Co-optimization LP

**Spec:** `specs/M3b_as_cooptimizer.md` (master: `specs/M3_ancillary_services.md`)
**Review:** none generated. This is the one PR of the eight with no
`specs/review_issues/review-<adw-id>.md` file; every other PR has one, even the ones that
passed clean. Worth asking why, since it's an outlier in an otherwise consistent pipeline
output.
**Analysis:** `ai_docs/research/3034ec63-m3b-as-cooptimizer-analysis.md`
**Size:** +1387/-28, merged 2026-08-01
**Density tier:** deepest of the eight

### Concepts worth knowing cold

1. **The LP formulation extended, not replaced.** All of PR #2's variables, dynamics, and
   bounds stay exactly as they were; per-product award variables `a_pt >= 0` are added with
   four new constraint families per interval: up coupling, down coupling, up energy
   adequacy, and down room adequacy (`src/bess/optimizer/as_lp.py:56-59`). Three pinned
   conventions matter more than the algebra: **(1)** adequacy uses *end-of-interval* SoC,
   not start-of-interval (equally defensible, but this is the choice the goldens are
   derived from); **(2)** awards may legitimately *exceed* `power_mw` while charging,
   because curtailing a charge is real up-capability and the coupling constraint captures
   the full swing, up to `2 * power_mw` (`src/bess/optimizer/as_lp.py:70-74`); do not "fix"
   this by capping awards; **(3)** capacity payments only, awards never move SoC. Golden
   tests 4 and 5 (additive == 250.0, REG_DOWN room == 150.0) both fail if someone caps
   awards at `power_mw`.
2. **Degeneracy one level up: it now moves money between products, not just intervals.**
   Shuffling the product order on the July fixture leaves the total objective identical
   (to the last bit) but moves $2,555 between REG_UP and ECRS, because at some hours the
   coupling constraint binds while adequacy is slack and two products tie on marginal
   value. The lesson from PR #2 (assert aggregates, never a specific vertex) escalates: any
   test or reader must assert the objective and total AS revenue, never a specific
   per-product dollar split, which is real but arbitrary.
3. **A pipeline-process lesson, not a code lesson: stale worktree branches.** This PR's
   ADW branch was cut from `main` before PR #8 (M3a) had actually merged, even though the
   spec named M3a as an already-merged prerequisite. The property tests needed M3a's
   committed fixtures and module, which were simply absent from the branch until `origin/main`
   was merged in. This produced a new codified pitfall
   (`ai_docs/memory/entries/pitfall-adw-stale-worktree-branch-dependency-merge.md`): when a
   spec names another slice as "merged," check the actual branch point, don't trust the
   spec's dependency claim at face value.

### Comprehension questions

**Q1.** What are the three pinned conventions in the AS co-optimization formulation, and
which golden tests would fail if someone "fixed" convention 2?
<details><summary>Answer</summary>
(1) Adequacy constraints use end-of-interval SoC, not start-of-interval. (2) Awards may
exceed `power_mw` while the battery is charging, because curtailing a charge is genuine
up-capability and the up-coupling constraint already captures the full swing. (3) Capacity
payments only; awards never move SoC (no deployment energy modeled). Goldens 4 (additive,
250.0) and 5 (REG_DOWN room, 150.0) both derive their expected numbers from convention 2
holding; capping awards at `power_mw` would make both fail.
</details>

**Q2.** Shuffling AS product order on the July fixture changes which product "earns" a
given $2,555 (REG_UP versus ECRS) while the objective stays bit-identical. What does that
mean for how tests (and reviewers) should treat `revenue_by_product`-style output?
<details><summary>Answer</summary>
It means per-product revenue attribution can be a degenerate/arbitrary choice among
multiple equally-optimal LP vertices, exactly one level up from PR #2's per-interval
degeneracy. Tests must assert the total objective and aggregate AS revenue, never a
specific per-product dollar figure, except in the hand-derived goldens where the optimum is
provably strict.
</details>

**Q3.** What went wrong with this PR's ADW worktree branch before any code was written, and
what pipeline-level lesson did it produce?
<details><summary>Answer</summary>
The branch was cut from `main` before PR #8 (M3a) actually merged, so M3a's fixtures
(`tests/fixtures/as_mcpc_2023_07.parquet`) and module (`src/bess/data/as_prices.py`) were
simply absent, even though the spec named M3a as an already-merged prerequisite. The
lesson: when a spec claims another slice is "merged," verify the actual branch point and
merge `origin/main` in before building, rather than discovering missing files mid-build.
</details>

**Q4.** `AsDispatchResult.dispatch.objective_value` is documented as the FULL co-optimized
dollar figure, not the energy leg alone. Why does that distinction matter for whoever calls
this function next?
<details><summary>Answer</summary>
Because a naive caller might assume `dispatch.objective_value` means the same thing it
meant in plain `optimize_dispatch` (energy-only revenue) and feed it straight into
energy-only scoring code. PR #10 has to explicitly swap this field out
(`dataclasses.replace`) before scoring the energy leg with `metrics_from_dispatch`,
specifically because this field really is the combined total, not just energy.
</details>

**Q5.** A synthetic 2-year, 5-product co-optimization solve (T=17,520, 122,640 variables)
completes in about 1 second against a 60-second budget. Why is runtime a non-issue here
even though the problem is roughly 5x larger than PR #2's plain optimizer?
<details><summary>Answer</summary>
The same CSC/column-wise numpy-built sparse matrix technique from PR #2 extends directly to
`(3+P)*T` columns without needing the slow incremental API; adding more products scales the
matrix construction, not the number of Python-to-C++ calls, so the added problem size costs
roughly linear extra build time, not a fundamentally different order of magnitude.
</details>

**Study time estimate:** 60 minutes. Read `src/bess/optimizer/as_lp.py` next to
`src/bess/optimizer/lp.py` side by side; the diff between them is most of the learning
value.

---

## PR #10: M3c, AS Backtest, CLI, and README

**Spec:** `specs/M3c_as_backtest_cli.md` (master: `specs/M3_ancillary_services.md`)
**Review:** `specs/review_issues/review-d39c4d18.md` (PASSED, 2 tech-debt/skippable issues)
**Analysis:** `ai_docs/research/d39c4d18-m3c-as-backtest-cli-analysis.md`
**Size:** +1525/-47, merged 2026-08-01
**Density tier:** integration, medium (one genuinely subtle correctness decision, the rest
is wiring)

### Concepts worth knowing cold

1. **The one real design decision: an objective-value substitution that has to happen
   before scoring.** `AsDispatchResult.dispatch.objective_value` is the FULL co-optimized
   figure (PR #9), but `metrics_from_dispatch` computes `daily_revenue` purely from the
   energy leg (`prices * (discharge - charge) * dt`). Feeding the raw co-opt result straight
   through would break two things at once: the AC-2 decomposition identity
   (`energy_revenue + as_revenue == total`) and M1's own invariant that `daily_revenue`
   sums to `total_revenue_usd`. The fix, one line via `dataclasses.replace`
   (`src/bess/backtest/as_runner.py:136`): swap `objective_value` for
   `as_dispatch.energy_revenue_usd` before calling `metrics_from_dispatch`, so the
   resulting `energy` field is a genuine, directly-comparable energy-leg `BacktestResult`.
2. **Two counterintuitive real numbers, both correct.** On the July fixture, the
   co-optimized *energy leg alone* ($567k) is actually *lower* than the pure energy-only
   backtest ($970k): the battery trades away arbitrage to sell AS capacity instead, and
   dominance (co-opt >= energy-only) only holds on the *total*, never the energy leg by
   itself. Separately, NONSPIN earns exactly $0 in the revenue mix, not because of a bug but
   because its 4-hour sustain-duration assumption is structurally unaffordable for a
   2-hour-duration battery (200 MWh / 100 MW) to back.
3. **Filename qualification, extended a third level, and a deliberate scope guard.** The
   metrics filename pattern born as a bugfix in PR #7
   (`{location}_metrics_{mode}.json`) gets extended to
   `{location}_metrics_{mode}_ancillary.json` here. Separately, `--ancillary --mode rolling`
   is explicitly rejected with a nonzero exit and a message naming M3's perfect-foresight-only
   scope (`src/bess/cli.py:395`), rather than either silently running an undefined
   combination or producing a plausible-looking but meaningless number.

### Comprehension questions

**Q1.** Why can't `AsDispatchResult` be passed straight into `metrics_from_dispatch`
without modification?
<details><summary>Answer</summary>
`dispatch.objective_value` on the co-optimized result is the FULL co-optimized dollar
figure (energy plus AS), but `metrics_from_dispatch` computes `daily_revenue` from the
energy leg only. Passed through unmodified, this breaks the AC-2 decomposition identity
(`energy_revenue_usd + as_revenue_usd == total_revenue_usd`) and M1's own invariant that
`daily_revenue.sum() == total_revenue_usd`. The fix replaces `objective_value` with
`energy_revenue_usd` via `dataclasses.replace` before scoring
(`src/bess/backtest/as_runner.py:136`).
</details>

**Q2.** On the July fixture, the co-optimized backtest's energy leg alone ($567k) is lower
than the plain energy-only backtest's revenue ($970k), even though the total co-opt revenue
dominates. Does this violate the spec's dominance criterion?
<details><summary>Answer</summary>
No. Dominance is defined on TOTAL revenue (energy + AS >= energy-only total), which holds
comfortably ($2.69M >= $970k). The energy leg alone can legitimately be lower, because the
battery is choosing to sell AS capacity instead of arbitraging energy at some hours, a real
economic tradeoff the optimizer makes on purpose. A test asserting dominance on the energy
leg alone would (correctly) fail.
</details>

**Q3.** Why does NONSPIN earn exactly $0.00 in the July fixture's revenue mix?
<details><summary>Answer</summary>
Not a bug: NONSPIN's 4.0-hour sustain-duration assumption makes it the most expensive
product per MW of adequacy to back, and the adequacy constraint makes a meaningful NONSPIN
award structurally unaffordable for a 2-hour-duration battery (200 MWh / 100 MW). The LP
legitimately never finds it worth awarding.
</details>

**Q4.** What happens when `--ancillary` and `--mode rolling` are requested together, and
why is that handled with an explicit guard instead of just letting it run?
<details><summary>Answer</summary>
The CLI checks for this combination up front and exits nonzero with a message naming M3's
perfect-foresight-only scope (`src/bess/cli.py:395`), rather than silently running an
unsupported/undefined combination or producing a number that looks plausible but has no
defined meaning. Rolling-horizon dispatch combined with AS co-optimization is explicitly
out of scope for this milestone.
</details>

**Q5.** The reviewer found `revenue_mix` could raise `ZeroDivisionError` if total AS revenue
across all products is exactly $0, but didn't block the merge on it. Why was that an
acceptable call, and what's the actual risk left on the table?
<details><summary>Answer</summary>
The failure mode (all AS products earning exactly $0 in total) is a plausible LP-degeneracy
edge case the spec itself calls out, but it isn't reachable on any currently committed
fixture, so it doesn't violate any acceptance criterion today. It's recorded as tech debt
(`ai_docs/memory/entries/lesson-revenue-ratio-helpers-need-zero-guard.md`) instead of being
fixed defensively; the risk is that `bess benchmark` would crash instead of skipping cleanly
if a future window ever hits exactly $0 total AS revenue.
</details>

**Study time estimate:** 30 minutes.

---

## Recommended study order and time budget

The density ranking (highest to lowest): **#9 > #2 > #5 > #1 > #8 > #4 > #10 > #7.** But
the recommended *study order* follows merge order instead of pure density, because the
concepts genuinely compound: PR #4's shared-solve pattern is a prerequisite for reading
PR #5 and PR #10 well, PR #1's DST/gridstatus lessons are a prerequisite for PR #8, and
PR #2's LP formulation and degeneracy lesson are a hard prerequisite for PR #9. Studying
density-first would mean re-deriving context PR #4 and PR #1 already hand you for free.

| Order | PR | Topic | Time | Running total |
|---|---|---|---|---|
| 1 | #1 | M1a data layer (DST, gridstatus quirks) | 30 min | 30 min |
| 2 | #2 | M1b LP optimizer (deep dive) | 50 min | 1h 20m |
| 3 | #4 | M1c backtest/CLI/plots (shared-solve pattern born) | 35 min | 1h 55m |
| 4 | #5 | M2a rolling horizon (DST bug hunt, capture-rate lesson) | 45 min | 2h 40m |
| 5 | #7 | M2b benchmarks/sweeps (lightest, filename-collision fix) | 20 min | 3h 00m |
| 6 | #8 | M3a AS data layer (wide-format archive trap) | 30 min | 3h 30m |
| 7 | #9 | M3b AS co-optimizer (deepest, read side by side with #2) | 60 min | 4h 30m |
| 8 | #10 | M3c AS backtest/CLI (objective_value substitution) | 30 min | 5h 00m |

**Total: about 5 hours.** Practical split: do #1/#2/#4 in one session (about 2 hours, this
is the M1 foundation and the one unavoidable deep dive), #5/#7/#8 in a second session (about
95 minutes, lighter, mostly pattern reinforcement), and #9/#10 in a third session (90
minutes, the second deep dive plus its integration). Do #2 and #9 early in a session while
fresh, not as the last item when attention is already spent; they're the two PRs where
skimming instead of reading the actual LP construction will cost the most understanding
later, especially once M4 (the Rust port of exactly this LP) starts.

---

## Going-forward review ritual

Goal: make future PRs get read this deeply *the first time*, without turning every merge
into a 5-hour session. This plugs into the existing runbook flow described at the top of
`specs/TASKS.md`: "kick off the next unchecked task, review its PR, merge, tick the box,
move on." The ritual below is what happens inside the "review its PR" step.

### The ritual (per PR, time-boxed)

1. **Generate the explainer first, before reading the raw diff (agent time, not yours;
   about 2-5 min wall clock).** Once the draft PR is open, run the installed
   `explain-diff-html` skill (`.claude/skills/explain-diff-html/SKILL.md`) against the PR.
   It produces a single self-contained HTML file (background, intuition with toy examples,
   a literate code walkthrough, and a 5-question interactive quiz) at a path outside the
   repo, timestamped per the skill's own convention. Read it before opening `gh pr diff`
   cold; it does the orientation work a raw diff forces you to redo by hand.
2. **Take the quiz cold (5-10 min).** Don't peek at the answers while reading the code
   walkthrough section if you can help it. A missed question tells you exactly which
   concept to go back and actually read, rather than skim.
3. **Cross-check against the pipeline's own review (5 min).** The ADW pipeline already
   writes `specs/review_issues/review-<adw-id>.md` during its own review phase. Read it as
   a second opinion, not a substitute: confirm the reported issues are genuinely
   tech-debt/skippable and not something that should actually block. (Note from this
   study: PR #9 shipped with no such file at all, which is worth a one-line question to
   whatever produces that phase.)
4. **Spot-check one load-bearing file directly in the raw diff (5-10 min, scales with PR
   risk tier).** Pick the file with the most domain risk for this PR: the LP formulation
   file for an optimizer PR, the validation/canonicalization function for a data-layer PR,
   the CLI wiring for an integration PR. This is where you catch the kind of subtle,
   easy-to-miss correctness call PR #10 had (the `objective_value` substitution) that an
   explainer's intuition section might gloss over.
5. **Decide and record.** Merge, request changes, or (for a PR dense enough to warrant real
   study time, like a future LP-formulation PR) flag it and add a card to a file like this
   one before merging, not after forgetting why it mattered.
6. **Tick the box, append the Log row.** Already part of the existing flow at the bottom of
   `specs/TASKS.md`; no change needed there. (Side note surfaced by this study: T6/T7/T8's
   checkboxes are currently still `[ ]` in `specs/TASKS.md` even though the Log table and
   PR links show all three merged; worth a quick manual sync pass independent of this
   ritual.)

**Time box:** 15-20 minutes total for a plumbing-tier PR (data layer, CLI wiring, analytics),
30-45 minutes for an LP-formulation or new-algorithm PR. This mirrors the per-PR study
estimates above almost exactly, which is the point: the ritual is this guide's density
ranking applied prospectively instead of retroactively.

### Where `explain-diff-html` slots in, precisely

Step 1, and only step 1. It replaces "read the raw diff cold" as the first pass, not the
whole review. Its quiz is the forcing function; its background/intuition sections are the
context you'd otherwise reconstruct by hand every time. It is not a substitute for step 4
(the direct file spot-check), because an explainer optimized for clarity can smooth over
exactly the kind of subtle, deliberate design decision (a pinned convention, a swapped
field, a documented-but-counterintuitive number) that only shows up by reading the actual
lines.

### Proposed one-line addition to `specs/TASKS.md`

Not applied, per instructions; this is the exact line to add. It belongs in the "How to run
a task" section, as a new sentence immediately after "Merging is always manual." in the
existing explanatory paragraph:

> Before merging: run the `explain-diff-html` skill on the PR and pass its quiz cold; treat
> `specs/review_issues/review-<adw-id>.md` as a second opinion, not a substitute for reading it.

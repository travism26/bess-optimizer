# Research: M1b LP Dispatch Optimizer (HiGHS/highspy)

## Metadata

adw_id: `3b9cf1a9`
prompt: `specs/M1b_optimizer.md`
date: `2026-07-29`

## Executive Summary

M1b is a tightly bounded, additive build: one stub function
(`optimize_dispatch` in `src/bess/optimizer/lp.py`, currently
`raise NotImplementedError`) plus two test files that are pure TODO comments. No
existing implemented code changes, no dependency changes (highspy is already a
pinned dependency, resolving to 1.15.1), and the baseline gates are green today
(ruff, mypy, 11 passing tests).

I prototyped the exact LP formulation from the master spec against the installed
highspy and it reproduces all four golden objectives exactly (0.0, 180.0, 175.0,
50.0) and solves T=17,520 in **0.22 s**, roughly 130x inside the 30 s budget. The
two findings that will actually cost the build phase time are: (1) the obvious
construction for acceptance criterion 10 does **not** produce simultaneous
charge/discharge (the LP drains the battery for free in earlier zero-price hours
instead), and (2) mypy's `warn_return_any` will reject values read straight out of
highspy, which is untyped.

## Existing Architecture

### Relevant Documentation Found

| Document | Contents relevant to M1b |
| -------- | ------------------------ |
| `specs/M1_python_core.md` | Master spec, wins on conflict. Frozen `optimize_dispatch` signature, the LP formulation to implement exactly, `DispatchResult` shape, gotcha 2 (simultaneous charge/discharge is expected, MILP fix deferred), gotcha 3 (negative prices are valid). |
| `specs/M1b_optimizer.md` | The task spec. In/out of scope, hard purity rule, 11 acceptance criteria (4 golden, 5 property, 2 behavior/budget). |
| `specs/M1c_backtest_cli.md` | Downstream consumer. Its AC-1 runs the same property battery on the real HB_NORTH July 2023 fixture, and its AC-5 injects a stub optimizer. Relevant because it is where master AC-5 (properties on real fixture data) actually lands. |
| `specs/TASKS.md` | T2 is this task; technically independent of T1, sequenced after it so PRs land one at a time. T1 is merged (commit `b56e14f`). |
| `CLAUDE.md` | Repo rules: frozen interfaces, `optimize_dispatch` purity, no network in tests, no em-dashes, no AI-attribution commit trailer. |
| `ai_docs/memory/entries/lesson-ast-based-import-confinement-guard.md` | Prior lesson: implement import-confinement guards with `ast`, not text search. Directly applicable to the purity test here. |
| `ai_docs/memory/entries/pitfall-adw-worktree-port-file-cleanup.md` | `.ports.env` is tracked and is already dirty in this worktree; untrack/restore it before finalizing. |
| `specs/review_issues/review-3c648beb.md` | M1a review. Issue #3: stale scaffold TODO comments left above implemented tests read as outstanding work. Delete the TODOs in this task's test files as they are implemented. |
| `app_docs/feature-3c648beb-data-layer.md` | The documentation format the document phase will mirror for M1b. |

No architecture diagram exists yet; the README `## Architecture` section is still a
TODO owned by M1c.

### Component Map

```
                    numpy price array + dt + BatterySpec
                                   │
                                   ▼
              src/bess/optimizer/lp.py :: optimize_dispatch()   <- M1b, the only
                 ├─ build HighsLp (cols: c_t, d_t, s_t)            source file
                 ├─ h.passModel(lp) / h.run()                      in scope
                 ├─ status check (non-optimal -> raise)
                 └─ DispatchResult(c, d, s, obj, status, simultaneous_hours)
                                   │
        ┌──────────────────────────┴───────────────────────┐
        ▼                                                  ▼
 src/bess/backtest/runner.py                     tests/test_optimizer_golden.py
   run_backtest(..., optimizer=optimize_dispatch)  tests/test_optimizer_properties.py
   (stub today, built in M1c)                      (TODO scaffolding today)
        │
        ▼
 src/bess/cli.py :: backtest/plot (stubs, M1c)

 imports allowed inside lp.py: numpy, highspy, bess.models (+ stdlib logging,
 __future__). NOT pandas, NOT bess.data.*  <- enforced by a purity test
```

Dependency direction is one-way: `lp.py` depends only on `bess.models`, and
`backtest/runner.py` depends on `lp.py`. Nothing depends on internals of `lp.py`
other than the frozen `DispatchResult`.

### Key Files and Modules

| File | Purpose / current state |
| ---- | ----------------------- |
| `src/bess/optimizer/lp.py` | 41 lines. Module docstring plus `optimize_dispatch` with a full intended-behavior docstring and `raise NotImplementedError`. The single implementation target. |
| `src/bess/models.py` | Frozen `BatterySpec`, `DispatchResult`, `BacktestResult`. Implemented, must not change. |
| `tests/test_optimizer_golden.py` | 23 lines, all TODO comments for AC-1 through AC-4. |
| `tests/test_optimizer_properties.py` | 23 lines, all TODO comments for AC-5 through AC-7 (master numbering; M1b renumbers these as 5-11). |
| `tests/conftest.py` | Autouse socket guard. Harmless here: the LP tests use synthetic arrays and never touch the network. |
| `tests/test_data.py` | Reference test style, including the `ast`-based `_imports_gridstatus` guard to copy for the purity test. |
| `src/bess/data/prices.py` | Reference module style: spec-referencing docstrings, module-level `logger`, `_`-prefixed private helpers. |
| `pyproject.toml` | `highspy>=1.7` (resolved 1.15.1 in `uv.lock`), mypy override `ignore_missing_imports` for `highspy.*` already present, ruff `line-length = 100`, mypy `files = ["src", "tests"]` with `disallow_untyped_defs`. |

## Affected Areas

### Files That Will Need Changes

| File | Why |
| ---- | --- |
| `src/bess/optimizer/lp.py` | Implement `optimize_dispatch`. Docstring must document the no-terminal-SoC decision and the deferred `max_cycles_per_day` (M1b definition of done). |
| `tests/test_optimizer_golden.py` | AC-1 through AC-4, replacing the TODO comments. |
| `tests/test_optimizer_properties.py` | AC-5 through AC-11 (properties on 3 seeded synthetic series, simultaneity behavior, runtime budget) plus the import-purity test. |

No other file needs to change. Specifically **not** needed:

- `pyproject.toml`: highspy is already a dependency with a mypy override; no new
  marker is needed (the runtime test is a normal test, not `manual`).
- `src/bess/models.py`: frozen, and `DispatchResult` already has every field.
- `src/bess/backtest/runner.py` and `src/bess/cli.py`: their stubs already import
  `optimize_dispatch`, so they start working against a real implementation with no
  edit. Wiring them is M1c.
- `tests/conftest.py`: the network guard needs no carve-out for this task.

### Dependencies

- **Upstream of `lp.py`:** `bess.models` (frozen dataclasses), numpy, highspy.
- **Downstream of `lp.py`:** `bess.backtest.runner` imports `optimize_dispatch` as
  the default `optimizer` argument; `tests/test_smoke.py::test_imports_resolve`
  imports the module. Both already pass against the stub and will keep passing.
- **External:** highspy 1.15.1 wheels (HiGHS 1.15.1). Already in `uv.lock`, so CI
  `uv sync --locked` gets the same build.

### Integration Points

1. `run_backtest(prices_df, battery, optimizer=optimize_dispatch)` (M1c) is the
   only production caller. It will pass a `float64` price array extracted from the
   canonical DataFrame and `dt_hours=1.0`.
2. M1c AC-1 re-runs the property battery on real fixture data, and M1c AC-2 puts a
   sanity corridor (5 to 60 equivalent full cycles for the fixture month) on the
   result. A units or `dt` bug in M1b surfaces there, so getting the MWh vs MW
   bookkeeping right matters beyond this PR.
3. M4 (Rust) replaces this function behind the same signature; anything computed
   outside the solver (for example `simultaneous_hours`) has to be reproducible
   from the returned arrays.

## Impact Analysis

### Scope of Change

Small and purely additive: roughly 100 to 140 lines of implementation and 250 to
350 lines of tests. Zero refactoring risk, since every touched symbol currently
raises `NotImplementedError` or is a comment. The blast radius is bounded by the
frozen `DispatchResult`.

### Risks and Considerations

**1. The obvious AC-10 construction silently does not produce simultaneity (highest
risk item).** I built the case the spec describes literally ("deeply negative price
and initial SoC at capacity") with the negative hour in the middle of a horizon of
zero-price hours. Result: `simultaneous_hours == 0`. The LP simply discharges to
waste during the free zero-price hours before the negative hour, arriving empty and
charging cleanly. Simultaneity is only forced when there is **no opportunity to
pre-drain**. Verified working constructions:

- Negative price at `t=0` with `initial_soc_mwh == energy_mwh`: 1 MW / 2 MWh,
  eff 0.9/0.9, `prices[0] = -1000`, rest 0 gives `c_0 = 1.0`, `d_0 = 0.81`,
  `s_0 = 2.0`, objective 190.0, `simultaneous_hours == 1`.
- An all-negative series with a full battery: `prices = [-100] * 6`, same battery,
  gives `simultaneous_hours == 6`.

The economics: at `p = -1000`, holding the SoC bound requires
`d >= eta_c * eta_d * c = 0.81` per MW charged, and net revenue
`p * (d - c) = -1000 * (0.81 - 1) = +190` stays positive, so burning energy through
the round-trip loss is genuinely profitable. Any plan for AC-10 must pin the
negative price at `t=0`.

**2. mypy `warn_return_any` versus untyped highspy.** `pyproject.toml` sets
`warn_return_any = true` and `disallow_untyped_defs = true`, and highspy is under
`ignore_missing_imports`, so every value coming out of it is `Any`. Returning
`h.getObjectiveValue()` directly into a `float` field, or `h.getSolution().col_value`
into an `np.ndarray` field, will fail the typecheck gate. Wrap explicitly:
`float(h.getObjectiveValue())`, `np.asarray(sol.col_value, dtype=np.float64)`,
`str(h.modelStatusToString(status))`.

**3. Solution arrays are populated even when the model is not optimal.** An
infeasible probe (`initial_soc_mwh=5.0` with `energy_mwh=2.0`) returned model status
`Infeasible` with a full-length, all-zero `col_value` and objective `0.0`. Nothing
raises on its own. Check `h.getModelStatus() == highspy.HighsModelStatus.kOptimal`
**before** reading or trusting the solution, and raise with the status string in the
message (AC-3 of the M1b spec).

**4. `solver_status` string casing.** The master spec says the field "must be
`optimal` for success" (lowercase) and AC-5 asserts `solver_status == "optimal"`.
`h.modelStatusToString(...)` returns `"Optimal"`, `"Infeasible"`, `"Unbounded"`,
`"Time limit reached"`. Lowercasing the HiGHS string satisfies both the success
assertion and the "status in the message" requirement for failures.

**5. Degenerate optima: assert revenue, never a specific schedule.** The spec
already warns about this for AC-1 ("assert zero revenue, not zero dispatch"), and it
applies equally to AC-3: with hours 0-11 all at $10, any split of the 2.5 MWh grid
draw across those hours is optimal, so the spec's "(1.0, 1.0, 0.5 MW hours)" is one
representative solution, not a unique one. Assert the objective and aggregate
quantities (total grid draw, total discharge), not per-hour values.

**6. HiGHS writes a solver log to stdout by default.** Set
`h.setOptionValue("output_flag", False)` before `run()`, otherwise every test emits
solver banners. This is a solver option, not Python logging configuration, so it
does not violate the purity rule.

**7. Empty or malformed input.** My prototype raised a bare `IndexError` on `T=0`.
The spec is silent here, but a naked `IndexError` out of a frozen public function is
poor behavior. Guard the input minimally: 1-D array, `T >= 1`, `dt_hours > 0`, and
let genuinely infeasible parameter combinations surface as a solver-status raise.

**8. Purity test implementation.** M1b requires "a test asserts the module's import
list". Per the prior memory lesson, parse `src/bess/optimizer/lp.py` with `ast` and
compare the set of top-level module names imported, rather than grepping text (a
docstring mentioning pandas would false-positive; the current `lp.py` docstring
already mentions "DataFrames"). Allowed set today:
`{"__future__", "logging", "numpy", "highspy", "bess.models"}`.

**9. Recording wall time in test output (AC-11).** pytest captures stdout and
`addopts = "-q"` is set, so a plain `print()` is only visible with `-s` or on
failure. Simplest honest option: `print()` the measured time **and** include it in
the assertion message, so a breach of the budget always shows the number. Anything
fancier (junit `record_property`, a warning) is not worth the complexity.

**10. Spec conflict, master versus M1b, on the property-test data source.** Master
AC-5 says properties run on "real fixture data (one frozen month of HB_NORTH 2023)";
M1b criteria 5 to 9 say 3 seeded synthetic series (T=168, uniform [-20, 150]) and
declares the task "Independent of M1a; all tests use synthetic price arrays, no
market data". The master-wins clause makes this worth flagging, but they are
reconcilable: M1c AC-1 runs exactly the master's property battery on the real July
2023 fixture, which is already committed. Recommendation: implement M1b's synthetic
version as specified (it is the task's own acceptance criteria and it keeps this
module's tests free of pandas and fixtures), and let M1c satisfy master AC-5 on real
data. Adding a fixture-based property test here would duplicate M1c AC-1 and pull
pandas into the optimizer test module.

**11. Runtime is a non-issue but the model-build API choice matters.** Measured
0.22 to 0.25 s for T=17,520 (52,560 columns, 17,520 rows) using the low-level
`HighsLp` + `passModel` path. The high-level incremental API
(`h.addVariable` / `h.addConstr` per interval) would mean ~70,000 Python-level calls
into the extension and is the one plausible way to approach the 30 s budget. Use
`passModel`.

**12. Housekeeping.** `.ports.env` is tracked and currently modified in this
worktree (the known ADW pitfall); restore or untrack it before finalizing. Delete
the scaffold TODO comments as each criterion is implemented (M1a review issue #3).
No em-dashes in code or docs; no AI-attribution trailer in commits.

### Existing Patterns to Follow

- Module docstring states purpose and cites the spec sections it implements
  (`data/prices.py` is the model).
- `from __future__ import annotations` at the top of every module and test file.
- Module-level `logger = logging.getLogger(__name__)`; no `basicConfig`, no handler
  setup (explicitly allowed by the purity rule).
- Private helpers prefixed with `_` and unit-tested directly where useful
  (`_canonicalize`, `_validate` in the data layer are imported by name in tests).
- Test docstrings name the acceptance criterion they cover ("Acceptance criterion 3:
  ...").
- Every test function annotated `-> None` (mypy checks `tests/` too).
- Failures raise `ValueError` with a message naming the offending values.
- Ruff line length 100, rule set `E, W, F, I, B, UP, SIM, RUF`.

## Recommendations

### Implementation shape (validated by prototype)

Column ordering interleaved per interval, `[c_0, d_0, s_0, c_1, d_1, s_1, ...]`,
which keeps the constraint matrix banded and makes slicing the solution trivial
(`x[0::3]`, `x[1::3]`, `x[2::3]`).

- Objective (`lp.sense_ = ObjSense.kMaximize`): cost `-p_t * dt` on `c_t`,
  `+p_t * dt` on `d_t`, `0` on `s_t`.
- Bounds: `0 <= c_t, d_t <= power_mw`, `0 <= s_t <= energy_mwh`.
- Row `t` (equality, `row_lower == row_upper`):
  `-eta_c*dt*c_t + (dt/eta_d)*d_t + s_t - s_{t-1} = 0`, with the `s_{-1}` term
  dropped for `t = 0` and that row's RHS set to `initial_soc_mwh`.
- Build the matrix rowwise (`MatrixFormat.kRowwise`): 3 nonzeros in row 0, 4 in
  every later row, `nnz = 3 + 4*(T-1)`. Vectorized numpy construction is
  straightforward and even a plain Python loop was fast enough at T=17,520.
- After `run()`: check `getModelStatus()`, then read `getSolution().col_value` and
  `getObjectiveValue()`; compute
  `simultaneous_hours = int(np.sum((c > 1e-3) & (d > 1e-3)))` and
  `logger.warning(...)` when it is nonzero.

Reference prototype (verified against installed highspy 1.15.1; all four golden
objectives exact, T=17,520 in 0.22 s):

```python
lp = highspy.HighsLp()
lp.num_col_, lp.num_row_ = 3 * T, T
lp.col_cost_, lp.col_lower_, lp.col_upper_ = col_cost, col_lower, col_upper
lp.row_lower_, lp.row_upper_ = row_bound, row_bound   # equality rows
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = start, index, value
lp.sense_ = highspy.ObjSense.kMaximize

h = highspy.Highs()
h.setOptionValue("output_flag", False)
h.passModel(lp)
h.run()
status = h.getModelStatus()
if status != highspy.HighsModelStatus.kOptimal:
    raise ValueError(f"HiGHS did not solve to optimality: {h.modelStatusToString(status)}")
```

### Test plan mapping

| Criterion | Test | Note |
| --------- | ---- | ---- |
| 1 | `test_flat_prices_yield_zero_revenue` | Assert objective 0.0 within 1e-6; do not assert zero dispatch. |
| 2 | `test_step_prices_lossless` | Objective 180.0. |
| 3 | `test_step_prices_lossy_charge` | Objective 175.0; assert totals (2.5 MWh drawn, 2.0 MWh discharged), not per-hour values. |
| 4 | `test_negative_hour_is_paid_to_charge` | Objective 50.0. |
| 5-9 | `test_properties_on_seeded_series`, parametrized over 3 fixed seeds | `default_rng(seed).uniform(-20, 150, 168)`, default 100 MW / 200 MWh / 0.927 battery. Status, SoC bounds (1e-6), dynamics residual (1e-6), revenue identity (1e-4), power limits. |
| 10 | `test_simultaneous_charge_discharge_is_reported_not_raised` | Negative price at `t=0` with `initial_soc_mwh == energy_mwh` (see risk 1). Use `caplog.at_level(logging.WARNING)` to assert the WARNING. |
| 11 | `test_two_year_horizon_within_runtime_budget` | T=17,520, `time.perf_counter()`, assert < 30 s with the measured value in both the printout and the assertion message. |
| purity | `test_lp_module_imports_are_confined` | `ast`-based, mirroring `test_data.py::_imports_gridstatus`. |

### Sequencing

Implement `lp.py` first, then golden tests (they fail fast and pin the formulation),
then properties, then the simultaneity and runtime behavior tests, then the purity
test. Run `uv run ruff check .`, `uv run mypy`, `uv run pytest -q` (the three
`adw_gates.json` gates, mirroring CI) after each step; the typecheck gate is the one
most likely to bite, per risk 2.

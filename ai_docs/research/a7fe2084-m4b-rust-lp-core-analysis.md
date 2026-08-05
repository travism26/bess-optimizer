# Research: M4b Rust LP Core (hand-written slice)

## Metadata

adw_id: `a7fe2084`
prompt: `specs/M4b_rust_lp_core.md`
date: `2026-08-04`

## Executive Summary

M4b is the only slice in the project that an agent must not implement. Its diff
is confined to `rust/bess_engine/**` plus a runbook tick in `specs/TASKS.md`; no
Python source file changes, and the Python correctness oracle
(`src/bess/optimizer/lp.py`, 179 lines) sits untouched a few lines away. The
research value here is therefore not "what do we build" but "what will Travis
hit, and what does the pinned dependency set actually look like", so that the
tutoring mode has correct facts to tutor from.

Three findings need action before a keystroke is typed. First, **`rust/` is
still empty** (`rust/.gitkeep` only): M4a is specified but not built, so M4b is
currently blocked on T9. Second, and most important, **the `py.allow_threads`
API named in both the master spec and the learning research doc does not exist
in PyO3 0.28.3**: it was renamed to `Python::detach` (and `with_gil` to
`attach`). The crates are already vendored in the local cargo registry, so this
is verified against source, not recalled. Third, the `highs` 2.4.0 `ColProblem`
API maps onto `_build_lp` more cleanly than expected (`SolvedModel::objective_value()`
exists, so nothing has to be recomputed), but its `add_column` ordering
requirement inverts the mental model of the Python code: **every row must exist
before any column is added**, which forces a two-pass structure the numpy
version does not have.

## Existing Architecture

### Relevant Documentation Found

| Doc | What it contains |
| --- | --- |
| `specs/M4_rust_engine.md` | Master. Pins the `highs` crate, PyO3 0.28.x + rust-numpy pairing, `DispatchError` via thiserror, "simultaneous_hours computed in Rust", the frozen `optimize_dispatch_rust` seam, and the binding Learning protocol. Wins on conflict. |
| `specs/M4b_rust_lp_core.md` | This slice. 8 acceptance criteria, the 3-question review gate, "the agent may author nothing in this slice" except dictated literal test data. |
| `specs/M4a_rust_scaffold.md` | Upstream dependency (T9, unbuilt). Crate scaffold, maturin, CI rust job, gates, import-confinement guard, `optimize_dispatch_rust` raising NotImplementedError. Explicitly forbids a stub `optimize_dispatch`: M4b owns that name. |
| `specs/M4c_engine_parity_bench.md` | Downstream consumer (T11). Assumes `optimize_dispatch_rust` can "unpack BatterySpec, call bess_engine, assemble DispatchResult", which silently constrains M4b's return shape (see Risks). |
| `specs/M1_python_core.md` | The LP formulation to mirror exactly, plus golden cases 1-4 and the 30 s / T=17,520 budget. |
| `specs/M1b_optimizer.md` | The 11 acceptance criteria behind `lp.py`, including AC-10 (simultaneous charge/discharge) and the purity rule. |
| `ai_docs/research/learning/rust-learning-plan-m4.md` | The plan this slice implements: hand-write vs delegate split, week-2/week-3 ordering, `highs` over `good_lp` rationale. Its PyO3 API names are now stale (see Impact). |
| `ai_docs/memory/entries/lesson-lp-optimizer-degeneracy-in-tests.md` | Why cargo goldens must assert objective and net dispatch, not per-interval vertices. |
| `ai_docs/memory/entries/lesson-ast-based-import-confinement-guard.md` | The pattern M4a uses to confine `bess_engine`; M4b inherits it and must not add an import elsewhere. |
| `CLAUDE.md` | Frozen interfaces, no em-dashes, no AI-attribution trailer, gate commands. |

### Component Map

```
  Python side (unchanged by M4b)                     Rust side (M4b's whole diff)
  ------------------------------                     ----------------------------
  bess.backtest.runner.solve_dispatch                rust/bess_engine/
  bess.backtest.rolling.solve_rolling_dispatch         Cargo.toml   (M4a)
        |  optimizer(prices, dt_hours, battery)        src/lib.rs   (M4a: engine_info)
        v          ^ positional, 3 args                    + #[pyfunction] optimize_dispatch   <- M4b
  bess.optimizer.lp.optimize_dispatch  (ORACLE)           + build/solve/extract               <- M4b
        |                                                 + enum DispatchError                <- M4b
        |  highspy CSC HighsLp                             + #[cfg(test)] golden tests        <- M4b
        v
      HiGHS 1.15.1  (highspy wheel)                   highs 2.4.0 -> highs-sys 1.15.0
                                                        -> vendored HiGHS built from source

  bess.optimizer.rust.optimize_dispatch_rust  (M4a stub -> M4c completes)
        | the only module allowed to import bess_engine (AST guard, M4a)
        v
      bess_engine.optimize_dispatch   <- the boundary M4b builds
```

Solver-version parity is better than the master spec assumes: `uv.lock` pins
`highspy 1.15.1`, and `highs-sys 1.15.0` vendors the HiGHS C++ sources at the
matching 1.15 line. Same solver, same simplex, so 1e-6 golden agreement is a
reasonable bar rather than an optimistic one.

### Key Files and Modules

| File | Purpose for this slice |
| --- | --- |
| `src/bess/optimizer/lp.py:107-179` | `_build_lp`. The CSC layout to port: `col_nnz`, `start`, `index`, `value`, the three bound arrays, `col_cost`, `kMaximize`. |
| `src/bess/optimizer/lp.py:28-104` | `optimize_dispatch`. Status check, slicing the flat solution into three arrays, the 1e-3 simultaneity count, the WARNING, the RuntimeError message shape. |
| `src/bess/models.py:19-49` | `BatterySpec` (6 fields, `max_cycles_per_day` ignored) and `DispatchResult` (the 6 fields the boundary must ultimately feed). |
| `tests/test_optimizer_golden.py` | Goldens 1-4 with the exact price vectors and battery params to dictate into Rust test fixtures. |
| `tests/test_optimizer_properties.py:93-127` | AC-10, the simultaneous-charge/discharge case: `prices = [-1000.0]`, T=1, 1 MW / 1 MWh, eff 0.9/0.9, `initial_soc_mwh=1.0`. |
| `tests/test_optimizer_properties.py:145-171` | The AST import-confinement guard M4a extends for `bess_engine`. |
| `~/.cargo/registry/src/*/highs-2.4.0/src/` | Already vendored locally: `lib.rs`, `matrix_col.rs`, `status.rs`. The authoritative API reference, offline. |

## Affected Areas

### Files That Will Need Changes

| File | Change | Author |
| --- | --- | --- |
| `rust/bess_engine/src/lib.rs` (or a new `src/lp.rs` + `src/error.rs`) | The LP builder, solve, extraction, `DispatchError`, the `#[pyfunction]`. | Travis, by hand |
| `rust/bess_engine/src/lib.rs` `#[cfg(test)] mod tests` (or `tests/golden.rs`) | Cargo goldens 1-5 plus the infeasible path. | Travis; literal price vectors may be dictated by the agent |
| `rust/bess_engine/Cargo.toml` | Only if M4a left `highs` unused-but-declared and clippy or a feature flag needs a nudge. | Travis |
| `specs/TASKS.md` | Tick T10, record the PR number and merge date, per the existing log-table convention. | either |

Nothing else. `src/bess/**`, `tests/**`, `pyproject.toml`, `adw_gates.json`, and
`.github/workflows/ci.yml` are all M4a or M4c territory. If a change outside
`rust/bess_engine` looks necessary during M4b, that is a signal M4a was
under-built, not that M4b's scope grew.

### Dependencies

Upstream (must exist before M4b starts):

- A compiling crate with `highs`, `pyo3`, `numpy` (rust-numpy), and `thiserror`
  in `Cargo.toml`, a working `maturin develop`, and a green CI rust job. All of
  M4a.
- The local toolchain: `cargo 1.94.1` and `rustc 1.94.1` are installed;
  `cmake 3.x` and `/usr/bin/c++` are present. **`maturin` is not installed**
  (`which maturin` fails), so `uv tool install maturin` or the dev-group entry
  from M4a is a prerequisite for acceptance criterion 7.

Downstream (what breaks if M4b's shape is wrong):

- `src/bess/optimizer/rust.py` (M4c) is the only caller. It unpacks
  `BatterySpec` into plain floats and reassembles `DispatchResult`.
- `run_backtest` and `run_backtest_rolling` call the optimizer **positionally**
  as `optimizer(prices, dt_hours, battery)` (`runner.py:69`, `rolling.py:173`),
  so the Python-level signature is fixed; the Rust-level signature underneath it
  is M4b's choice.

### Integration Points

The single integration point is the `#[pyfunction]` boundary. Everything else
in the milestone was pre-built for this moment: the `optimizer` parameter on
`run_backtest` has existed since M1c precisely so M4 could drop in without
touching call sites.

## Impact Analysis

### Scope of Change

Small in file count, deep in unfamiliar surface. Roughly 200-300 lines of Rust
across the builder, the error enum, the boundary, and six tests, against a
179-line Python oracle. The spec's 12-16 hour budget is consistent with the
learning-plan estimate and with the fact that the algorithm is already known;
the time goes to the borrow checker and the two API surfaces below, not to the
LP.

### Risks and Considerations

1. **`py.allow_threads` does not exist in PyO3 0.28.3.** Verified in
   `~/.cargo/registry/src/*/pyo3-0.28.3/src/marker.rs`: the method is
   `Python::detach<T, F>(self, f: F) -> T where F: Ungil + FnOnce() -> T, T: Ungil`
   (line 558), and `with_gil` is now `attach`. Neither old name survives as a
   deprecated alias anywhere in the crate source. Both `specs/M4_rust_engine.md`
   ("the HiGHS build+solve wrapped in `py.allow_threads`") and the learning
   research doc name the old API. Treat the spec's intent as normative and the
   spelling as stale; note the correction in the M4b PR rather than editing the
   master mid-slice.

2. **The GIL-release boundary is the real borrow-checker fight, and the obvious
   shape is the unsound one.** `PyReadonlyArray1::as_array()` returns
   `ArrayView<'_, f64, Ix1>` borrowing Python-owned memory. Because `Ungil` is
   blanket-implemented for every `Send` type on stable
   (`unsafe impl<T: Send> Ungil for T`, marker.rs:188), carrying that view into
   `py.detach(...)` **compiles** while leaving another thread free to mutate the
   buffer. The clean pattern is to copy prices into an owned `Vec<f64>` before
   detaching (T=17,520 is a 140 KB memcpy, noise against the solve) and let the
   detached closure own its inputs outright. This is exactly the "one gray area"
   the learning plan flagged, and it is worth deriving rather than being handed.

3. **`ColProblem` inverts the build order.** `Problem<ColMatrix>::add_row(bounds)`
   takes bounds only and returns a `Row` handle; the coefficients arrive later
   via `add_column(cost, bounds, &[(Row, f64), ...])` (matrix_col.rs). So all T
   SoC rows must be created first, then the 3T columns. The Python code writes
   rows and columns into the same CSC arrays in one pass, so the port is not a
   line-by-line transcription. Column order still has to be
   `[c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]` because
   `Solution::columns()` returns values in add order and the extraction slices
   depend on it.

4. **Equality rows come from inclusive ranges.** `add_row` takes
   `B: RangeBounds<N>`, and `bound_value` maps `Bound::Unbounded` to
   +/- infinity. Row 0 is `add_row(init..=init)` with `init = initial_soc_mwh`;
   rows 1..T-1 are `add_row(0.0..=0.0)`. A half-open `0.0..0.0` would silently
   be treated as inclusive on both ends (the crate maps `Excluded` and
   `Included` identically), which is right here by luck, not by contract.

5. **Objective value is exposed, so nothing needs recomputing.**
   `SolvedModel::objective_value()` (lib.rs:1103) wraps
   `Highs_getObjectiveValue`. Its doc warns the value "may be zero" if the model
   is not solved, so the `status()` check must come first, matching `lp.py`'s
   order. `Sense::Maximise` is spelled the British way.

6. **The SoC recursion off-by-one is the likeliest silent failure**, exactly as
   the master spec warns. The row for interval t is
   `-eta_c*dt*c_t + (dt/eta_d)*d_t + s_t - s_{t-1} = rhs_t` with
   `rhs_0 = initial_soc_mwh` and `rhs_t = 0` otherwise. Golden 2 (lossless,
   180.0) passes under several wrong recursions; golden 3 (charge_eff 0.8,
   175.0) does not. Build golden 3 early, not last.

7. **M4b implicitly freezes a cross-slice contract the spec never names: the
   Python-visible return shape.** M4c says its wrapper will "call bess_engine,
   assemble DispatchResult", but nothing states whether `optimize_dispatch`
   returns a 5-tuple, a dict, or a `#[pyclass]`. Whatever M4b ships becomes
   M4c's contract. A tuple of
   `(charge, discharge, soc, objective_value, simultaneous_hours)` keeps
   `rust.py` to one unpack line and avoids a `#[pyclass]` whose fields would
   duplicate the frozen `DispatchResult`. Decide it deliberately and document
   it in the PR description so M4c's agent run has something to read.

8. **`solver_status` has no Rust counterpart to return.** `lp.py` only ever
   emits the literal `"optimal"` on the success path (any other status raises),
   so the boundary does not need to hand a status string back; M4c's wrapper can
   hardcode it. Confirm this rather than inventing a status enum crossing the
   FFI line.

9. **The WARNING log has no natural home in Rust.** `lp.py` logs at WARNING when
   `simultaneous_hours > 0` and `tests/test_optimizer_properties.py:119` asserts
   on the `bess.optimizer.lp` logger. The Rust engine should return the count
   and let M4c's `rust.py` emit the warning through Python `logging`; emitting
   it from Rust (via the `log` crate, which `highs` already pulls in) would not
   reach `caplog` and would fail any parity test written against the Python
   logger.

10. **CI build cost is worse than the M4a spec's gotcha 1 states.**
    `highs-sys 1.15.0` defaults to features `["build", "highs_release"]`, so it
    compiles the vendored HiGHS C++ tree via `cmake`, **and** it has a
    build-dependency on `bindgen 0.72`, which needs `libclang`. The M4a spec
    lists cmake and a C++ toolchain but not libclang. If the rust job fails at
    `highs-sys` build with a libclang error, that is an M4a defect, not an M4b
    bug; do not chase it inside this slice.

11. **Degeneracy applies to cargo tests too** (memory:
    `lp-optimizer-degeneracy-in-tests`). Golden 2 at eff 1.0/1.0 has an
    interchangeable charge/discharge pair inside a window; assert the objective
    and the per-window net dispatch sums, mirroring
    `tests/test_optimizer_golden.py:38-46`. Golden 3 is the one case where gross
    dispatch (2.5 MWh in, 2.0 MWh out) is safely assertable.

12. **Criterion 6's infeasible construction needs care.** All columns are
    bounded, so the model cannot be unbounded; infeasibility is the only
    non-optimal status reachable by construction. A test-only helper that sets
    `initial_soc_mwh` above `energy_mwh` with `power_mw = 0.0` makes row 0
    demand `s_0 = 5.0` while `s_0 <= 1.0`, yielding
    `HighsModelStatus::Infeasible`. Note that `#[non_exhaustive]` on that enum
    means any `match` over it needs a `_` arm.

13. **The worktree is current.** `git diff main...HEAD` is empty and the M4
    specs are in history, so the stale-branch pitfall
    (`adw-stale-worktree-branch-dependency-merge`) does not bite here. It will
    become relevant the moment T9's PR merges to main while this branch sits.

### Existing Patterns to Follow

- **Purity mirrors purity.** `lp.py` imports only numpy, highspy, `bess.models`,
  and logging. The Rust core should keep the LP module free of PyO3 types so
  cargo tests run solver-only (criterion 5 requires exactly this), with the
  `#[pyfunction]` as a thin adapter in a separate module.
- **Errors carry the status.** `lp.py` raises
  `RuntimeError(f"HiGHS did not reach an optimal solution: status={...}")`.
  `DispatchError` should carry the `HighsModelStatus` in its `Display` output so
  M4c's error-parity test can assert on key content.
- **Comment the "why", not the "what".** `_build_lp`'s docstring explains why
  CSC arrays are built directly rather than through the high-level API; the
  no-terminal-SoC decision is documented at the call site. Match that density.
- **No em-dashes** anywhere, and no AI-attribution trailer on the commits
  (`CLAUDE.md`, plus the global rule).
- **Runbook bookkeeping**: `specs/TASKS.md` records PR number, merge date, and a
  log-table row per task. T10's row should say the diff was hand-written.

## Recommendations

1. **Do not start until T9 is merged.** `rust/` contains only `.gitkeep`. Every
   M4b acceptance criterion assumes a crate that builds, and criterion 8
   explicitly requires the CI rust job to stay green. Install `maturin` at the
   same time.

2. **Read the vendored crate sources, not the web docs.** `highs 2.4.0`,
   `highs-sys 1.15.0`, `pyo3 0.28.3`, `numpy 0.28.0`, and `thiserror 2.0.19` are
   already unpacked under `~/.cargo/registry/src/index.crates.io-*/`. They are
   the exact pinned versions, they are offline, and they are where the
   `allow_threads` / `detach` discrepancy was caught. `matrix_col.rs` is 176
   lines and is the entire `ColProblem` surface worth knowing.

3. **Order the work solver-first, in this sequence:** column layout on paper
   from memory, then check against `lp.py:118-160`; then golden 3 (lossy, 175.0)
   as the first end-to-end cargo test rather than golden 1, because it is the
   only one that falsifies a wrong SoC recursion; then goldens 1, 2, 4, 5; then
   `DispatchError` and criterion 6; then the boundary. This deviates from the
   spec's suggested working order (golden 1 first) for one reason worth stating
   in the PR: golden 1's objective of 0.0 is satisfied by an engine that returns
   all zeros for any reason at all.

4. **Copy prices into an owned `Vec<f64>` before `py.detach`.** Take
   `PyReadonlyArray1<'py, f64>`, call `.as_array()`, materialize with
   `.to_vec()`, then detach around build plus solve, then `into_pyarray` the
   three owned `Vec<f64>` results (rust-numpy implements `IntoPyArray` for
   `Vec<T>` directly, so no `ndarray::Array1` round trip is needed). Zero-copy
   in is still correct at the extraction step; the copy buys soundness at the
   exact point the GIL is released.

5. **Answer the review gate before writing the PR body, not after.** The three
   questions are the merge blocker. Question 2 ("what breaks if the horizon
   length or SoC bounds change") has a concrete answer worth having ready: the
   last SoC column carries one nonzero rather than two
   (`lp.py:124`), and T=1 collapses the recursion to a single equality row, so
   both are boundary cases the loop structure has to get right without a special
   case leaking in.

6. **Keep the agent in the lane the master spec draws.** Tutoring, concept
   explanation, review of a written diff, and dictation of literal test vectors.
   The five golden price vectors and battery parameters are already transcribed
   above from `tests/test_optimizer_golden.py` and
   `tests/test_optimizer_properties.py:110-117`; that is the full extent of what
   should arrive pre-written.

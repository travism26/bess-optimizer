# ADW Feature Spec: M4, Rust Dispatch Engine (master)

- **Project:** bess-optimizer (public repo, MIT license)
- **Milestone:** M4 of 6
- **Slices:** M4a (specs/M4a_rust_scaffold.md, agent run), M4b (specs/M4b_rust_lp_core.md, HUMAN-WRITTEN, agent tutors only), M4c (specs/M4c_engine_parity_bench.md, agent run); on any conflict this master wins
- **Languages:** Rust (edition 2021+) and Python 3.12
- **Depends on:** M3 merged. Informed by ai_docs/research/learning/rust-learning-plan-m4.md

## Objective

Port `optimize_dispatch` to Rust behind the frozen interface, prove it is a
drop-in replacement via the injected-callable seam built in M1 for exactly
this moment, and benchmark it against the Python implementation. This
milestone has a second, equally weighted goal: Travis learns Rust for real.
The slice structure enforces that: agents scaffold and verify, but the LP
core and the PyO3 boundary are hand-written by Travis with the agent in
tutoring mode only. An agent MUST NOT write the code in M4b's scope even if
asked to "just fix it".

## In scope

1. Rust crate `rust/bess_engine`: LP construction and HiGHS solve mirroring
   `_build_lp`/`optimize_dispatch` in src/bess/optimizer/lp.py, exposed to
   Python via PyO3 + maturin as module `bess_engine`.
2. Thin Python wrapper `src/bess/optimizer/rust.py` exposing
   `optimize_dispatch_rust` with the exact frozen signature of
   `optimize_dispatch`, so it drops into `run_backtest` and
   `run_backtest_rolling` through the existing `optimizer` parameter
   unchanged.
3. `bess backtest --engine python|rust` (default python, both modes).
4. Parity test suite (goldens, fixture month, properties) and a
   `bess bench-engine` command producing an engine comparison JSON plus a
   README M4 section with the speedup table.
5. CI and ADW gates for the Rust toolchain: cargo fmt, clippy, cargo test,
   maturin build, parity tests.

## Out of scope (do not build)

Porting `optimize_dispatch_as` (stays Python; candidate for later), porting
the rolling-horizon loop (only the per-window optimizer callable is Rust),
MILP, wheel distribution or PyPI packaging, free-threaded Python targets,
criterion.rs micro-benchmark suites beyond the budget check, Snowflake/AWS
(M5), dashboard (M6), any change to M1/M2/M3 frozen interfaces.

## Frozen interfaces

Nothing existing changes. M4 adds, and then freezes, the Python-visible
seam:

```python
# src/bess/optimizer/rust.py
def optimize_dispatch_rust(
    prices: np.ndarray,        # $/MWh, shape (T,), may contain negatives
    dt_hours: float,           # 1.0 for hourly
    battery: BatterySpec,
) -> DispatchResult: ...
```

Identical signature, identical semantics, identical error behavior
(non-optimal solver status raises RuntimeError) to `optimize_dispatch`. The
Rust extension module `bess_engine` is an implementation detail behind this
wrapper; nothing outside src/bess/optimizer/rust.py imports it (enforce
with the same AST-based import-confinement pattern used for gridstatus and
highspy).

## Technical decisions (from the research doc; implement as stated)

1. **Solver crate:** `highs` (v2.4.x, safe wrapper over highs-sys), using
   the `ColProblem` builder whose column-wise shape maps onto the existing
   `_build_lp` CSC layout (columns `[c_0..c_{T-1}, d_0..d_{T-1},
   s_0..s_{T-1}]`). Same underlying HiGHS solver as highspy, so golden
   values match to solver tolerance. Do NOT use good_lp (the DSL hides the
   matrix structure) or clarabel (different solver family breaks golden
   parity). Dropping to raw highs-sys CSC arrays is a stretch goal only if
   the benchmark demands it.
2. **Bindings:** PyO3 0.28.x + rust-numpy, versions pinned together.
   `PyReadonlyArray1<f64>` in (zero-copy), `into_pyarray` out, the HiGHS
   build+solve wrapped in `py.allow_threads`.
3. **Errors:** `enum DispatchError` via thiserror with a
   `From<DispatchError> for PyErr` impl mapping to RuntimeError, mirroring
   lp.py's status handling.
4. **simultaneous_hours is computed in Rust** (count of intervals where
   both charge and discharge exceed 1e-3 MW), so the engine is a complete
   port, and the Python wrapper only assembles DispatchResult.
5. **Extension loading:** src/bess/optimizer/rust.py imports bess_engine
   lazily; a missing extension raises a clear error naming
   `maturin develop` as the fix. Parity tests use importorskip so the
   Python-only CI job stays green; the Rust CI job builds the extension
   and runs everything.

## Parity requirements (the correctness bar for the whole milestone)

The M1 Python implementation is the oracle. On identical inputs:

- Objective values match within 1e-6 on all M1 golden cases (criteria 1-4
  and 6 of specs/M1_python_core.md).
- July 2023 fixture: objective within $0.01; BacktestResult metrics via
  `run_backtest(optimizer=optimize_dispatch_rust)` match the Python run
  within the same tolerances the M2 equivalence golden uses.
- Per-interval dispatch arrays are NOT asserted equal: the LP optimum is
  often degenerate and HiGHS may return a different vertex (memory:
  lp-optimizer-degeneracy-in-tests). Assert objective, feasibility
  residuals, and derived metrics instead.
- All M1 acceptance-criterion-5 properties hold on the Rust results.

## Config and CLI

No config.toml additions. `--engine python|rust` on `bess backtest`
(default python; rolling mode accepts it too since the seam passes
through). `bess bench-engine --config config.toml` runs both engines on a
synthetic T=17,520 horizon plus the fixture month, writes
engine_benchmark.json (wall times, objectives, speedup; document the
wall-time fields as non-deterministic per the established convention).

## Acceptance criteria (rollup; slices carry the detail)

M4a: crate scaffolds and builds, hello-world extension callable from the
venv, CI rust job green (fmt, clippy -D warnings, cargo test, maturin
develop, pytest), adw_gates.json extended, import-confinement guard covers
bess_engine, Python-only path still green with the extension absent.

M4b (human): all five golden cases pass as cargo tests against the
hand-written core, DispatchError maps to RuntimeError, the PyO3 boundary
round-trips from Python, and the PR description contains the three
review-gate answers (see Learning protocol below).

M4c: full parity suite green both engines, `--engine rust` end to end on
fixtures for both modes, bench-engine JSON + README M4 section with the
speedup table, T=17,520 Rust solve comfortably under the 30 s M1 budget.

## Learning protocol (binding for M4b, recommended elsewhere)

1. Agent tutors, never authors, inside M4b's scope: explain concepts,
   review Travis's drafts, answer "why does the borrow checker reject
   this"; do not produce the implementation, even on request mid-session.
2. Compiler errors: Travis reads and attempts every rustc/clippy error
   himself first (5-10 minutes) before asking the agent, for at least the
   first two weeks (per the Anthropic RCT findings in the research doc).
3. Review gate: before the M4b PR merges, Travis answers three questions
   in the PR description without looking at the diff: what each function
   does and why that way, what breaks if the horizon length or SoC bounds
   change, and which line he would have gotten wrong writing it alone.

## Known gotchas

1. **Degenerate optima:** never compare dispatch arrays across engines;
   the goldens with strict optima (lossy efficiency) are the only places
   exact dispatch is checkable.
2. **highs-sys builds HiGHS from source:** the build needs a C++
   toolchain; CI must install it and cache the cargo build directory or
   the rust job will dominate CI time.
3. **Version skew:** PyO3 and rust-numpy must be pinned as a compatible
   pair; maturin resolves the ABI. Pin exact versions in Cargo.toml.
4. **rust/target/ is already gitignored;** keep Cargo.lock TRACKED (this
   is an application-shaped crate, not a published library).
5. **The M1 no-terminal-SoC convention and end-of-interval SoC semantics
   must port exactly;** off-by-one in the SoC recursion rows is the
   likeliest silent parity failure, and the lossy step golden (175.0)
   catches it while the lossless one (180.0) may not.

## Definition of done

All three slices merged, parity suite green in CI on both the Python-only
and Rust jobs, ruff + mypy + fmt + clippy clean, README M4 section live
with the speedup table and a one-paragraph honest note on what was
hand-written vs delegated, no frozen interface changed, Cargo.lock
committed, no secrets or data files in history.

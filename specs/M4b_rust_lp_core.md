# Spec: M4b, Rust LP Core (HUMAN-WRITTEN, not an ADW run)

- **Repo:** bess-optimizer
- **Master spec:** specs/M4_rust_engine.md (decisions and the Learning protocol live there; the protocol is BINDING for this slice)
- **Depends on:** M4a merged (compiling crate, CI, gates).
- **Author:** Travis, by hand, agent in tutoring mode only. This spec is a
  checklist and acceptance bar for a person, not a pipeline prompt.
- **Implements:** the LP builder, solve, and result extraction in
  rust/bess_engine; DispatchError; the #[pyfunction] optimize_dispatch
  boundary; cargo golden tests

## Objective

Hand-write the port of `_build_lp` + `optimize_dispatch` (from
src/bess/optimizer/lp.py) to Rust against the highs crate, and the PyO3
boundary that exposes it. This is the learning core of M4: the LP
construction forces ownership and borrowing, the boundary forces the
numpy/Rust memory model, and the error enum forces trait impls and `?`
propagation. The Python file is the correctness oracle, always a few lines
away.

## Scope for the human author

1. LP builder: columns [c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}], SoC
   recursion rows, bounds, maximize objective, via highs ColProblem.
   Mirror the M1 formulation exactly: no terminal SoC constraint,
   end-of-interval SoC semantics, negative prices pass through.
2. Solve + extraction: assert optimal status, extract the three arrays,
   objective, and count simultaneous_hours (both legs > 1e-3 MW) in Rust.
3. `enum DispatchError` (thiserror) with From<DispatchError> for PyErr
   mapping to RuntimeError, matching lp.py's semantics.
4. `#[pyfunction] optimize_dispatch`: PyReadonlyArray1<f64> prices in,
   battery params as plain floats (the wrapper unpacks BatterySpec),
   allow_threads around build+solve, into_pyarray for the outputs,
   PyResult return.
5. Cargo tests for the golden cases (listed below), solver-only, no
   Python in the loop.

Delegable within this slice (agent may author): none of the above. The
agent may author nothing in this slice. Rubber ducking, concept
explanations, and post-hoc review of Travis's diffs are the allowed modes.
Test-fixture data entry (typing out the 24-element price vectors) may be
dictated to the agent as literal data only.

## Acceptance criteria

Golden values from specs/M1_python_core.md, as `cargo test`, all within
1e-6:

1. Flat prices (T=24, all $50, eff 0.9/0.9): objective == 0.0. Assert
   zero revenue, not zero dispatch.
2. Step lossless (1 MW / 2 MWh, eff 1.0): objective == 180.0.
3. Step lossy charge (charge_eff 0.8): objective == 175.0. This is the
   test that catches SoC-recursion off-by-ones; treat a failure here as
   a formulation bug, not a tolerance issue.
4. Negative price hour (eff 0.9/0.9): objective == 50.0.
5. Simultaneous charge/discharge case (deep negative price, full
   battery): simultaneous_hours > 0, reported not raised.
6. Non-optimal status path: an infeasible construction (e.g. forced via
   contradictory bounds in a test-only helper) surfaces DispatchError and,
   through the boundary, RuntimeError in Python.
7. Boundary smoke: after maturin develop, calling bess_engine's
   optimize_dispatch from a Python REPL on golden 2's inputs returns
   arrays of the right shape and 180.0.
8. cargo fmt, clippy -D warnings, cargo test all green; CI rust job stays
   green.

## Review gate (merges are blocked on this, self-enforced)

The PR description must contain, written without looking at the diff:

1. What each function does and why it is shaped that way.
2. What breaks if the horizon length or the SoC bounds change.
3. The one line you would have gotten wrong writing it alone.

## Suggested working order (from the research doc, not binding)

Week-2 pattern: re-derive the column layout from memory, check against
lp.py, then build golden 1 end to end solver-only before touching PyO3.
Add the boundary only after goldens 1-5 pass in pure Rust. Budget: 6-8
hours for the LP core, 6-8 for the boundary and error handling.

## Definition of done

All 8 criteria green, review gate answered in the PR description, the
diff authored by Travis (agent contributions limited to dictated literal
test data), no changes outside rust/bess_engine except recording progress
in specs/TASKS.md.

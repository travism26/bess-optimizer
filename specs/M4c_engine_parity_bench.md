# ADW Feature Spec: M4c, Engine Parity, CLI, and Benchmarks

- **Repo:** bess-optimizer
- **Master spec:** specs/M4_rust_engine.md (parity requirements live there; on any conflict the master wins)
- **Depends on:** M4a AND M4b merged (a working, golden-passing Rust engine).
- **Implements:** completing src/bess/optimizer/rust.py, the `--engine` flag, tests/test_engine_parity.py, `bess bench-engine`, README M4 section

## Objective

Prove the Rust engine is a drop-in replacement and publish the numbers.
The M1 Python implementation is the oracle; the M1 `optimizer` callable
seam is the socket; this slice supplies the plug, the test harness around
it, and the benchmark story.

## In scope

1. Complete `optimize_dispatch_rust` in src/bess/optimizer/rust.py:
   unpack BatterySpec, call bess_engine, assemble DispatchResult. Frozen
   signature per the master; behavior-identical error semantics.
2. `bess backtest --engine python|rust` (default python), accepted in
   both perfect and rolling modes, threaded through the existing
   `optimizer` parameter. Metrics JSON gains an additive `engine` field.
   Qualified output filenames include the engine only when rust (existing
   filenames stay byte-stable for the default path).
3. `tests/test_engine_parity.py` implementing the master's parity
   requirements, with importorskip so the Python-only CI job skips it.
4. `bess bench-engine --config config.toml`: both engines on a synthetic
   T=17,520 horizon and the July 2023 fixture; writes
   engine_benchmark.json (per-engine wall time, objective, speedup;
   wall-time fields documented as the non-deterministic exception).
5. README M4 section: the speedup table, the parity statement (what is
   asserted equal and what is deliberately not, with the degeneracy
   explanation), and the hand-written vs delegated note per the master's
   definition of done.

## Out of scope

Any edit inside rust/bess_engine beyond what parity failures strictly
require (and any such fix must be reviewed by Travis under the master's
Learning protocol before merge), porting optimize_dispatch_as, rolling
loop internals, wheels/distribution, criterion.rs, plots changes.

## Acceptance criteria

1. **Golden parity:** M1 criteria 1-4 and 6 pass with
   optimize_dispatch_rust substituted, objectives within 1e-6 of the
   Python values.
2. **Fixture parity:** July 2023, default battery:
   run_backtest(optimizer=optimize_dispatch_rust) objective within $0.01
   of Python; every BacktestResult metric within the M2 equivalence
   tolerances. Dispatch arrays are NOT compared (degenerate optima).
3. **Property parity:** all M1 criterion-5 properties hold on the Rust
   results (SoC bounds, dynamics residual < 1e-6, revenue recompute
   within 1e-4, power bounds).
4. **Rolling drop-in:** run_backtest_rolling with the Rust engine on the
   fixture: SoC continuity holds, dominance vs Python-perfect holds, and
   the M2a equivalence golden passes with rolling-perfect matching the
   Rust full-horizon objective within $0.01.
5. **Error parity:** the non-optimal path raises RuntimeError from both
   engines with comparable messages (assert type and key content, not
   exact strings).
6. **CLI:** `--engine rust` end to end on fixtures in both modes writes
   metrics JSON with the engine field; default-path filenames and
   contents are byte-identical to pre-M4 runs (excluding the documented
   wall-time field).
7. **Runtime:** Rust T=17,520 solve completes comfortably under the M1
   30 s budget; record both engines' times. If Rust is not at least at
   parity with Python, that is a finding to report in the README, not
   hide (the honest-numbers convention).
8. **bench-engine:** JSON written, deterministic after key sorting
   excluding wall-time fields; two consecutive runs agree.
9. **CI:** python job green with parity tests skipped; rust job green
   with them run. No network anywhere.
10. **README:** M4 section live with the real speedup table and the
    hand-written vs delegated paragraph.

## Gotchas

1. Do not "fix" cross-engine dispatch differences: degenerate vertices
   are expected (memory: lp-optimizer-degeneracy-in-tests). Only
   objective, residuals, and metrics are comparable.
2. Wall-time fields are the only intentional non-determinism (memory:
   determinism-tests-exclude-wallclock-fields); keep the bench JSON
   writer consistent with the metrics writer's documented convention.
3. The default engine's output filenames must not change: M2b's capture
   rates and M3c's uplift read them (memory:
   metrics-json-unqualified-filename-collision cuts both ways).
4. Benchmark in --release; a debug-build benchmark would understate Rust
   by an order of magnitude and produce a nonsense README table.

## Definition of done

All 10 criteria green in CI (both jobs), ruff/mypy/fmt/clippy clean,
README M4 section live with real numbers, no frozen interface changed,
rust/bess_engine untouched unless a parity failure strictly required it
and Travis reviewed the fix.

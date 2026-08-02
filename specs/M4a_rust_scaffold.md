# ADW Feature Spec: M4a, Rust Crate Scaffold and Toolchain Wiring

- **Repo:** bess-optimizer
- **Master spec:** specs/M4_rust_engine.md (decisions live there; on any conflict the master wins)
- **Depends on:** M3 merged. Manual pre-step for Travis (harness side, not this repo): re-run the ADW command tailoring for Rust in the private harness repo.
- **Implements:** rust/bess_engine crate scaffold, maturin wiring, CI rust job, adw_gates.json extension, src/bess/optimizer/rust.py loader stub, tests/test_rust_scaffold.py

## Objective

Give M4b a compiling, CI-green foundation so Travis's hand-written work
starts at the LP logic, not at build plumbing. Everything in this slice is
deliberately boilerplate: cargo/maturin config, CI, gates. Zero LP logic.
The hello-world function proves the whole PyO3 -> maturin -> venv -> pytest
round trip once, on something trivial, before it matters.

## In scope

1. `rust/bess_engine/`: cargo crate (edition 2021+), PyO3 0.28.x +
   rust-numpy pinned as a compatible pair, thiserror, highs 2.4.x declared
   (unused for now), maturin build config. Cargo.lock committed.
2. One placeholder `#[pyfunction]` `engine_info()` returning a dict with
   crate version and HiGHS version string: enough to prove linking against
   highs-sys works, without any LP code. A stub `optimize_dispatch` entry
   point must NOT be created; M4b owns that name from the start.
3. `src/bess/optimizer/rust.py`: lazy import of bess_engine with a clear
   ImportError message naming `uvx maturin develop` (or the equivalent
   documented command) as the fix; `engine_available() -> bool` helper;
   `optimize_dispatch_rust` declared with the frozen signature raising
   NotImplementedError until M4b/M4c wire it.
4. CI: a separate `rust` job (stable toolchain, C++ compiler present,
   cargo caching) running cargo fmt --check, cargo clippy -D warnings,
   cargo test, maturin develop, then the full pytest suite. The existing
   python job stays untouched and must stay green with no extension built.
5. adw_gates.json gains fmt/clippy/cargo-test gates with explicit
   --manifest-path rust/bess_engine/Cargo.toml so gates work from the repo
   root worktree.
6. Import confinement: extend the AST guard so bess_engine is imported
   only inside src/bess/optimizer/rust.py.
7. `tests/test_rust_scaffold.py`: skips cleanly when the extension is
   absent; when present, asserts engine_info() returns the expected keys.
8. Dev dependency: maturin added to the dev group in pyproject.toml.

## Out of scope

Any LP construction, solving, or numpy array handling beyond the
hello-world dict (all M4b); parity tests, --engine flag, benchmarks (all
M4c); publishing config, wheels, abi3 tuning beyond what maturin defaults
to; touching src/bess/optimizer/lp.py.

## Acceptance criteria

1. `cargo build`, `cargo test`, `cargo fmt --check`, and
   `cargo clippy -- -D warnings` all pass in rust/bess_engine.
2. `maturin develop` installs bess_engine into the active venv;
   `python -c "import bess_engine; print(bess_engine.engine_info())"`
   prints the version dict, proving the highs-sys link.
3. With NO extension built (fresh venv): `uv run pytest` is green
   (scaffold test skips with a clear reason), `uv run ruff check .` and
   `uv run mypy` pass. The Python-only path must not degrade.
4. CI: the new rust job is green end to end including the pytest run with
   the extension present; the python job is green without it; cargo build
   caching keeps the rust job under ~10 minutes.
5. adw_gates.json parses and all gates pass from the repo root.
6. The import-confinement test fails if bess_engine is imported anywhere
   outside src/bess/optimizer/rust.py (prove with a doctored-file test,
   same technique as the gridstatus guard).
7. calling `optimize_dispatch_rust` today raises NotImplementedError with
   a message pointing at M4b/M4c.
8. No test touches the network.

## Gotchas

1. highs-sys compiles HiGHS from source: the CI image needs cmake and a
   C++ toolchain; cache ~/.cargo and rust/bess_engine/target keyed on
   Cargo.lock or the job will take 15+ minutes every run.
2. PyO3/rust-numpy version pairing is strict; pin exact versions, do not
   use loose carets that let the pair drift apart.
3. The extension module name (bess_engine) must match the crate lib name
   or maturin produces an unimportable wheel; set [lib] name explicitly.
4. Gates run in ADW worktrees under trees/<adw-id>/: use --manifest-path
   relative to the repo root, never cd.

## Definition of done

All 8 criteria green (CI proves 1-4), ruff/mypy/fmt/clippy clean, gates
extended, Cargo.lock committed, no LP logic anywhere in the crate, no
frozen interface changed.

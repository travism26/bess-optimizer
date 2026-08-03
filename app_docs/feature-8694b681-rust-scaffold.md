# Rust Crate Scaffold and Toolchain Wiring (M4a)

**ADW ID:** 8694b681
**Date:** 2026-08-02
**Specification:** specs/M4a_rust_scaffold.md

## Overview

M4 ports `optimize_dispatch` to Rust behind the frozen interface, but M4b
(the hand-written LP core) needs a compiling crate and green CI to start from
the LP logic instead of build plumbing. This slice adds that plumbing only:
the `rust/bess_engine` cargo crate, maturin wiring, a `hello world`
`#[pyfunction]` that proves the PyO3 -> maturin -> venv -> pytest round trip
and the highs-sys native link, a lazy-loading Python wrapper, CI, and gates.
Zero LP logic, and no `optimize_dispatch` entry point: M4b owns that name
from the start.

## What Was Built

- `rust/bess_engine/`: a cargo crate (edition 2021) with `engine_info()`, a
  `#[pyfunction]` returning `{"crate_version": ..., "highs_version": ...}`,
  proving the highs-sys link without any LP code. `Cargo.lock` is committed
  (this is an application-shaped crate, not a published library).
- `src/bess/optimizer/rust.py`: lazy `import bess_engine` with a clear
  `ImportError` naming the `maturin develop` fix, `engine_available() ->
  bool`, and `optimize_dispatch_rust` with the frozen signature, raising
  `NotImplementedError` naming M4b/M4c.
- `tests/test_rust_scaffold.py`: an extension-gated test for `engine_info()`
  (skips cleanly when the extension is absent), an ungated
  `NotImplementedError` test, and an AST-based import-confinement guard
  (plus a doctored-file proof) restricting `bess_engine` imports to
  `optimizer/rust.py`.
- A new `rust` CI job (fmt, clippy, cargo test, maturin develop, then the
  full pytest suite with the extension present); the existing `checks` job
  is untouched and stays green with no extension built.
- `adw_gates.json` gains `rust-fmt`, `rust-clippy`, and `rust-test`, all
  `--manifest-path`-qualified so they run correctly from the repo root.
- `maturin` added to the dev dependency group; `bess_engine` added to the
  mypy stub-less-module overrides alongside `gridstatus.*`/`highspy.*`.

## Technical Implementation

### Files Modified

- `rust/bess_engine/Cargo.toml` (new): `pyo3 = "0.28.3"`, `numpy = "0.28.0"`
  (pinned as a compatible pair), `highs = "2.4.0"`, `highs-sys = "1.15"`
  (direct dependency, since the safe `highs` crate does not re-export
  `highs_sys`), `thiserror = "2.0.19"` (declared for M4b, unused here). No
  `pyo3/extension-module` cargo feature is declared.
- `rust/bess_engine/src/lib.rs` (new): `engine_info()`, a private
  `highs_version()` helper wrapping the single `unsafe` FFI call to
  `highs_sys::Highs_version()`, the `#[pymodule]` registration, and a
  `#[cfg(test)]` test.
- `rust/.gitkeep` deleted (the crate now exists).
- `src/bess/optimizer/rust.py` (new): `_load_engine`, `engine_available`,
  `optimize_dispatch_rust`.
- `tests/test_rust_scaffold.py` (new).
- `pyproject.toml`: `maturin>=1.7` in `[dependency-groups] dev`; `bess_engine`
  added to the `ignore_missing_imports` mypy override.
- `uv.lock`: regenerated for the `maturin` addition.
- `.github/workflows/ci.yml`: new `rust` job.
- `adw_gates.json`: three new gates.
- `.gitignore`: `rust/target/` (which did not match
  `rust/bess_engine/target/`) replaced with `rust/**/target/`; added
  `*.so`, `*.pyd`, `*.dylib`.
- `README.md`: one line in "Quick start" pointing at `maturin develop`.

### Key Changes

- **No `pyo3/extension-module` cargo feature.** Declaring it unconditionally
  breaks `cargo build`/`cargo test` linking on macOS (`ld: symbol(s) not
  found`), and the usual `.cargo/config.toml` workaround is resolved from the
  process's current working directory, so it silently does not apply when
  gates invoke cargo from the repo root via `--manifest-path`. maturin sets
  `PYO3_BUILD_EXTENSION_MODULE=1` itself when it builds the wheel, so plain
  cargo commands link against libpython (fine for `cargo test`) while
  `maturin develop` still produces a correct, importable extension.
- **Direct `highs-sys` dependency for the version string.** The safe `highs`
  crate wraps `highs_sys` privately and does not re-export it; `engine_info`
  needs the raw FFI call to prove the native link rather than just echoing
  `CARGO_PKG_VERSION` for both fields.
- **The import-confinement guard cannot skip itself.** Only the
  `engine_info()` test is gated on `engine_available()`; the AST sweep and
  its doctored-file proof always run, so criterion 6 (catches offenders)
  and criterion 3 (green with no extension) do not conflict.
- **mypy needs a cast, not just an override.** The `ignore_missing_imports`
  override silences `import-not-found` for `bess_engine`, but
  `warn_return_any` still flags `_load_engine`'s `return bess_engine` (typed
  `Any` off a stub-less import) against its declared `ModuleType` return
  type; fixed with `cast(ModuleType, bess_engine)`.

## Usage

```bash
uv run maturin develop --manifest-path rust/bess_engine/Cargo.toml
uv run python -c "import bess_engine; print(bess_engine.engine_info())"
# {'crate_version': '0.1.0', 'highs_version': '1.15.0'}
```

Without the extension built, `bess.optimizer.rust.engine_available()` returns
`False` and `optimize_dispatch_rust(...)` raises `NotImplementedError`; the
Python-only path (`optimize_dispatch` in `src/bess/optimizer/lp.py`) is
completely unaffected.

## Configuration

No `config.toml` additions. The three new ADW gates:

```json
{ "name": "rust-fmt", "command": "cargo fmt --manifest-path rust/bess_engine/Cargo.toml -- --check" }
{ "name": "rust-clippy", "command": "cargo clippy --manifest-path rust/bess_engine/Cargo.toml --all-targets -- -D warnings" }
{ "name": "rust-test", "command": "cargo test --manifest-path rust/bess_engine/Cargo.toml" }
```

## Testing

```bash
cargo fmt --manifest-path rust/bess_engine/Cargo.toml -- --check
cargo clippy --manifest-path rust/bess_engine/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/bess_engine/Cargo.toml
uv run maturin develop --manifest-path rust/bess_engine/Cargo.toml
uv run pytest       # green both with and without the extension built
uv run ruff check .
uv run mypy
```

## Notes

- Zero LP construction, solving, or numpy array handling beyond the
  hello-world dict; `src/bess/optimizer/lp.py` was not touched.
- No frozen interface (`BatterySpec`, `DispatchResult`, `BacktestResult`,
  `optimize_dispatch`, `fetch_da_prices`, `run_backtest`) changed.
- `optimize_dispatch` was deliberately NOT created in the crate: M4b owns
  that name, `DispatchError`, and the PyO3 boundary from the start.

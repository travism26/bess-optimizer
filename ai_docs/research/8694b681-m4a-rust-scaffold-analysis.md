# Research: M4a Rust Crate Scaffold and Toolchain Wiring

## Metadata

adw_id: `8694b681`
prompt: `specs/M4a_rust_scaffold.md`
date: `2026-08-02`

## Executive Summary

M4a is pure build plumbing with zero LP logic, so the risk is entirely in
the toolchain, not the algorithm. I prototyped the complete chain in /tmp
(cargo crate, pyo3 0.28.3 + numpy 0.28.0 + highs 2.4.0 + highs-sys 1.15.0 +
thiserror 2.0.19, maturin 1.14.1 develop into the repo's own `.venv`) and
the round trip works end to end: `bess_engine.engine_info()` returned
`{'crate_version': '0.1.0', 'highs_version': '1.15.0'}`, which proves the
highs-sys native link. All four cargo gates plus `maturin develop` run
correctly from the repo root with `--manifest-path`, satisfying gotcha 4.

Three concrete problems the spec does not anticipate, all validated by
running them: (1) declaring `pyo3/extension-module` as a cargo feature
breaks `cargo build` and `cargo test` on macOS with `ld: symbol(s) not
found`, and the usual `.cargo/config.toml` workaround is resolved relative
to the current working directory, so it silently does not apply to a
repo-root `--manifest-path` invocation; the fix is to not declare the
feature at all and let maturin set `PYO3_BUILD_EXTENSION_MODULE=1` itself.
(2) The safe `highs` crate does not re-export `highs_sys`, so `engine_info()`
needs a direct `highs-sys` dependency and one `unsafe` block. (3)
`.gitignore` line 28 is `rust/target/`, which does not match
`rust/bess_engine/target/`; verified with `git check-ignore`.

Good news on the CI budget: a genuinely cold build (target/ deleted,
libhighs.a compiled from source) took 20.6 s wall and 108 CPU-seconds on a
12-core M-series Mac. The spec's "15+ minutes every run" fear is
substantially overstated; caching is still worth doing, but the ~10 minute
budget is not in danger.

## Existing Architecture

### Relevant Documentation Found

| Doc | What it contains |
| --- | --- |
| `specs/M4_rust_engine.md` (167 lines) | Master spec. Technical decisions 1-5 (highs crate ColProblem, PyO3 0.28.x + rust-numpy pinned together, thiserror DispatchError, simultaneous_hours computed in Rust, lazy extension loading), parity requirements, the binding Learning protocol, known gotchas. |
| `specs/M4a_rust_scaffold.md` (87 lines) | This slice. 8 in-scope items, 8 acceptance criteria, 4 gotchas. |
| `specs/M4b_rust_lp_core.md` (89 lines) | The human-written slice. Important as a scope fence: M4b owns the `optimize_dispatch` name, `DispatchError`, and the `#[pyfunction]` boundary from the start. |
| `specs/M4c_engine_parity_bench.md` (97 lines) | Owns `optimize_dispatch_rust`'s body, the `--engine` flag, parity tests, `bench-engine`, README M4 section. |
| `ai_docs/research/learning/rust-learning-plan-m4.md` (138 lines) | Where the crate choices came from. Names `highs` v2.4.0 wrapping `highs-sys` ^1.14.3, PyO3 0.28.x + maturin 1.8.x, and lists Cargo/maturin scaffolding as fully delegable. Contains no CI YAML, no caching keys, no gate command lines, no wrapper design. |
| `CLAUDE.md` (lines 20-33, 76-89) | CI must stay green on ruff/mypy/pytest; frozen interfaces; no network in tests; no em-dashes; no AI-attribution trailer. |
| `specs/TASKS.md` (T9 entry) | M4a is T9, one task = one spec = one run = one PR. Manual pre-step (private harness repo) is re-tailoring the ADW commands for Rust. |
| `ai_docs/memory/entries/` (17 entries) | `ast-based-import-confinement-guard`, `highspy-untyped-mypy`, and `adw-worktree-port-file-cleanup` are all directly load-bearing here. |

### Component Map

```
                    frozen seam, unchanged by M4a
                                |
 bess.cli ──► bess.backtest.runner.run_backtest(optimizer=...)  ──┐
          └─► bess.backtest.rolling.run_backtest_rolling(...)   ──┤
                                                                  │
                                        Callable[..., DispatchResult]
                                                                  │
                        ┌─────────────────────────────────────────┴──────┐
                        │                                                │
        src/bess/optimizer/lp.py                    src/bess/optimizer/rust.py   NEW (M4a)
        optimize_dispatch  (the oracle)             optimize_dispatch_rust  -> NotImplementedError
        imports: numpy, highspy, bess.models        engine_available() -> bool
                                                    lazy `import bess_engine`
                                                                │
                                            only module allowed to import bess_engine
                                                                │
                                          rust/bess_engine/  NEW (M4a)
                                          #[pymodule] bess_engine
                                          engine_info() -> dict   (M4a, hello world)
                                          optimize_dispatch        (M4b, NOT M4a)
                                                                │
                                          highs 2.4.0 ──► highs-sys 1.15.0 ──► libhighs.a
                                                                                (built from source, cmake + bindgen)
```

Build/verify plane:

```
adw_gates.json  ──►  ruff / mypy / pytest          (existing, 3 gates)
                └──►  cargo fmt / clippy / test     (M4a adds, all with --manifest-path from repo root)

.github/workflows/ci.yml
  job `checks`  ── python only, extension absent, scaffold test SKIPS      (must stay untouched)
  job `rust`    ── NEW: toolchain, cmake/C++, cache, fmt, clippy, test,
                        maturin develop, then full pytest with extension PRESENT
```

### Key Files and Modules

- `src/bess/optimizer/lp.py` (179 lines): the oracle. `optimize_dispatch` and `_build_lp`. M4a must not touch it (spec "Out of scope").
- `src/bess/optimizer/__init__.py` (1 line): docstring only, no re-exports. Nothing to add here.
- `src/bess/models.py` (138 lines): `BatterySpec`, `DispatchResult`, `BacktestResult` frozen dataclasses. `rust.py` imports `BatterySpec` and `DispatchResult` for its signature.
- `src/bess/backtest/runner.py` (157 lines) and `rolling.py` (233 lines): the `optimizer: Callable[..., DispatchResult] = optimize_dispatch` seam, already in place since M1c. M4a does not wire into it; M4c does.
- `tests/test_optimizer_properties.py` lines 145-171: `_top_level_import_modules(path)` plus the purity allowlist assertion. The exact AST helper to copy.
- `tests/test_data.py` lines 203-225: `_imports_gridstatus(path)` plus `test_gridstatus_import_confined_to_data_modules`, which walks `src_root.rglob("*.py")` and asserts `offenders == []`. The confinement pattern to mirror.
- `tests/conftest.py` (40 lines): autouse socket block, `manual` marker exemption. Applies automatically to any new test file; nothing to add for criterion 8.
- `.github/workflows/ci.yml` (30 lines): single `checks` job, `uv sync --locked`, ruff, mypy, pytest.
- `adw_gates.json` (7 lines): three gates, all `uv run ...`.
- `pyproject.toml` (68 lines): hatchling backend, `packages = ["src/bess"]`, mypy `files = ["src", "tests"]` with `warn_return_any`, and an existing `[[tool.mypy.overrides]]` for `gridstatus.*` / `highspy.*`.
- `.gitignore` (48 lines): line 28 is `rust/target/`. No `*.so` / `*.pyd` / `*.dylib` entries anywhere.
- `rust/` currently holds only `rust/.gitkeep`.

## Affected Areas

### Files That Will Need Changes

| File | Change |
| --- | --- |
| `rust/bess_engine/Cargo.toml` | **New.** `[lib] name = "bess_engine"`, `crate-type = ["cdylib", "rlib"]`, edition 2021, exact pins for pyo3/numpy/highs/highs-sys/thiserror. Do NOT declare a `pyo3/extension-module` feature (see risk 1). |
| `rust/bess_engine/Cargo.lock` | **New, tracked** (master gotcha 4: application-shaped crate). |
| `rust/bess_engine/src/lib.rs` | **New.** `#[pymodule] fn bess_engine`, one `#[pyfunction] engine_info`, a private `highs_version()` helper with the single `unsafe` FFI call, and a `#[cfg(test)]` module so `cargo test` has something to run. No `optimize_dispatch`. |
| `rust/bess_engine/pyproject.toml` | **Optional.** maturin builds fine from Cargo.toml alone (verified). Add it only if you want `[tool.maturin]` config; if added, it must NOT be picked up by the root hatchling build. |
| `rust/.gitkeep` | Delete once the crate exists. |
| `src/bess/optimizer/rust.py` | **New.** Lazy import, `engine_available() -> bool`, `optimize_dispatch_rust` with the frozen signature raising `NotImplementedError` naming M4b/M4c. |
| `tests/test_rust_scaffold.py` | **New.** Extension-present test (skipped when absent), the `bess_engine` confinement guard (must NOT be skipped when absent), the doctored-file proof, and the `NotImplementedError` assertion. |
| `pyproject.toml` | `maturin` into `[dependency-groups] dev`; a new `[[tool.mypy.overrides]]` entry for `bess_engine` (see risk 4). |
| `uv.lock` | Regenerated by adding maturin. CI runs `uv sync --locked`, so a stale lock fails the python job. |
| `.github/workflows/ci.yml` | Add a `rust` job. Leave `checks` byte-identical. |
| `adw_gates.json` | Add `rust-fmt`, `rust-clippy`, `rust-test` gates, each with `--manifest-path rust/bess_engine/Cargo.toml`. |
| `.gitignore` | Fix `rust/target/` so it covers `rust/bess_engine/target/`; add `*.so`, `*.pyd`, `*.dylib` (see risk 3). |
| `specs/TASKS.md` | Tick T9, record the PR number and adw id in the Log table. |
| `README.md` | Optional but recommended: one line in `## Quick start` for the Rust toolchain / `maturin develop`. The M4 results section itself belongs to M4c. |
| `app_docs/feature-8694b681-rust-scaffold.md` | **New**, per the established doc convention. |

### Dependencies

What M4a depends on:
- Nothing in `src/bess` at runtime. `rust.py` imports only `numpy` and `bess.models` at module level, plus `bess_engine` lazily.
- Rust toolchain, a C++ compiler, cmake, and libclang (bindgen) at build time.

What depends on M4a:
- M4b needs a compiling crate and green CI to start at the LP logic.
- M4c needs `optimize_dispatch_rust`, `engine_available()`, and the CI rust job to exist.
- Nothing in M1/M2/M3 depends on M4a. With the extension absent, the Python path is unchanged (verified: `uv run pytest -q` is green, 117 tests, ~26 s).

Verified dependency graph (crates.io, queried 2026-08-02):

| Crate | Latest | Resolves to | Notes |
| --- | --- | --- | --- |
| `pyo3` | 0.29.1 | pin `0.28.3` | Master spec says 0.28.x. |
| `numpy` (rust-numpy) | 0.29.0 | pin `0.28.0` | `numpy` 0.28.0 requires `pyo3 ^0.28.0`; `numpy` 0.29.0 requires `pyo3 ^0.29.0`. That is the strict pairing the spec warns about, and it resolves cleanly. |
| `highs` | 2.4.0 | `2.4.0` | Depends on `highs-sys ^1.14.3` and `log ^0.4.27`. |
| `highs-sys` | 1.15.0 | `1.15.0` | `^1.14.3` resolves UP to 1.15.0. Build deps: `bindgen ^0.72`, optional `cmake ^0.1.49`, optional `pkg-config`. Default features `["build", "highs_release"]`, so cmake is on and HiGHS is compiled in Release mode. No `links` key. |
| `thiserror` | 2.0.19 | pin `2.0.x` | Declared for M4b; unused in M4a, which trips `unused_crate_dependencies` only if that lint is enabled (it is not by default). |
| `maturin` (PyPI) | 1.14.1 | dev group | The learning plan's "1.8.x" is stale by six minor versions. |

### Integration Points

1. **The optimizer callable seam** (`runner.py:57`, `rolling.py:114`, `as_runner.py:110`): untouched by M4a. `optimize_dispatch_rust` only needs the exact signature `(prices: np.ndarray, dt_hours: float, battery: BatterySpec) -> DispatchResult` so M4c can drop it in.
2. **The venv**: `maturin develop` installs `bess_engine` into whatever venv `VIRTUAL_ENV` points at. In this repo that is `.venv`, already gitignored.
3. **CI**: two jobs sharing one repo. The python job must remain a valid proof that the Python-only path works, so it must never build the extension.
4. **ADW gates**: `adw_gates.json` is consumed by the private harness and runs from the worktree root (`trees/<adw-id>/`). Every cargo gate must be root-relative.
5. **The tailored ADW commands** (`.claude/commands/validate.md`, `test.md`): these are tracked in THIS repo and are currently Python-only (`/validate` runs mypy, `ruff format --check`, `ruff check`). The M4a spec says the re-tailoring is "harness side, not this repo", so M4a should leave them alone, but be aware they will be stale until that pre-step regenerates them.

## Prototype Results (run during this research, throwaway crates under /tmp)

Everything below was executed, not inferred.

| Check | Result |
| --- | --- |
| `highs` 2.4.0 solves a trivial LP | Optimal, `columns() == [4.0]` |
| `highs_sys::Highs_version()` via `CStr::from_ptr` | `"1.15.0"` |
| `highs` crate re-exports `highs_sys`? | **No.** `src/lib.rs:118` does a private `use highs_sys::*;`; the only `pub use` lines are matrix/options/status types. A direct `highs-sys` dependency is required for the version string. |
| `cargo test` with `pyo3/extension-module` enabled unconditionally | **FAILS** on macOS: `ld: symbol(s) not found for architecture arm64`, `__Py_NoneStruct` and friends undefined |
| `cargo build` with `pyo3/extension-module` enabled unconditionally | **FAILS**, same linker error |
| Same, plus `.cargo/config.toml` with `-undefined dynamic_lookup` for apple targets, run from inside the crate dir | Passes |
| Same config, invoked from the REPO ROOT via `--manifest-path` | **FAILS.** Cargo resolves `.cargo/config.toml` from the current working directory, not the manifest directory, so the crate-local config is ignored. This directly collides with gotcha 4. |
| Cargo.toml with NO `extension-module` feature declared, all commands from the repo root | `cargo fmt --manifest-path ... -- --check` OK, `cargo clippy --manifest-path ... --all-targets -- -D warnings` OK, `cargo test --manifest-path ...` OK, `cargo build --manifest-path ...` OK |
| `maturin develop --manifest-path ...` from the repo root with `VIRTUAL_ENV=$PWD/.venv` | Built `bess_engine-0.1.0-cp312-cp312-macosx_11_0_arm64.whl` and installed editable. maturin passes `PYO3_BUILD_EXTENSION_MODULE=1` itself, so the cargo feature is unnecessary. |
| `python -c "import bess_engine; print(bess_engine.engine_info())"` | `{'crate_version': '0.1.0', 'highs_version': '1.15.0'}` |
| maturin needs a `pyproject.toml`? | No. It printed "Found pyo3 bindings" and built from `Cargo.toml` alone. |
| Cold build (`rm -rf target`, then build) | **20.6 s wall, 108 CPU-seconds**, 50 crates, `libhighs.a` genuinely rebuilt, on a 12-core M4-class Mac |
| `git check-ignore rust/bess_engine/target/probe.o` | **exit 1, NOT ignored.** `rust/target/probe.o` is ignored (`.gitignore:28`). |
| `git check-ignore src/bess/x.so` | **exit 1, NOT ignored** |
| mypy on a draft `rust.py` | 2 errors: `Cannot find implementation or library stub for module named "bess_engine"` and `Returning Any from function declared to return "dict[str, str]"` |
| ruff on the same draft | Clean (function-level imports are fine; PLC0415 is not in the selected rule set) |
| Local toolchain | cargo/rustc 1.94.1, cmake 4.4.2, Apple clang 21.0.0 present. **maturin is NOT installed.** |
| Baseline `uv run pytest -q` | Green, 117 tests, ~26 s |
| GitHub `ubuntu-24.04` runner image | CMake 3.31.6, Ninja 1.13.2, Clang 16/17/18, GNU C++ 12/13/14, Rust 1.97.1 + rustfmt + rustup preinstalled. `libclang` and `clippy` are not listed explicitly. |

## Impact Analysis

### Scope of Change

Additive and well fenced. Roughly 5 new files (crate manifest, lock, lib.rs,
`rust.py`, the scaffold test) and 6 touched files (pyproject, uv.lock, ci.yml,
adw_gates.json, .gitignore, TASKS.md), plus the app_docs feature doc. No
existing Python module is modified, no frozen interface changes, and no
existing test changes behavior. The blast radius on the Python side is a
single new module that nothing imports yet.

The real difficulty is not volume, it is that four of the eight acceptance
criteria (1, 2, 4, 5) are statements about toolchains behaving, which fail in
platform-specific ways that only show up when you actually run them.

### Risks and Considerations

1. **(blocker) `pyo3/extension-module` as a cargo feature breaks criteria 1 and 5.** Reproduced above. If `Cargo.toml` declares `pyo3 = { features = ["extension-module"] }`, `cargo build` and `cargo test` fail to link on macOS, which is Travis's dev machine and where the ADW gates run. The common workaround (`.cargo/config.toml` with `-C link-arg=-undefined -C link-arg=dynamic_lookup`) is resolved from the process CWD, so putting it in `rust/bess_engine/.cargo/config.toml` silently does nothing when gates invoke cargo from the repo root with `--manifest-path`, which gotcha 4 mandates. The other common workaround (an optional feature plus `cargo test --no-default-features`) works but forces every gate to remember the flag and leaves `cargo build` broken. **Simplest correct answer: do not declare the feature at all.** maturin sets `PYO3_BUILD_EXTENSION_MODULE=1` in the environment when it builds, and pyo3 0.28 honors it, so plain cargo commands link against libpython (fine for tests) while maturin still produces a correct extension wheel. Verified both ways.
2. **(blocker) `engine_info()` cannot report the HiGHS version through the safe `highs` crate.** It does not re-export `highs_sys`. Criterion 2 explicitly wants proof "that linking against highs-sys works", so returning `env!("CARGO_PKG_VERSION")` for both fields would satisfy the letter and defeat the purpose. Add `highs-sys` as a direct dependency and call `Highs_version()` in one documented `unsafe` block with `CStr::from_ptr`. Keep the declared version compatible with what `highs` resolves (a caret like `1.15` or `1.14.3`, never `=1.14.3`), or cargo will pull two copies of highs-sys and the native symbols will collide at link time. highs-sys has no `links` key, so cargo will not catch that for you.
3. **`.gitignore` does not cover the crate's build directory.** `rust/target/` is root-anchored and does not match `rust/bess_engine/target/`, which is where cargo will actually write (verified with `git check-ignore`). Left unfixed, the first `cargo build` leaves several hundred MB of untracked artifacts and `git status` noise, and a careless `git add -A` commits `libhighs.a`. Change the entry to `target/` (or add `rust/**/target/`) and add `*.so`, `*.pyd`, `*.dylib` while you are there.
4. **mypy will fail on `rust.py` two ways** (memory: `highspy-untyped-mypy`). A compiled extension has no stubs, so `import bess_engine` produces `import-not-found`; and `warn_return_any` rejects returning anything read off it. Add `bess_engine` to the existing `[[tool.mypy.overrides]]` block alongside `gridstatus.*` and `highspy.*`, and cast or annotate anything returned from `engine_info()`. Note that the override alone does not silence `no-any-return`.
5. **The confinement guard must not skip itself.** Criterion 3 (green with no extension) and criterion 6 (guard catches offenders) pull in opposite directions if `tests/test_rust_scaffold.py` starts with a module-level `pytest.importorskip("bess_engine")`, because that would skip the guard too. Scope the skip to the single test that needs the extension.
6. **The doctored-file proof has no precedent to copy.** The spec says "prove with a doctored-file test, same technique as the gridstatus guard", but the gridstatus guard (`tests/test_data.py:214`) has no such test; it only asserts `offenders == []`. Implementing this means factoring the detector to take a `Path` and pointing it at a `tmp_path` file containing `import bess_engine`. Assert both directions: the doctored file is flagged, and a clean file is not.
7. **`uv sync --locked` in CI means `uv.lock` must be regenerated.** Adding maturin to the dev group without committing the refreshed lock fails the existing python job, which is the one job the spec insists must stay green.
8. **libclang for bindgen is the one CI unknown.** `highs-sys` 1.15.0 build-depends on `bindgen 0.72`, which needs `libclang` at build time. The ubuntu-24.04 runner lists Clang 16/17/18 but does not list libclang explicitly. Cheap insurance: `sudo apt-get update && sudo apt-get install -y libclang-dev` in the rust job, or set `LIBCLANG_PATH`. cmake and a C++ compiler are confirmed preinstalled, so gotcha 1's cmake concern is already satisfied.
9. **The 15-minute CI fear is overstated, but cache anyway.** 108 CPU-seconds cold locally. On a 4-vCPU runner expect low single-digit minutes worst case. Use `Swatinem/rust-cache@v2` with `workspaces: rust/bess_engine` rather than hand-rolled `actions/cache`; it keys on Cargo.lock and handles the target dir correctly. Do not over-engineer this.
10. **`crate-type` must include `rlib`, not just `cdylib`.** A cdylib-only crate cannot be linked by cargo's unit-test harness in the normal way, and M4b will want `#[cfg(test)]` golden tests. Use `["cdylib", "rlib"]`.
11. **`edition` defaults to 2024 with cargo 1.94.** `cargo new` will write `edition = "2024"`. The spec says "edition 2021+", so either is legal, but 2021 is the wider-compatibility choice and matches what the ecosystem crates use (`highs` is 2021, `highs-sys` is 2018). Pick one deliberately rather than inheriting the default.
12. **Do not create `optimize_dispatch` in the crate.** The spec is explicit: M4b owns that name from the start. `engine_info` is the only `#[pyfunction]` in M4a.
13. **`.ports.env` will show up modified** (memory: `adw-worktree-port-file-cleanup`). It is already modified in this worktree right now. Restore it before opening the PR.
14. **Do not add `cargo fmt` to `.pre-commit-config.yaml`.** It is out of scope and pre-commit would then require a Rust toolchain for a docs-only commit. The spec asks for gates and CI, not hooks.

### Existing Patterns to Follow

- **AST-based import confinement** (memory: `ast-based-import-confinement-guard`, used 4 times already). Copy `_top_level_import_modules` from `tests/test_optimizer_properties.py:145` or `_imports_gridstatus` from `tests/test_data.py:203`, walk `src_root.rglob("*.py")`, allowlist `src/bess/optimizer/rust.py`, assert `offenders == []`. Never grep source text.
- **Module docstrings that cite the spec.** Every module in `src/bess` opens with a docstring naming the spec section and the contract it upholds. `lp.py:1-10` is the model.
- **`mypy` overrides for stub-less libraries.** `pyproject.toml:59-61` already has the pattern.
- **Network blocking is automatic.** `tests/conftest.py`'s autouse fixture covers new test files with no action needed (criterion 8).
- **Docs convention.** `app_docs/feature-<adw_id>-<slug>.md` with Overview / What Was Built / Technical Implementation (Files Modified, Key Changes) / Usage / Configuration / Testing / Notes, ending with the three gate commands.
- **Prose style.** No em-dashes anywhere. Commas, colons, or parentheses instead (CLAUDE.md).

## Recommendations

1. **Cargo.toml: pin exactly, declare no extension-module feature.**

   ```toml
   [package]
   name = "bess_engine"
   version = "0.1.0"
   edition = "2021"

   [lib]
   name = "bess_engine"
   crate-type = ["cdylib", "rlib"]

   [dependencies]
   pyo3 = "0.28.3"
   numpy = "0.28.0"       # rust-numpy; requires pyo3 ^0.28, pinned as a pair
   highs = "2.4.0"
   highs-sys = "1.15"     # direct dep so engine_info can call Highs_version
   thiserror = "2.0.19"   # declared for M4b's DispatchError, unused here
   ```

   Commit `Cargo.lock`. Delete `rust/.gitkeep`.

2. **lib.rs: one pyfunction, one unsafe block, one cargo test.** Keep the
   FFI call in a small private helper with a `// SAFETY:` comment
   (`Highs_version` returns a pointer to a static NUL-terminated string), and
   add a `#[cfg(test)]` test asserting the version string is non-empty so
   `cargo test` is meaningful rather than vacuous. The prototype's shape:

   ```rust
   #[pyfunction]
   fn engine_info(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
       let d = PyDict::new(py);
       d.set_item("crate_version", env!("CARGO_PKG_VERSION"))?;
       d.set_item("highs_version", highs_version())?;
       Ok(d)
   }

   #[pymodule]
   fn bess_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
       m.add_function(wrap_pyfunction!(engine_info, m)?)?;
       Ok(())
   }
   ```

3. **rust.py: lazy import, explicit error text, typed returns.** Module-level
   imports stay `numpy` + `bess.models` only. Put `import bess_engine` inside a
   loader helper, catch `ImportError`, and re-raise with the documented build
   command. `engine_available()` returns bool by swallowing that ImportError.
   `optimize_dispatch_rust` keeps the frozen signature and raises
   `NotImplementedError` naming M4b/M4c. Cast anything read off the extension
   before returning it (risk 4).

4. **Document one build command and use it everywhere.** With maturin in the
   dev group, that command is:

   ```
   uv run maturin develop --manifest-path rust/bess_engine/Cargo.toml
   ```

   Verified working from the repo root against `.venv`. Use this exact string
   in the ImportError message, the README quick-start line, and the CI job so
   there is one thing to keep true.

5. **adw_gates.json: append three gates, all root-relative.**

   ```json
   { "name": "rust-fmt",    "command": "cargo fmt --manifest-path rust/bess_engine/Cargo.toml -- --check" },
   { "name": "rust-clippy", "command": "cargo clippy --manifest-path rust/bess_engine/Cargo.toml --all-targets -- -D warnings" },
   { "name": "rust-test",   "command": "cargo test --manifest-path rust/bess_engine/Cargo.toml" }
   ```

   All four verified from the repo root. `cargo fmt` does accept
   `--manifest-path`. Never `cd`.

6. **CI rust job shape.** `runs-on: ubuntu-latest`; checkout;
   `dtolnay/rust-toolchain@stable` with `components: rustfmt, clippy` (do not
   rely on the image's preinstalled clippy being present);
   `apt-get install -y libclang-dev` as insurance for bindgen;
   `Swatinem/rust-cache@v2` with `workspaces: rust/bess_engine`;
   `astral-sh/setup-uv@v5` + `uv sync --locked`; then fmt, clippy, cargo test,
   `uv run maturin develop --manifest-path ...`, and finally `uv run pytest`.
   Leave the `checks` job byte-identical so its green run keeps proving the
   extension-absent path.

7. **Test file layout for `tests/test_rust_scaffold.py`.** Four tests, only
   one of them extension-gated:
   - `test_engine_info_reports_versions`: gated on `engine_available()` (or a
     function-local `importorskip`) with a skip reason naming the maturin
     command; asserts the returned mapping has `crate_version` and
     `highs_version` keys with non-empty string values.
   - `test_optimize_dispatch_rust_is_not_implemented_yet`: ungated;
     `pytest.raises(NotImplementedError, match="M4b")`.
   - `test_bess_engine_import_confined_to_rust_module`: ungated; AST sweep of
     `src/bess/**/*.py`.
   - `test_confinement_guard_detects_a_doctored_module`: ungated; writes a
     `tmp_path` file containing `import bess_engine`, asserts the detector
     flags it, and asserts a clean file is not flagged.

8. **Sequencing that fails fast.** Crate and `cargo test` first (proves the
   HiGHS link, the expensive unknown), then `maturin develop` and the Python
   import (proves the boundary), then `rust.py` and the tests, then gates,
   then CI, then `.gitignore`/`uv.lock`/docs. If the crate does not build,
   nothing downstream is worth writing.

9. **Before opening the PR:** confirm `uv run pytest` is green in a venv with
   the extension REMOVED (delete
   `.venv/lib/python3.12/site-packages/bess_engine*` and re-run) so criterion 3
   is genuinely tested and not accidentally passing because your dev venv still
   has the extension installed. Then check `git status` for `.ports.env` and any
   stray `target/` output.

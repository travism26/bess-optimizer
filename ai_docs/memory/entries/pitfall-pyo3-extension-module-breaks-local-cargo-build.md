---
name: pyo3-extension-module-breaks-local-cargo-build
description: Declaring pyo3's extension-module cargo feature breaks standalone cargo build/test; let maturin set it instead
type: pitfall
source_adw_ids: [8694b681]
date: 2026-08-02
---

In rust/bess_engine (M4a), declaring the `pyo3/extension-module` cargo feature unconditionally makes `cargo build`/`cargo test`/`cargo clippy` fail on macOS with `ld: symbol(s) not found`, because that feature strips the libpython link that a standalone (non-maturin) build still needs. The usual fix, a `.cargo/config.toml` rustflags workaround, resolves relative to the current working directory, so it silently does not apply when gates invoke `cargo build --manifest-path rust/bess_engine/Cargo.toml` from the repo root instead of `cd`-ing into the crate (this repo's gates always use --manifest-path, per CLAUDE.md gotcha 4 in the M4a spec). Fix: do not declare the feature in Cargo.toml at all; maturin sets `PYO3_BUILD_EXTENSION_MODULE=1` itself when it builds the wheel, so plain cargo commands work standalone and `maturin develop` still produces an importable extension. Separately, the safe `highs` crate (v2.4.0) does not re-export `highs_sys`, so any code needing a raw HiGHS C API call (e.g. a version-string hello-world) needs its own direct `highs-sys` dependency plus one documented `unsafe` block. Relevant to any future Rust crate or PyO3 binding added in this repo (M4b/M4c and beyond).

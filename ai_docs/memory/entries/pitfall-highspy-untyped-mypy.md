---
name: highspy-untyped-mypy
description: highspy and bess_engine have no type stubs; mypy needs an ignore_missing_imports override plus explicit casts at call sites
type: pitfall
source_adw_ids: [3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-08-02
---

highspy (the HiGHS Python binding used in src/bess/optimizer/lp.py and src/bess/optimizer/as_lp.py) ships without type stubs, so mypy treats attributes read off Highs/HighsLp objects (solution values, status, etc.) as Any. This repo's mypy config has warn_return_any enabled (per CLAUDE.md's `uv run mypy` gate), so returning such values directly from a typed function fails the gate; cast or explicitly annotate them before returning. The same stub-less-extension problem recurred in M4a for `bess_engine`, the new PyO3/maturin-built Rust extension imported lazily in src/bess/optimizer/rust.py: it needed the identical treatment, added to the same `[[tool.mypy.overrides]] module = ["gridstatus.*", "highspy.*", "bess_engine"]` block (pyproject.toml) plus a `cast` where its return value crosses into typed code. Any future native/compiled extension without stubs (M4b/M4c's real bess_engine.optimize_dispatch, or anything else) should get the same override-plus-cast treatment rather than a new mechanism.

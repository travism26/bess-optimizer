---
name: ast-based-import-confinement-guard
description: Guard tests that confine an import (e.g. gridstatus, highspy, bess_engine) to one module should parse the AST, not grep source text
type: lesson
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-08-02
---

When writing a test to enforce that a library import is confined to a single module (e.g. gridstatus to src/bess/data/prices.py and src/bess/data/as_prices.py, the optimizer purity rule limiting lp.py/as_lp.py to numpy/highspy/bess.models, or M4a's bess_engine confined to src/bess/optimizer/rust.py), implement the check via Python's `ast` module (parse the file, walk Import/ImportFrom nodes against an allowlist) rather than a substring/regex search over file text. A substring guard produces false positives when the library name appears in a docstring or comment elsewhere in src/. This pattern has now been reused five times (energy data-layer gridstatus confinement, M1 optimizer purity rule, AS data-layer gridstatus confinement, M3b AS co-optimizer purity rule, M4a Rust extension confinement) and should be the default approach for any future import-confinement acceptance criterion, including M4b/M4c if they add more Rust-facing modules.

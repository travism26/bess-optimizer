---
name: ast-based-import-confinement-guard
description: Guard tests that confine an import (e.g. gridstatus, highspy) to one module should parse the AST, not grep source text
type: lesson
source_adw_ids: [3c648beb, 3b9cf1a9, 5dbaba17]
date: 2026-07-29
---

When writing a test to enforce that a library import is confined to a single module (e.g. gridstatus to src/bess/data/prices.py, or the optimizer/lp.py purity rule limiting it to numpy/highspy/bess.models), implement the check via Python's `ast` module (parse the file, walk Import/ImportFrom nodes against an allowlist) rather than a substring/regex search over file text. A substring guard produces false positives when the library name appears in a docstring or comment elsewhere in src/. This pattern has now been reused twice (data-layer gridstatus confinement, optimizer purity rule) and should be the default approach for any future import-confinement acceptance criterion.

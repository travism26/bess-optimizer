---
name: ast-based-import-confinement-guard
description: Guard tests that confine an import (e.g. gridstatus) to one module should parse the AST, not grep source text
type: lesson
source_adw_ids: [3c648beb]
date: 2026-07-29
---

When writing a test to enforce that a library import (e.g. gridstatus) is confined to a single module (src/bess/data/prices.py per CLAUDE.md), implement the check via Python's `ast` module (parse each src/ file, walk Import/ImportFrom nodes) rather than a substring/regex search over file text. A substring guard produces false positives when the library name appears in a docstring or comment elsewhere in src/. This pattern was needed once already for the gridstatus confinement test and will recur for any similar future confinement rule.

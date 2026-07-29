---
name: highspy-untyped-mypy
description: highspy has no type stubs; values read from it need explicit casts/annotations to satisfy mypy warn_return_any
type: pitfall
source_adw_ids: [3b9cf1a9, 27b2b22d]
date: 2026-07-29
---

highspy (the HiGHS Python binding used in src/bess/optimizer/lp.py) ships without type stubs, so mypy treats attributes read off Highs/HighsLp objects (solution values, status, etc.) as Any. This repo's mypy config has warn_return_any enabled (per CLAUDE.md's `uv run mypy` gate), so returning such values directly from a typed function fails the gate. Cast or explicitly annotate values pulled from highspy before returning them from optimize_dispatch or any future code that touches highspy directly (e.g. the M4 Rust engine's Python-side parity harness, if any).

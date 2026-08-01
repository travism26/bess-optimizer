---
name: revenue-ratio-helpers-need-zero-guard
description: Pure ratio/percentage analytics helpers over LP-derived revenue need explicit zero-denominator guards
type: lesson
source_adw_ids: [d39c4d18]
date: 2026-08-01
---

src/bess/analytics/benchmarks.py's `revenue_mix` (M3c) divides by `sum(revenue_by_product.values())` with no zero-guard; a backtest window with exactly $0 total AS revenue across all products (an LP-degeneracy edge case the M3 spec itself calls out, see [[lp-optimizer-degeneracy-in-tests]]) would raise ZeroDivisionError inside `bess benchmark` instead of skipping cleanly, though not reachable on the current committed fixtures. Flagged skippable in review, not fixed. Any future percentage/ratio analytics helper computed over LP-derived revenue or dispatch totals (capture rate, uplift, mix, or similar) should guard the zero-denominator case explicitly (return NaN/None or skip) rather than assume the totals are always nonzero, since simultaneous charge/discharge or degenerate LP optima can legitimately produce exact zeros.

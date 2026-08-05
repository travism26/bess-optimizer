---
name: lp-optimizer-degeneracy-in-tests
description: LP optimum is often non-unique; assert net dispatch/revenue/aggregate totals, not raw per-vertex or per-product values
type: lesson
source_adw_ids: [3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-08-01
---

src/bess/optimizer/lp.py's HiGHS LP can have multiple optimal basic solutions sharing the same objective value (e.g. the lossless eff=1.0 golden case: charge and discharge within the same window are interchangeable at the vertex level). Tests asserting a specific expected charge_mw/discharge_mw per interval can be brittle or wrong even when the solver is correct. Prefer asserting net dispatch (discharge - charge) per window, objective/revenue value, and SoC bounds/dynamics rather than exact per-interval gross dispatch. This degeneracy extends to the AS co-optimizer (src/bess/optimizer/as_lp.py, M3b): shuffling AS product order changes which product 'earns' a given dollar (REG_UP and ECRS swapped $2,555 on the July fixture) while the objective and aggregate AS revenue stay identical, so co-optimizer tests must assert aggregate AS revenue and the objective, never a per-product split. Separately, constructing a targeted behavior case such as M1b's AC-10 (forcing simultaneous charge+discharge at a negative price) needs a single-interval horizon or another tightly constrained setup, since an obvious multi-hour construction lets the LP dodge simultaneity by draining the battery for free in an earlier zero-price hour instead. Relevant to any future optimizer test (M1c backtest properties, M4 Rust engine parity tests). See also [[revenue-ratio-helpers-need-zero-guard]] for the same degeneracy showing up as a possible zero-revenue edge case in production code, not just tests.

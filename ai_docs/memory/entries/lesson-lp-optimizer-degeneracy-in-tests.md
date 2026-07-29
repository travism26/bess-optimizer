---
name: lp-optimizer-degeneracy-in-tests
description: LP dispatch optimum is often non-unique; assert net dispatch/revenue, not raw per-interval vertex values
type: lesson
source_adw_ids: [3b9cf1a9, 5dbaba17]
date: 2026-07-29
---

src/bess/optimizer/lp.py's HiGHS LP can have multiple optimal basic solutions sharing the same objective value (e.g. the lossless eff=1.0 golden case: charge and discharge within the same window are interchangeable at the vertex level). Tests asserting a specific expected charge_mw/discharge_mw per interval can be brittle or wrong even when the solver is correct. Prefer asserting net dispatch (discharge - charge) per window, objective/revenue value, and SoC bounds/dynamics rather than exact per-interval gross dispatch. Separately, constructing a targeted behavior case such as M1b's AC-10 (forcing simultaneous charge+discharge at a negative price) needs a single-interval horizon or another tightly constrained setup: an obvious multi-hour construction lets the LP dodge simultaneity by draining the battery for free in an earlier zero-price hour instead. Relevant to any future optimizer test (M1c backtest properties, M4 Rust engine parity tests).

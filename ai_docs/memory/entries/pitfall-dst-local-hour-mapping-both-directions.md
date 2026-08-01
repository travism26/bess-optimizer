---
name: dst-local-hour-mapping-both-directions
description: Local-hour-of-day mapping across DST must handle 23h/25h on both source and target days, not just the target
type: pitfall
source_adw_ids: [cea65174, 325296bb, 6f498150]
date: 2026-07-30
---

When mapping prices/forecasts by local hour-of-day across a DST boundary (e.g. persistence forecast in src/bess/backtest/rolling.py, M2a), the master spec's DST gotcha text only describes the *target*/lookahead day having 23 or 25 hours. But the *source* (commit) day can also be a DST-transition day: a 23-hour spring-forward source day has no local hour 2, leaving a hole when mapped onto a normal 24-hour lookahead day; a first prototype left this as NaN, which made HiGHS return status 'Unknown' and `optimize_dispatch` raise `RuntimeError: HiGHS did not reach an optimal solution` (a synthetic 730-day rolling run hit this exactly). A 25-hour fall-back source day has two prices for one local hour and needs an explicit tie-break (e.g. keep='first'). When implementing any local-hour-of-day mapping or windowing logic, enumerate both directions (23/24/25 source paired with 23/24/25 target) and pick and document explicit fill/dedup rules for each; don't assume only the lookahead/target side needs special-casing.

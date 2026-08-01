---
name: timestamp-plus-timedelta-days-crosses-dst
description: Timestamp + Timedelta(days=N) on tz-aware data adds exact elapsed hours, not calendar days, and drifts across DST
type: pitfall
source_adw_ids: [6f498150, 3034ec63]
date: 2026-08-01
---

pandas `Timestamp + Timedelta(days=1)` on a tz-aware timestamp adds exactly 24 hours of elapsed time, not one calendar day; across a DST transition this silently shifts the local wall-clock hour by one, which breaks day-window boundary math (e.g. computing the next day's cutoff for gap validation or fixture generation). Hit again in M3a fixture generation for the AS data layer (src/bess/data/as_prices.py), after already being documented for M2a's rolling forecast (see dst-local-hour-mapping-both-directions). Fix: do the arithmetic on the plain date (`date + timedelta(days=1)`) and only localize/convert to UTC at the end, rather than adding Timedelta directly to a tz-aware Timestamp. Apply this whenever computing a day-boundary or window edge from a tz-aware timestamp anywhere in this repo.

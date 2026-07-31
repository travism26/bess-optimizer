---
name: gridstatus-ercot-dam-api-pitfall
description: gridstatus Ercot.get_spp() is unreliable for historical DAM data; use get_dam_spp(year) instead
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb]
date: 2026-07-29
---

In gridstatus==0.36.0, `Ercot.get_spp(..., market=DAY_AHEAD_HOURLY)` queries ERCOT's MIS recent-documents endpoint, which only retains recent documents and silently returns an empty DataFrame (not an exception) when no documents match a historical date range. Its date filtering also uses *publish* date, which is one day before the delivery day, causing an off-by-one on `[start, end]` requests. For historical/backfill fetches (e.g. the fixture generation in M1a), use `Ercot.get_dam_spp(year=...)` instead, which returns the full yearly archive. This is why src/bess/data/prices.py's `_fetch_raw` calls `get_dam_spp(year)` per year rather than `get_spp` with a date range. Relevant to any future work touching src/bess/data/prices.py or adding new ISO/location fetches.

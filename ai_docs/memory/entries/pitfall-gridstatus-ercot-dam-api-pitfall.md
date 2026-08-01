---
name: gridstatus-ercot-dam-api-pitfall
description: gridstatus 'recent/current' report methods are unreliable for historical backfill; use yearly-archive report types instead
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18]
date: 2026-08-01
---

In gridstatus==0.36.0, ERCOT 'current/recent' report methods read MIS recent-documents endpoints that retain only a short window and silently return an empty DataFrame (not an exception) outside it. Energy: `Ercot.get_spp(..., market=DAY_AHEAD_HOURLY)` reads report NP4-190-CD; use `Ercot.get_dam_spp(year=...)` instead (full yearly archive). Its date filtering also uses *publish* date, one day before delivery, causing an off-by-one on [start, end] requests. AS/MCPC: both spec-named methods `get_as_prices` and `get_mcpc_dam` read report 12329, retaining only ~31 days; the working path (found in M3a) is MIS report type 13091, 'Historical DAM Ancillary Service MCPCs', yearly zips (`DAMASMCPC_{year}.zip`) via the same `Ercot._get_document(report_type_id=..., constructed_name_contains=f'{year}.zip')` plumbing `get_dam_spp` uses. Lesson: for any new gridstatus historical/backfill fetch, do not trust the obviously-named method; verify live whether it actually serves the needed date range, and look for a yearly-archive report type by number instead.

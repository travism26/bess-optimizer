---
name: as-mcpc-archive-wide-format
description: ERCOT's yearly AS MCPC archive (MIS report 13091) is wide-format with a trailing-space header and non-canonical product codes
type: pitfall
source_adw_ids: [6f498150]
date: 2026-08-01
---

The gridstatus-backed yearly AS MCPC archive (DAMASMCPC_{year}.zip, MIS report 13091) is one row per hour with one column per product (wide), not long. The 'REGUP' column header carries a trailing space (`'REGUP '`) in both the 2023 and 2024 archives. Raw product codes are REGDN/REGUP/RRS/NSPIN/ECRS, none matching the canonical REG_DOWN/REG_UP/RRS/NONSPIN/ECRS names used elsewhere in this repo's schema. src/bess/data/as_prices.py melts the wide frame to long and applies an explicit _PRODUCT_MAP, raising on any unmapped column rather than passing it through. Any future code parsing this archive directly (or a similar wide ISO report) must strip column whitespace before matching and maintain an explicit rename/allowlist map.

---
name: fetch-da-prices-per-location-redownload
description: fetch_da_prices redownloads the full yearly ERCOT archive once per location, not shared across locations
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174]
date: 2026-07-29
---

`_fetch_raw` in src/bess/data/prices.py downloads and parses the entire yearly ERCOT DAM archive (all hubs, all locations) on every call, but `fetch_da_prices` is invoked once per location. A `bess fetch` run over the default multi-location config therefore re-downloads and re-parses the same yearly zip file once per location instead of once total. Flagged as tech_debt in M1a review, not fixed. If working on performance of `bess fetch` or adding more default locations, consider sharing/caching the per-year raw fetch across locations (e.g. a module-level cache keyed by year) before assuming the current per-location cost is fine.

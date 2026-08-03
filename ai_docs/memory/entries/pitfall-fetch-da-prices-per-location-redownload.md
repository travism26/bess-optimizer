---
name: fetch-da-prices-per-location-redownload
description: Redundant re-fetches of already-cached price data recur across call sites instead of threading the DataFrame through
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-08-01
---

`_fetch_raw` in src/bess/data/prices.py downloads and parses the entire yearly ERCOT DAM archive (all hubs, all locations) on every call, but `fetch_da_prices` is invoked once per location. A `bess fetch` run over the default multi-location config therefore re-downloads and re-parses the same yearly zip file once per location instead of once total. Flagged as tech_debt in M1a review, not fixed. The same shape recurred in M3c at a different call site: `bess backtest --ancillary` calls fetch_da_prices a second time per location purely to feed run_backtest_as, even though `_run_location` already loaded the identical cached parquet moments earlier (flagged tech_debt again in review, not fixed). The on-disk parquet cache makes each individual redundant call cheap, so it never blocks a milestone, but review keeps flagging it. When wiring a new code path that needs data another nearby call site in the same command already fetched, thread the already-loaded DataFrame through rather than calling the fetch function again; if working on `bess fetch` performance broadly, consider a module-level cache keyed by year shared across locations.

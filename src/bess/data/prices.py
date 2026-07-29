"""Fetch, canonicalize, and parquet-cache ERCOT day-ahead settlement point prices.

This module is the only place allowed to import or call gridstatus (spec gotcha 4:
its API surface changes between versions, so the pin and the isolation both live
here). It owns all timezone handling: gridstatus returns tz-aware prevailing
Central Time, which must be converted to UTC immediately (spec gotcha 1: DST days
have 23 or 25 hours, never assume 24 rows per calendar day). Negative prices are
valid data and must never be clipped or filtered (spec gotcha 3).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

# Canonical price schema (spec section "Canonical price schema"). This exact
# column set and naming survives unchanged into Snowflake in M5.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "interval_start_utc",  # timestamp[us, tz=UTC]
    "interval_end_utc",  # timestamp[us, tz=UTC]
    "iso",  # "ERCOT"
    "market",  # "DAY_AHEAD_HOURLY"
    "location",  # "HB_NORTH" etc.
    "location_type",  # "Trading Hub"
    "price",  # float64, $/MWh, negatives allowed
)


def fetch_da_prices(
    location: str,
    start: date,
    end: date,
    cache_dir: Path,
) -> pd.DataFrame:
    """Return canonical-schema day-ahead hourly prices for one ERCOT hub.

    Intended behavior:
    - Serve from the parquet cache under cache_dir when present; otherwise fetch
      via gridstatus, canonicalize to CANONICAL_COLUMNS, and write the cache.
    - Output is sorted by interval_start_utc, deduplicated, strictly increasing
      per location.
    - Gaps within [start, end] raise with the missing intervals listed; never
      silently interpolate.

    Covered by acceptance criteria: 9 (tests exercise this only via committed
    fixtures, no network in CI) and the canonical-schema requirements tested in
    tests/test_data.py. gridstatus itself is exercised only by `bess fetch`
    run manually.
    """
    raise NotImplementedError

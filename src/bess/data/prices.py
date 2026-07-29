"""Fetch, canonicalize, and parquet-cache ERCOT day-ahead settlement point prices.

This module is the only place allowed to import or call gridstatus (spec gotcha 4:
its API surface changes between versions, so the pin and the isolation both live
here). It owns all timezone handling: gridstatus returns tz-aware prevailing
Central Time, which must be converted to UTC immediately (spec gotcha 1: DST days
have 23 or 25 hours, never assume 24 rows per calendar day). Negative prices are
valid data and must never be clipped or filtered (spec gotcha 3).

Historical DA prices are pulled via gridstatus's yearly DAM archive
(``Ercot.get_dam_spp``) rather than the recent-documents endpoint (``Ercot.get_spp``),
because the latter filters on document *publish* date (one day before delivery for
DAM) and silently returns an empty frame once ERCOT's document list ages the
relevant postings out. The yearly archive has neither problem for the 2023-2024
window this project targets.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

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

_ISO = "ERCOT"
_CENTRAL_TZ = "US/Central"


def _fetch_raw(location: str, start: date, end: date) -> pd.DataFrame:
    """Fetch gridstatus's raw ERCOT DAM settlement point price rows for one hub.

    Raw rows use gridstatus's own column names (Interval Start, Interval End,
    Location, Location Type, Market, SPP), tz-aware in prevailing Central Time.
    Pulls the full-year historical archive for every year spanning [start, end]
    and filters to `location`; canonicalization and date-window slicing happen
    separately in `_canonicalize` so an upstream gridstatus API change is
    confined to this one function (spec gotcha 2).
    """
    import gridstatus  # imported lazily so gridstatus is only paid for here

    ercot = gridstatus.Ercot()
    raw_years = [ercot.get_dam_spp(year=year) for year in range(start.year, end.year + 1)]
    raw = pd.concat(raw_years, ignore_index=True)
    raw = raw[raw["Location"] == location]
    if raw.empty:
        raise ValueError(
            f"gridstatus returned no rows for location {location!r} in "
            f"{start.year}-{end.year}. Check the location name."
        )
    return raw


def _canonicalize(raw: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Normalize a raw gridstatus DAM SPP frame to CANONICAL_COLUMNS.

    Converts prevailing Central Time to UTC first, then slices to the
    requested window of Central calendar days [start, end] inclusive. Sorts by
    interval_start_utc and drops duplicate intervals, keeping the first.
    """
    lower = pd.Timestamp(start, tz=_CENTRAL_TZ)
    upper = pd.Timestamp(end + timedelta(days=1), tz=_CENTRAL_TZ)
    window = raw[(raw["Interval Start"] >= lower) & (raw["Interval Start"] < upper)]

    canonical = pd.DataFrame(
        {
            "interval_start_utc": window["Interval Start"].dt.tz_convert("UTC"),
            "interval_end_utc": window["Interval End"].dt.tz_convert("UTC"),
            "iso": _ISO,
            "market": window["Market"].astype(str),
            "location": window["Location"].astype(str),
            "location_type": window["Location Type"].astype(str),
            "price": window["SPP"].astype("float64"),
        }
    )
    canonical["interval_start_utc"] = canonical["interval_start_utc"].astype("datetime64[us, UTC]")
    canonical["interval_end_utc"] = canonical["interval_end_utc"].astype("datetime64[us, UTC]")

    # kind="stable" so that if a duplicate interval appears, which copy is kept
    # deterministically reflects its original position in the raw input.
    canonical = canonical.sort_values("interval_start_utc", kind="stable")
    canonical = canonical.drop_duplicates(subset="interval_start_utc", keep="first")
    canonical = canonical.reset_index(drop=True)
    return canonical[list(CANONICAL_COLUMNS)]


def _validate(df: pd.DataFrame, location: str, start: date, end: date) -> None:
    """Assert canonical-schema invariants for the requested window.

    Checks column names and dtypes, strict monotonicity, no duplicates, and no
    gaps within [start, end]. A gap raises with the missing interval
    timestamps listed; never silently interpolated (spec item 3).
    """
    if list(df.columns) != list(CANONICAL_COLUMNS):
        raise ValueError(f"Expected columns {list(CANONICAL_COLUMNS)}, got {list(df.columns)}")

    expected_dtypes = {
        "interval_start_utc": "datetime64[us, UTC]",
        "interval_end_utc": "datetime64[us, UTC]",
        "iso": "object",
        "market": "object",
        "location": "object",
        "location_type": "object",
        "price": "float64",
    }
    bad_dtypes = {
        column: str(df[column].dtype)
        for column, expected in expected_dtypes.items()
        if str(df[column].dtype) != expected
    }
    if bad_dtypes:
        raise ValueError(f"Unexpected dtypes for {location}: {bad_dtypes}")

    if df["interval_start_utc"].duplicated().any():
        raise ValueError(f"Duplicate interval_start_utc values for {location}")
    if not df["interval_start_utc"].is_monotonic_increasing:
        raise ValueError(f"interval_start_utc is not sorted increasing for {location}")

    lower_utc = pd.Timestamp(start, tz=_CENTRAL_TZ).tz_convert("UTC")
    upper_utc = pd.Timestamp(end + timedelta(days=1), tz=_CENTRAL_TZ).tz_convert("UTC")
    expected_index = pd.date_range(lower_utc, upper_utc, freq="h", inclusive="left")
    missing = expected_index.difference(pd.DatetimeIndex(df["interval_start_utc"]))
    if len(missing) > 0:
        raise ValueError(
            f"Missing {len(missing)} interval(s) for {location} in [{start}, {end}]: "
            f"{[ts.isoformat() for ts in missing]}"
        )


def _cache_path(cache_dir: Path, location: str, start: date, end: date) -> Path:
    return cache_dir / f"{location}_{start.isoformat()}_{end.isoformat()}.parquet"


def fetch_da_prices(
    location: str,
    start: date,
    end: date,
    cache_dir: Path,
) -> pd.DataFrame:
    """Return canonical-schema day-ahead hourly prices for one ERCOT hub.

    Serves from the parquet cache under cache_dir when present; otherwise
    fetches via gridstatus, canonicalizes to CANONICAL_COLUMNS, and writes the
    cache. Output is sorted by interval_start_utc, deduplicated, and validated
    on every return path (cache hit or fresh fetch) so a corrupted or
    hand-edited cache file fails loudly instead of propagating bad data.

    Covered by acceptance criteria: 9 (tests exercise this only via committed
    fixtures, no network in CI) and the canonical-schema requirements tested in
    tests/test_data.py. gridstatus itself is exercised only by `bess fetch`
    run manually.
    """
    cache_path = _cache_path(cache_dir, location, start, end)
    if cache_path.exists():
        logger.info("Loading %s prices from cache: %s", location, cache_path)
        df = pd.read_parquet(cache_path)
    else:
        logger.info("Fetching %s prices from gridstatus for [%s, %s]", location, start, end)
        raw = _fetch_raw(location, start, end)
        df = _canonicalize(raw, start, end)
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info("Cached %s prices to %s", location, cache_path)

    _validate(df, location, start, end)
    return df

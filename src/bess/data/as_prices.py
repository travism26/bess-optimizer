"""Fetch, canonicalize, and parquet-cache ERCOT DAM ancillary-service clearing prices.

This module, alongside data/prices.py, is the only place allowed to import or
call gridstatus (spec gotcha: an upstream API surface change should be a
one-file fix; the AST-based import-confinement guard in tests/test_as_data.py
enforces the allowlist, memory: ast-based-import-confinement-guard). It owns
all timezone handling exactly like data/prices.py: ERCOT publishes ancillary
MCPCs in prevailing Central Time, converted to UTC immediately (DST days have
23 or 25 hours, never assume 24 rows per calendar day). Zero-priced MCPCs are
valid data and must never be clipped or filtered (the energy layer's
negative-price philosophy, extended here since AS MCPCs are typically
non-negative but zero is common).

MCPCs are pulled from gridstatus's yearly MIS report 13091, "Historical DAM
Ancillary Service MCPCs" (``DAMASMCPC_<year>.zip``), not from
``Ercot.get_as_prices`` or ``Ercot.get_mcpc_dam``: both of the latter read MIS
report 12329, whose live document list retains only about a month of history
and cannot serve the 2023-2024 window this project targets (verified live
during research; the same lesson as get_spp being unreliable for historical
DAM energy prices, one level deeper: memory: gridstatus-ercot-dam-api-pitfall).
Report 13091 is reached with the same ``Ercot._get_document`` plumbing
``get_dam_spp(year)`` uses for energy prices.

MCPCs are system-wide (no location), so a full window is fetched once, not
once per hub the way fetch_da_prices is (memory:
fetch-da-prices-per-location-redownload does not apply here).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import IO, cast

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical AS price schema (specs/M3_ancillary_services.md, "Canonical AS
# price schema"). Long format, one row per (interval, product); no location
# column because ERCOT DAM MCPCs are system-wide.
AS_CANONICAL_COLUMNS: tuple[str, ...] = (
    "interval_start_utc",  # timestamp[us, tz=UTC]
    "interval_end_utc",  # timestamp[us, tz=UTC]
    "iso",  # "ERCOT"
    "market",  # "DAM_AS"
    "product",  # "REG_UP" | "REG_DOWN" | "RRS" | "ECRS" | "NONSPIN"
    "price",  # float64, MCPC $/MW-h
)

_ISO = "ERCOT"
_MARKET = "DAM_AS"
_CENTRAL_TZ = "US/Central"

# MIS report type ID for "Historical DAM Ancillary Service MCPCs" (yearly
# zips). gridstatus 0.36.0 has no named constant for this report.
HISTORICAL_DAM_AS_MCPC_RTID = 13091

# ECRS cleared for the first time on this date; absence before it is
# structural (the market did not exist yet), not a data gap (spec gotcha 2).
ECRS_LAUNCH = date(2023, 6, 10)

# Per-product launch dates, used as the lower bound of each product's gap
# validation window. Products absent from this map are treated as live for
# the entire history this project targets. Public so bess.backtest.as_runner
# (M3c) can build the same launch-rule availability mask without reaching
# into a private name.
PRODUCT_LAUNCH: dict[str, date] = {"ECRS": ECRS_LAUNCH}

# gridstatus's raw MIS 13091 column names (post whitespace-strip) mapped to
# canonical product names. Explicit and exhaustive: an unrecognized raw
# product column raises rather than passing through (spec gotcha 2).
_PRODUCT_MAP: dict[str, str] = {
    "REGDN": "REG_DOWN",
    "REGUP": "REG_UP",
    "RRS": "RRS",
    "NSPIN": "NONSPIN",
    "ECRS": "ECRS",
}

# Non-product columns present on the parsed (post gridstatus.Ercot.parse_doc)
# raw frame; everything else is assumed to be a product column.
_RAW_ID_COLUMNS = ("Time", "Interval Start", "Interval End")


def _fetch_raw(start: date, end: date) -> pd.DataFrame:
    """Fetch gridstatus's raw ERCOT DAM AS MCPC rows spanning [start.year, end.year].

    Pulls one yearly zip per year in the window from MIS report 13091 (wide
    format: one row per hour, one column per product), strips whitespace from
    column headers (the 2023 and 2024 archives both ship a "REGUP " column
    with a trailing space), and hands the concatenated frame to
    ``Ercot.parse_doc`` so it owns the DST-aware Central-time localization
    exactly as it does for get_dam_spp (spec gotcha 3). The returned frame is
    still wide and still uses gridstatus's raw product codes; melting to long
    format and mapping to canonical product names happens in `_canonicalize`
    so an upstream gridstatus change stays a one-function fix (spec gotcha 1).
    """
    import gridstatus  # imported lazily so gridstatus is only paid for here

    ercot = gridstatus.Ercot()
    raw_years = []
    for year in range(start.year, end.year + 1):
        doc = ercot._get_document(
            report_type_id=HISTORICAL_DAM_AS_MCPC_RTID,
            constructed_name_contains=f"{year}.zip",
        )
        # get_zip_file is annotated -> ZipFile but actually returns the opened
        # member file (ZipExtFile, a binary IO stream); cast for read_csv.
        zip_member = cast(IO[bytes], gridstatus.utils.get_zip_file(doc.url))
        year_df = pd.read_csv(zip_member)
        year_df.columns = [str(column).strip() for column in year_df.columns]
        raw_years.append(year_df)
    raw = pd.concat(raw_years, ignore_index=True)
    if raw.empty:
        raise ValueError(
            f"gridstatus returned no AS MCPC rows for {start.year}-{end.year}. "
            "Check MIS report 13091's document list."
        )
    return ercot.parse_doc(raw)


def _canonicalize(raw: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Normalize a raw (post `Ercot.parse_doc`) wide AS MCPC frame to AS_CANONICAL_COLUMNS.

    Slices to the requested window of Central calendar days [start, end]
    inclusive, melts the wide per-product columns to long format, and drops
    rows with a NaN price: this is what implements the "structural absence"
    rule for products before their market launch (e.g. ECRS before
    2023-06-10), never a silent fill for a genuine gap (a genuine mid-window
    gap in a live product is simply dropped the same way here and then
    re-detected and raised by `_validate`, spec item 5). Raises on any raw
    product column not in `_PRODUCT_MAP` rather than passing it through (spec
    gotcha 2). Converts to UTC, sorts by (interval_start_utc, product), and
    drops duplicate (product, interval) pairs, keeping the first: this row
    order is a deliberate, stable convention (interval_start_utc primary so
    the file reads chronologically; product breaks ties within an interval).
    """
    lower = pd.Timestamp(start, tz=_CENTRAL_TZ)
    upper = pd.Timestamp(end + timedelta(days=1), tz=_CENTRAL_TZ)
    window = raw[(raw["Interval Start"] >= lower) & (raw["Interval Start"] < upper)]

    raw_products = [column for column in window.columns if column not in _RAW_ID_COLUMNS]
    unmapped = sorted(set(raw_products) - set(_PRODUCT_MAP))
    if unmapped:
        raise ValueError(f"Unknown AS product column(s) from gridstatus: {unmapped}")

    long = window.melt(
        id_vars=["Interval Start", "Interval End"],
        value_vars=raw_products,
        var_name="raw_product",
        value_name="price",
    )
    long = long.dropna(subset=["price"])

    canonical = pd.DataFrame(
        {
            "interval_start_utc": long["Interval Start"].dt.tz_convert("UTC"),
            "interval_end_utc": long["Interval End"].dt.tz_convert("UTC"),
            "iso": _ISO,
            "market": _MARKET,
            "product": long["raw_product"].map(_PRODUCT_MAP),
            "price": long["price"].astype("float64"),
        }
    )
    canonical["interval_start_utc"] = canonical["interval_start_utc"].astype("datetime64[us, UTC]")
    canonical["interval_end_utc"] = canonical["interval_end_utc"].astype("datetime64[us, UTC]")

    # kind="stable" so that if a duplicate (product, interval) appears, which
    # copy is kept deterministically reflects its original position in the
    # raw input.
    canonical = canonical.sort_values(["interval_start_utc", "product"], kind="stable")
    canonical = canonical.drop_duplicates(subset=["product", "interval_start_utc"], keep="first")
    canonical = canonical.reset_index(drop=True)
    return canonical[list(AS_CANONICAL_COLUMNS)]


def _validate(df: pd.DataFrame, start: date, end: date) -> None:
    """Assert canonical-AS-schema invariants for the requested window.

    Checks column names and dtypes, then per product: no duplicates, strict
    monotonicity, and no gaps between the later of `start` and that product's
    launch date (see `PRODUCT_LAUNCH`) and `end`. Iterates every known
    product, not just the ones present in `df`, so a product missing entirely
    is caught the same way as a partial gap. A gap raises listing every
    missing (product, interval) pair; never silently interpolated (spec
    item 5).
    """
    if list(df.columns) != list(AS_CANONICAL_COLUMNS):
        raise ValueError(f"Expected columns {list(AS_CANONICAL_COLUMNS)}, got {list(df.columns)}")

    expected_dtypes = {
        "interval_start_utc": "datetime64[us, UTC]",
        "interval_end_utc": "datetime64[us, UTC]",
        "iso": "object",
        "market": "object",
        "product": "object",
        "price": "float64",
    }
    bad_dtypes = {
        column: str(df[column].dtype)
        for column, expected in expected_dtypes.items()
        if str(df[column].dtype) != expected
    }
    if bad_dtypes:
        raise ValueError(f"Unexpected dtypes: {bad_dtypes}")

    missing_pairs: list[tuple[str, pd.Timestamp]] = []
    for product in sorted(set(_PRODUCT_MAP.values())):
        group = df.loc[df["product"] == product, "interval_start_utc"]
        if group.duplicated().any():
            raise ValueError(f"Duplicate interval_start_utc values for product {product}")
        if not group.is_monotonic_increasing:
            raise ValueError(f"interval_start_utc is not sorted increasing for product {product}")

        effective_start = max(start, PRODUCT_LAUNCH.get(product, date.min))
        if effective_start > end:
            # The whole requested window is before this product's launch:
            # nothing is expected, not even one interval (pd.date_range with
            # lower == upper still yields that single point under
            # inclusive="left", so this can't be delegated to date_range).
            continue
        lower_utc = pd.Timestamp(effective_start, tz=_CENTRAL_TZ).tz_convert("UTC")
        upper_utc = pd.Timestamp(end + timedelta(days=1), tz=_CENTRAL_TZ).tz_convert("UTC")
        expected_index = pd.date_range(lower_utc, upper_utc, freq="h", inclusive="left")
        missing = expected_index.difference(pd.DatetimeIndex(group))
        missing_pairs.extend((product, ts) for ts in missing)

    if missing_pairs:
        raise ValueError(
            f"Missing {len(missing_pairs)} (product, interval) pair(s) in [{start}, {end}]: "
            f"{[(product, ts.isoformat()) for product, ts in missing_pairs]}"
        )


def _cache_path(cache_dir: Path, start: date, end: date) -> Path:
    return cache_dir / f"AS_MCPC_{start.isoformat()}_{end.isoformat()}.parquet"


def fetch_as_prices(
    start: date,
    end: date,
    cache_dir: Path,
) -> pd.DataFrame:
    """Return canonical-schema day-ahead AS clearing prices (MCPCs) for all five products.

    Serves from the parquet cache under cache_dir when present; otherwise
    fetches via gridstatus, canonicalizes to AS_CANONICAL_COLUMNS, and writes
    the cache. MCPCs are system-wide (no location argument, spec item 1);
    callers should fetch once per window, not once per hub. Output is sorted,
    deduplicated, and validated on every return path (cache hit or fresh
    fetch), so a corrupted or hand-edited cache file fails loudly instead of
    propagating bad data.

    Covered by acceptance criteria: 8 (tests exercise this only via committed
    fixtures, no network in CI) and the canonical-schema requirements tested
    in tests/test_as_data.py. gridstatus itself is exercised only by `bess
    fetch` run manually.
    """
    cache_path = _cache_path(cache_dir, start, end)
    if cache_path.exists():
        logger.info("Loading AS MCPCs from cache: %s", cache_path)
        df = pd.read_parquet(cache_path)
    else:
        logger.info("Fetching AS MCPCs from gridstatus for [%s, %s]", start, end)
        raw = _fetch_raw(start, end)
        df = _canonicalize(raw, start, end)
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info("Cached AS MCPCs to %s", cache_path)

    _validate(df, start, end)
    return df

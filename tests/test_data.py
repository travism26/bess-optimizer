"""Tests for bess.data.prices canonicalization and caching (spec schema rules).

All tests run from committed fixtures under tests/fixtures/; the conftest
network guard enforces acceptance criterion 9 (gridstatus is only exercised by
`bess fetch` run manually). The one exception is the pytest.mark.manual test,
which touches the real network and is excluded from the default run and CI.
"""

from __future__ import annotations

import ast
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bess.data.prices import (
    CANONICAL_COLUMNS,
    _cache_path,
    _canonicalize,
    _validate,
    fetch_da_prices,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "hb_north_2023_07.parquet"
SPRING_FORWARD_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_03_12_raw.parquet"
FALL_BACK_RAW_FIXTURE = FIXTURES_DIR / "hb_north_2023_11_05_raw.parquet"


def _raw_row(
    hour: pd.Timestamp,
    spp: float,
    location: str = "HB_NORTH",
    location_type: str = "Trading Hub",
    market: str = "DAY_AHEAD_HOURLY",
) -> dict[str, object]:
    """Build one row in gridstatus's raw column shape for synthetic inputs."""
    return {
        "Interval Start": hour,
        "Interval End": hour + pd.Timedelta(1, unit="h"),
        "Location": location,
        "Location Type": location_type,
        "Market": market,
        "SPP": spp,
    }


# TODO(schema) Canonical schema: fetch_da_prices output has exactly the
#   CANONICAL_COLUMNS set with the spec dtypes (UTC microsecond timestamps,
#   float64 price), sorted, strictly increasing interval_start_utc, no
#   duplicates.


def test_frozen_fixture_matches_canonical_schema() -> None:
    """Acceptance criterion 8: the fixture exists, is small, loads, and validates."""
    assert JULY_FIXTURE.exists()
    assert JULY_FIXTURE.stat().st_size < 100_000

    df = pd.read_parquet(JULY_FIXTURE)
    _validate(df, "HB_NORTH", date(2023, 7, 1), date(2023, 7, 31))

    assert list(df.columns) == list(CANONICAL_COLUMNS)
    assert len(df) == 744
    assert str(df["interval_start_utc"].dtype) == "datetime64[us, UTC]"
    assert str(df["interval_end_utc"].dtype) == "datetime64[us, UTC]"
    assert df["price"].dtype == np.float64
    assert (df["iso"] == "ERCOT").all()
    assert (df["market"] == "DAY_AHEAD_HOURLY").all()
    assert (df["location"] == "HB_NORTH").all()
    assert (df["location_type"] == "Trading Hub").all()
    assert df["interval_start_utc"].is_monotonic_increasing
    assert df["interval_start_utc"].is_unique


def test_canonicalize_sorts_and_dedupes_raw_input() -> None:
    """Acceptance criterion 3: duplicate rows dropped, out-of-order input sorted."""
    start = end = date(2023, 7, 1)
    base = pd.Timestamp(start, tz="US/Central")
    raw = pd.DataFrame(
        [
            _raw_row(base + pd.Timedelta(1, unit="h"), spp=20.0),
            _raw_row(base, spp=10.0),  # first hour-0 row, kept on dedup
            _raw_row(base, spp=999.0),  # duplicate hour-0 row, dropped
        ]
    )

    canonical = _canonicalize(raw, start, end)

    assert len(canonical) == 2
    assert canonical["interval_start_utc"].is_monotonic_increasing
    assert canonical["interval_start_utc"].is_unique
    assert canonical.loc[0, "price"] == 10.0
    assert canonical.loc[1, "price"] == 20.0


# TODO(gaps) Gap detection: a fixture with a missing interval inside the
#   requested window fails loudly listing the missing intervals; it is never
#   silently interpolated.


def test_validate_raises_on_missing_interval() -> None:
    """A synthetic input missing one hour raises, message names the timestamp."""
    start = end = date(2023, 1, 1)
    hours = pd.date_range(
        pd.Timestamp(start, tz="US/Central").tz_convert("UTC"), periods=24, freq="h"
    )
    missing_hour = hours[12]
    kept_hours = hours.delete(12)

    df = pd.DataFrame(
        {
            "interval_start_utc": kept_hours,
            "interval_end_utc": kept_hours + pd.Timedelta(1, unit="h"),
            "iso": "ERCOT",
            "market": "DAY_AHEAD_HOURLY",
            "location": "HB_NORTH",
            "location_type": "Trading Hub",
            "price": 10.0,
        }
    )
    df["interval_start_utc"] = df["interval_start_utc"].astype("datetime64[us, UTC]")
    df["interval_end_utc"] = df["interval_end_utc"].astype("datetime64[us, UTC]")

    with pytest.raises(ValueError, match="Missing 1 interval") as excinfo:
        _validate(df, "HB_NORTH", start, end)
    assert missing_hour.isoformat() in str(excinfo.value)


# TODO(gotcha-1, DST) DST handling: spring-forward days have 23 hours and
#   fall-back days have 25 after conversion to UTC; never assume 24 rows per
#   calendar day. Fixture slices must cover both 2023 DST transitions.


def test_spring_forward_day_has_23_continuous_hours() -> None:
    """Acceptance criterion 2: 2023-03-12 (spring forward) yields 23 rows."""
    raw = pd.read_parquet(SPRING_FORWARD_RAW_FIXTURE)
    canonical = _canonicalize(raw, date(2023, 3, 12), date(2023, 3, 12))

    assert len(canonical) == 23
    deltas = canonical["interval_start_utc"].diff().dropna()
    assert (deltas == pd.Timedelta(1, unit="h")).all()


def test_fall_back_day_has_25_continuous_hours() -> None:
    """Acceptance criterion 2: 2023-11-05 (fall back) yields 25 rows."""
    raw = pd.read_parquet(FALL_BACK_RAW_FIXTURE)
    canonical = _canonicalize(raw, date(2023, 11, 5), date(2023, 11, 5))

    assert len(canonical) == 25
    deltas = canonical["interval_start_utc"].diff().dropna()
    assert (deltas == pd.Timedelta(1, unit="h")).all()


# TODO(gotcha-3) Negative prices survive ingestion unclipped and unfiltered.


def test_negative_prices_pass_through_unmodified() -> None:
    """Acceptance criterion 5: negative prices are not clipped, filtered, or NaN'd."""
    start = end = date(2023, 7, 1)
    base = pd.Timestamp(start, tz="US/Central")
    raw = pd.DataFrame(
        [
            _raw_row(base, spp=-57.34),
            _raw_row(base + pd.Timedelta(1, unit="h"), spp=0.0),
        ]
    )

    canonical = _canonicalize(raw, start, end)

    assert not canonical["price"].isna().any()
    assert canonical.loc[0, "price"] == pytest.approx(-57.34)
    assert canonical.loc[1, "price"] == pytest.approx(0.0)


# TODO(AC-9) Cache behavior: a second fetch_da_prices call over the same window
#   is served entirely from the parquet cache (no network; the conftest guard
#   would raise if it tried).


def test_fetch_da_prices_serves_from_parquet_cache(tmp_path: Path) -> None:
    """Acceptance criterion 7: cache hits never touch the network.

    The autouse block_network fixture (tests/conftest.py) would raise if either
    call below fell through to gridstatus, so two successful calls prove the
    cache path is taken both times.
    """
    location, start, end = "HB_NORTH", date(2023, 7, 1), date(2023, 7, 31)
    cache_path = _cache_path(tmp_path, location, start, end)
    shutil.copy(JULY_FIXTURE, cache_path)
    expected = pd.read_parquet(JULY_FIXTURE)

    first = fetch_da_prices(location, start, end, tmp_path)
    second = fetch_da_prices(location, start, end, tmp_path)

    pd.testing.assert_frame_equal(first, expected)
    pd.testing.assert_frame_equal(second, expected)


def _imports_gridstatus(path: Path) -> bool:
    """True if `path` contains an `import gridstatus` or `from gridstatus import ...`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "gridstatus" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "gridstatus":
            return True
    return False


def test_gridstatus_import_confined_to_data_modules() -> None:
    """Acceptance criterion 6: only data/prices.py and data/as_prices.py may import gridstatus."""
    src_root = Path(__file__).parent.parent / "src" / "bess"
    allowed_modules = {src_root / "data" / "prices.py", src_root / "data" / "as_prices.py"}

    offenders = [
        path
        for path in src_root.rglob("*.py")
        if path not in allowed_modules and _imports_gridstatus(path)
    ]

    assert offenders == []


@pytest.mark.manual
def test_manual_live_fetch_returns_canonical_schema(tmp_path: Path) -> None:
    """Live gridstatus fetch. Excluded from the default run and CI.

    Run explicitly with: uv run pytest -m manual tests/test_data.py
    """
    location, start, end = "HB_NORTH", date(2023, 7, 1), date(2023, 7, 1)

    df = fetch_da_prices(location, start, end, tmp_path)

    assert list(df.columns) == list(CANONICAL_COLUMNS)
    assert len(df) == 24

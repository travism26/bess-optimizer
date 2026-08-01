"""Tests for bess.data.as_prices canonicalization and caching (spec schema rules).

All tests run from committed fixtures under tests/fixtures/ or synthetic
frames built in-test; the conftest network guard enforces acceptance
criterion 8 (gridstatus is only exercised by `bess fetch` run manually). The
one exception is the pytest.mark.manual test, which touches the real network
and is excluded from the default run and CI.
"""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bess.data.as_prices import (
    AS_CANONICAL_COLUMNS,
    ECRS_LAUNCH,
    _cache_path,
    _canonicalize,
    _validate,
    fetch_as_prices,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JULY_FIXTURE = FIXTURES_DIR / "as_mcpc_2023_07.parquet"
SPRING_FORWARD_RAW_FIXTURE = FIXTURES_DIR / "as_2023_03_12_raw.parquet"
FALL_BACK_RAW_FIXTURE = FIXTURES_DIR / "as_2023_11_05_raw.parquet"

_ALL_PRODUCTS = ("ECRS", "NONSPIN", "REG_DOWN", "REG_UP", "RRS")
_LIVE_PRODUCTS = ("NONSPIN", "REG_DOWN", "REG_UP", "RRS")  # live for all of 2023, unlike ECRS


def _raw_row(
    hour: pd.Timestamp,
    regdn: float | None = 1.0,
    regup: float | None = 1.0,
    rrs: float | None = 1.0,
    nspin: float | None = 1.0,
    ecrs: float | None = 1.0,
) -> dict[str, object]:
    """Build one row in the post-`Ercot.parse_doc` wide AS shape (`_fetch_raw`'s output)."""
    return {
        "Interval Start": hour,
        "Interval End": hour + pd.Timedelta(1, unit="h"),
        "REGDN": regdn,
        "REGUP": regup,
        "RRS": rrs,
        "NSPIN": nspin,
        "ECRS": ecrs,
    }


def _full_day_canonical_frame(day: date, products: tuple[str, ...]) -> pd.DataFrame:
    """A synthetic canonical AS frame with complete hourly coverage for `products` on `day`."""
    hours_utc = pd.date_range(
        pd.Timestamp(day, tz="US/Central").tz_convert("UTC"),
        pd.Timestamp(day + timedelta(days=1), tz="US/Central").tz_convert("UTC"),
        freq="h",
        inclusive="left",
    )
    frames = [
        pd.DataFrame(
            {
                "interval_start_utc": hours_utc,
                "interval_end_utc": hours_utc + pd.Timedelta(1, unit="h"),
                "iso": "ERCOT",
                "market": "DAM_AS",
                "product": product,
                "price": 1.0,
            }
        )
        for product in products
    ]
    df = pd.concat(frames, ignore_index=True)
    df["interval_start_utc"] = df["interval_start_utc"].astype("datetime64[us, UTC]")
    df["interval_end_utc"] = df["interval_end_utc"].astype("datetime64[us, UTC]")
    return df.sort_values(["interval_start_utc", "product"], kind="stable").reset_index(drop=True)


def test_ecrs_launch_is_the_documented_named_constant() -> None:
    """Spec item 2: the ECRS launch date is a named constant, not a magic literal."""
    assert date(2023, 6, 10) == ECRS_LAUNCH


def test_frozen_fixture_matches_canonical_schema() -> None:
    """Acceptance criteria 1-2: the fixture exists, is small, loads, and validates."""
    assert JULY_FIXTURE.exists()
    assert JULY_FIXTURE.stat().st_size < 100_000

    df = pd.read_parquet(JULY_FIXTURE)
    _validate(df, date(2023, 7, 1), date(2023, 7, 31))

    assert list(df.columns) == list(AS_CANONICAL_COLUMNS)
    assert len(df) == 744 * 5
    assert str(df["interval_start_utc"].dtype) == "datetime64[us, UTC]"
    assert str(df["interval_end_utc"].dtype) == "datetime64[us, UTC]"
    assert df["price"].dtype == np.float64
    assert (df["iso"] == "ERCOT").all()
    assert (df["market"] == "DAM_AS").all()
    assert set(df["product"]) == set(_ALL_PRODUCTS)

    counts = df["product"].value_counts()
    assert (counts == 744).all()
    for _, group in df.groupby("product"):
        assert group["interval_start_utc"].is_monotonic_increasing
        assert group["interval_start_utc"].is_unique


def test_canonicalize_sorts_and_dedupes_raw_input() -> None:
    """Duplicate (product, interval) rows dropped, out-of-order input sorted."""
    start = end = date(2023, 7, 1)
    base = pd.Timestamp(start, tz="US/Central")
    raw = pd.DataFrame(
        [
            _raw_row(base + pd.Timedelta(1, unit="h"), regup=20.0),
            _raw_row(base, regup=10.0),  # first hour-0 row, kept on dedup
            _raw_row(base, regup=999.0),  # duplicate hour-0 row, dropped
        ]
    )

    canonical = _canonicalize(raw, start, end)
    regup = canonical.loc[canonical["product"] == "REG_UP"].reset_index(drop=True)

    assert len(regup) == 2
    assert regup["interval_start_utc"].is_monotonic_increasing
    assert regup["interval_start_utc"].is_unique
    assert regup.loc[0, "price"] == 10.0
    assert regup.loc[1, "price"] == 20.0


def test_canonicalize_raises_on_unknown_product_column() -> None:
    """Spec gotcha 2: an unrecognized raw product column is never passed through."""
    start = end = date(2023, 7, 1)
    base = pd.Timestamp(start, tz="US/Central")
    raw = pd.DataFrame([_raw_row(base)])
    raw["MYSTERY"] = 5.0

    with pytest.raises(ValueError, match="Unknown AS product column"):
        _canonicalize(raw, start, end)


def test_validate_raises_on_missing_interval_for_one_product() -> None:
    """A synthetic input missing one hour for one product raises, naming (product, interval)."""
    day = date(2023, 1, 1)
    df = _full_day_canonical_frame(day, _LIVE_PRODUCTS)
    regup_hours = df.loc[df["product"] == "REG_UP", "interval_start_utc"]
    missing_timestamp = regup_hours.iloc[12]
    df = df.loc[
        ~((df["product"] == "REG_UP") & (df["interval_start_utc"] == missing_timestamp))
    ].reset_index(drop=True)

    with pytest.raises(ValueError, match="Missing 1") as excinfo:
        _validate(df, day, day)
    assert "REG_UP" in str(excinfo.value)
    assert missing_timestamp.isoformat() in str(excinfo.value)


def test_ecrs_launch_rule_allows_missing_ecrs_before_launch() -> None:
    """Acceptance criterion 4: a window starting 2023-01-01 validates ECRS only from launch.

    The four always-live products are given complete hourly coverage through
    2023-06-09 (the day before ECRS launched); ECRS has no rows at all in
    this frame. Validation must still pass because ECRS's effective start
    (the later of the requested start and its launch date) falls after the
    window end.
    """
    start, end = date(2023, 1, 1), date(2023, 6, 9)
    hours_utc = pd.date_range(
        pd.Timestamp(start, tz="US/Central").tz_convert("UTC"),
        pd.Timestamp(end + timedelta(days=1), tz="US/Central").tz_convert("UTC"),
        freq="h",
        inclusive="left",
    )
    frames = [
        pd.DataFrame(
            {
                "interval_start_utc": hours_utc,
                "interval_end_utc": hours_utc + pd.Timedelta(1, unit="h"),
                "iso": "ERCOT",
                "market": "DAM_AS",
                "product": product,
                "price": 1.0,
            }
        )
        for product in _LIVE_PRODUCTS
    ]
    df = pd.concat(frames, ignore_index=True)
    df["interval_start_utc"] = df["interval_start_utc"].astype("datetime64[us, UTC]")
    df["interval_end_utc"] = df["interval_end_utc"].astype("datetime64[us, UTC]")
    df = df.sort_values(["interval_start_utc", "product"], kind="stable").reset_index(drop=True)

    assert "ECRS" not in set(df["product"])
    _validate(df, start, end)  # must not raise


def test_spring_forward_day_has_23_rows_per_product_and_no_ecrs() -> None:
    """Acceptance criterion 3: 2023-03-12 (spring forward, pre-ECRS) yields 23 rows x 4 products."""
    raw = pd.read_parquet(SPRING_FORWARD_RAW_FIXTURE)
    canonical = _canonicalize(raw, date(2023, 3, 12), date(2023, 3, 12))

    assert set(canonical["product"]) == set(_LIVE_PRODUCTS)
    counts = canonical["product"].value_counts()
    assert (counts == 23).all()
    for _, group in canonical.groupby("product"):
        deltas = group["interval_start_utc"].diff().dropna()
        assert (deltas == pd.Timedelta(1, unit="h")).all()


def test_fall_back_day_has_25_rows_per_product() -> None:
    """Acceptance criterion 3: 2023-11-05 (fall back) yields 25 rows across all 5 products."""
    raw = pd.read_parquet(FALL_BACK_RAW_FIXTURE)
    canonical = _canonicalize(raw, date(2023, 11, 5), date(2023, 11, 5))

    assert set(canonical["product"]) == set(_ALL_PRODUCTS)
    counts = canonical["product"].value_counts()
    assert (counts == 25).all()
    for _, group in canonical.groupby("product"):
        deltas = group["interval_start_utc"].diff().dropna()
        assert (deltas == pd.Timedelta(1, unit="h")).all()


def test_zero_and_negative_prices_pass_through_unmodified() -> None:
    """Acceptance criterion 7: zero and negative MCPCs are not clipped or filtered."""
    start = end = date(2023, 7, 1)
    base = pd.Timestamp(start, tz="US/Central")
    raw = pd.DataFrame(
        [
            _raw_row(base, regup=0.0),
            _raw_row(base + pd.Timedelta(1, unit="h"), regup=-5.0),
        ]
    )

    canonical = _canonicalize(raw, start, end)
    regup = canonical.loc[canonical["product"] == "REG_UP"].reset_index(drop=True)

    assert not regup["price"].isna().any()
    assert regup.loc[0, "price"] == pytest.approx(0.0)
    assert regup.loc[1, "price"] == pytest.approx(-5.0)


def test_fetch_as_prices_serves_from_parquet_cache(tmp_path: Path) -> None:
    """Acceptance criterion 6: cache hits never touch the network.

    The autouse block_network fixture (tests/conftest.py) would raise if
    either call below fell through to gridstatus, so two successful calls
    prove the cache path is taken both times.
    """
    start, end = date(2023, 7, 1), date(2023, 7, 31)
    cache_path = _cache_path(tmp_path, start, end)
    shutil.copy(JULY_FIXTURE, cache_path)
    expected = pd.read_parquet(JULY_FIXTURE)

    first = fetch_as_prices(start, end, tmp_path)
    second = fetch_as_prices(start, end, tmp_path)

    pd.testing.assert_frame_equal(first, expected)
    pd.testing.assert_frame_equal(second, expected)


@pytest.mark.manual
def test_manual_live_fetch_returns_canonical_schema(tmp_path: Path) -> None:
    """Live gridstatus fetch. Excluded from the default run and CI.

    Run explicitly with: uv run pytest -m manual tests/test_as_data.py
    """
    start = end = date(2023, 7, 1)

    df = fetch_as_prices(start, end, tmp_path)

    assert list(df.columns) == list(AS_CANONICAL_COLUMNS)
    assert len(df) == 24 * 5

"""Tests for bess.data.prices canonicalization and caching (spec schema rules).

All tests run from committed fixtures under tests/fixtures/; the conftest
network guard enforces acceptance criterion 9 (gridstatus is only exercised by
`bess fetch` manually).
"""

# TODO(schema) Canonical schema: fetch_da_prices output has exactly the
#   CANONICAL_COLUMNS set with the spec dtypes (UTC microsecond timestamps,
#   float64 price), sorted, strictly increasing interval_start_utc, no
#   duplicates.

# TODO(gaps) Gap detection: a fixture with a missing interval inside the
#   requested window fails loudly listing the missing intervals; it is never
#   silently interpolated.

# TODO(gotcha-1, DST) DST handling: spring-forward days have 23 hours and
#   fall-back days have 25 after conversion to UTC; never assume 24 rows per
#   calendar day. Fixture slices must cover both 2023 DST transitions.

# TODO(gotcha-3) Negative prices survive ingestion unclipped and unfiltered.

# TODO(AC-9) Cache behavior: a second fetch_da_prices call over the same window
#   is served entirely from the parquet cache (no network; the conftest guard
#   would raise if it tried).

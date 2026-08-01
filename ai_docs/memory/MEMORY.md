# Project Memory

Lessons and conventions learned by the ADW harness across runs on
this codebase. Edit entries by hand under `entries/`, or regenerate
via `uv run adws/travis/travis_dream.py --working-dir <this repo>`.

## Conventions
- network-test-marker-convention — Live/network tests use pytest.mark.manual, excluded by default via addopts and a marker-aware conftest guard

## Lessons
- ast-based-import-confinement-guard — Guard tests that confine an import (e.g. gridstatus, highspy) to one module should parse the AST, not grep source text
- backtest-shared-solve-for-metrics-and-plots — Frozen BacktestResult lacks per-interval dispatch arrays; share one LP solve for metrics and plots
- capture-rate-fixture-can-equal-one — Foresight capture rate can legitimately equal exactly 1.0 on fixtures with a day-separable optimum
- determinism-tests-exclude-wallclock-fields — Byte-identical determinism tests/output must exclude wall-clock fields like solve_time_seconds, per JSON writer
- lp-optimizer-degeneracy-in-tests — LP dispatch optimum is often non-unique; assert net dispatch/revenue, not raw per-interval vertex values

## Pitfalls
- adw-worktree-port-file-cleanup — ADW port-allocation file (.ports.env) recurringly gets committed mid-pipeline; check git status and untrack before finalizing
- as-mcpc-archive-wide-format — ERCOT's yearly AS MCPC archive (MIS report 13091) is wide-format with a trailing-space header and non-canonical product codes
- dst-local-hour-mapping-both-directions — Local-hour-of-day mapping across DST must handle 23h/25h on both source and target days, not just the target
- fetch-da-prices-per-location-redownload — fetch_da_prices redownloads the full yearly ERCOT archive once per location, not shared across locations
- gridstatus-ercot-dam-api-pitfall — gridstatus 'recent/current' report methods are unreliable for historical backfill; use yearly-archive report types instead
- highspy-untyped-mypy — highspy has no type stubs; values read from it need explicit casts/annotations to satisfy mypy warn_return_any
- matplotlib-agg-backend-for-plots — src/bess/viz/plots.py must force the Agg backend; default backend can't render headless in CI
- metrics-json-unqualified-filename-collision — bess backtest wrote perfect and rolling metrics to the same unqualified filename, overwriting each other
- timestamp-plus-timedelta-days-crosses-dst — Timestamp + Timedelta(days=N) on tz-aware data adds exact elapsed hours, not calendar days, and drifts across DST

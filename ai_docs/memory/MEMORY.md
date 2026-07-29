# Project Memory

Lessons and conventions learned by the ADW harness across runs on
this codebase. Edit entries by hand under `entries/`, or regenerate
via `uv run adws/travis/travis_dream.py --working-dir <this repo>`.

## Conventions
- network-test-marker-convention — Live/network tests use pytest.mark.manual, excluded by default via addopts and a marker-aware conftest guard

## Lessons
- ast-based-import-confinement-guard — Guard tests that confine an import (e.g. gridstatus, highspy) to one module should parse the AST, not grep source text
- backtest-shared-solve-for-metrics-and-plots — Frozen BacktestResult lacks per-interval dispatch arrays; share one LP solve for metrics and plotting
- determinism-tests-exclude-wallclock-fields — Byte-identical determinism tests/output must exclude wall-clock fields like solve_time_seconds
- lp-optimizer-degeneracy-in-tests — LP dispatch optimum is often non-unique; assert net dispatch/revenue, not raw per-interval vertex values

## Pitfalls
- adw-worktree-port-file-cleanup — ADW port-allocation file (.ports.env) recurringly gets committed mid-pipeline; check git status and untrack before finalizing
- fetch-da-prices-per-location-redownload — fetch_da_prices redownloads the full yearly ERCOT archive once per location, not shared across locations
- gridstatus-ercot-dam-api-pitfall — gridstatus Ercot.get_spp() is unreliable for historical DAM data; use get_dam_spp(year) instead
- highspy-untyped-mypy — highspy has no type stubs; values read from it need explicit casts/annotations to satisfy mypy warn_return_any
- matplotlib-agg-backend-for-plots — src/bess/viz/plots.py must force the Agg backend; default backend can't render headless in CI

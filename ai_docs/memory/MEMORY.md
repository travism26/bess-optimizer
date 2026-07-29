# Project Memory

Lessons and conventions learned by the ADW harness across runs on
this codebase. Edit entries by hand under `entries/`, or regenerate
via `uv run adws/travis/travis_dream.py --working-dir <this repo>`.

## Conventions
- network-test-marker-convention — Live/network tests use pytest.mark.manual, excluded by default via addopts and a marker-aware conftest guard

## Lessons
- ast-based-import-confinement-guard — Guard tests that confine an import (e.g. gridstatus) to one module should parse the AST, not grep source text

## Pitfalls
- adw-worktree-port-file-cleanup — ADW port-allocation file can get committed mid-pipeline; check git status and untrack before finalizing
- fetch-da-prices-per-location-redownload — fetch_da_prices redownloads the full yearly ERCOT archive once per location, not shared across locations
- gridstatus-ercot-dam-api-pitfall — gridstatus Ercot.get_spp() is unreliable for historical DAM data; use get_dam_spp(year) instead

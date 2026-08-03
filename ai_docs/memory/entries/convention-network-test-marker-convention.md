---
name: network-test-marker-convention
description: Live/network tests use pytest.mark.manual, excluded by default via addopts and a marker-aware conftest guard
type: convention
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18, 8694b681]
date: 2026-07-29
---

Tests that must hit the real network (e.g. a live gridstatus fetch) are marked `@pytest.mark.manual`, registered in pyproject.toml, and excluded from the default `pytest` run via addopts (so CI never runs them). tests/conftest.py's network-blocking socket guard is marker-aware: it must check for the `manual` marker before blocking sockets, otherwise manual tests can never actually reach the network even when deliberately run with `-m manual`. When adding any new test that needs real network access, follow this pattern rather than inventing a new opt-out mechanism.

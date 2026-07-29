"""Shared test configuration.

Acceptance criterion 9: no network in CI. The autouse guard below makes any
socket connection attempt fail loudly, so a test that accidentally reaches
gridstatus (or anything else) breaks immediately instead of passing on a
developer machine and flaking in CI.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Fail any test that attempts an outbound socket connection.

    Tests marked `manual` are exempt: they exist specifically to exercise the
    real gridstatus network call and are excluded from the default run and CI
    (see pyproject.toml addopts), so a developer running them explicitly with
    `-m manual` expects them to actually reach the network.
    """
    if request.node.get_closest_marker("manual") is not None:
        yield
        return

    def guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "Network access is blocked in tests (acceptance criterion 9). "
            "Use fixtures under tests/fixtures/ instead."
        )

    monkeypatch.setattr(socket.socket, "connect", guard)
    yield

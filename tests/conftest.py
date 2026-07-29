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
def block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that attempts an outbound socket connection."""

    def guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "Network access is blocked in tests (acceptance criterion 9). "
            "Use fixtures under tests/fixtures/ instead."
        )

    monkeypatch.setattr(socket.socket, "connect", guard)
    yield

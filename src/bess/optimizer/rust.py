"""Lazy-loaded wrapper around the Rust dispatch engine (specs/M4a_rust_scaffold.md).

`optimize_dispatch_rust` is the frozen, Python-visible seam
(specs/M4_rust_engine.md, "Frozen interfaces") that later slices wire up to
the compiled `bess_engine` PyO3 extension: M4b (specs/M4b_rust_lp_core.md)
hand-writes the Rust LP core, M4c (specs/M4c_engine_parity_bench.md) wires
its output through this wrapper. This module is the ONLY place in src/bess
allowed to import bess_engine; tests/test_rust_scaffold.py enforces that
with the same AST-based import-confinement pattern used for gridstatus and
highspy.
"""

from __future__ import annotations

from types import ModuleType
from typing import cast

import numpy as np

from bess.models import BatterySpec, DispatchResult

_BUILD_COMMAND = "uv run maturin develop --manifest-path rust/bess_engine/Cargo.toml"


def _load_engine() -> ModuleType:
    """Import the compiled bess_engine extension, or raise a clear fix-it error."""
    try:
        import bess_engine
    except ImportError as exc:
        raise ImportError(
            f"The bess_engine Rust extension is not built. Run `{_BUILD_COMMAND}` and retry."
        ) from exc
    return cast(ModuleType, bess_engine)


def engine_available() -> bool:
    """True if the bess_engine Rust extension is importable in this venv."""
    try:
        _load_engine()
    except ImportError:
        return False
    return True


def optimize_dispatch_rust(
    prices: np.ndarray,
    dt_hours: float,
    battery: BatterySpec,
) -> DispatchResult:
    """Rust port of optimize_dispatch (specs/M4_rust_engine.md, "Frozen interfaces").

    Not implemented yet. The LP core is hand-written in M4b
    (specs/M4b_rust_lp_core.md) and wired up to this wrapper in M4c
    (specs/M4c_engine_parity_bench.md); this scaffold slice only proves the
    PyO3 -> maturin -> venv -> pytest round trip via bess_engine.engine_info().

    Raises:
        NotImplementedError: always, until M4b/M4c land.
    """
    raise NotImplementedError(
        "optimize_dispatch_rust is not implemented yet: the LP core lands in M4b "
        "(specs/M4b_rust_lp_core.md) and is wired up here in M4c "
        "(specs/M4c_engine_parity_bench.md)."
    )

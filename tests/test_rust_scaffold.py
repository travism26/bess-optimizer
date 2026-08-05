"""Tests for the M4a Rust scaffold (specs/M4a_rust_scaffold.md, acceptance criteria).

Only `test_engine_info_reports_versions` needs the compiled bess_engine
extension and is skipped cleanly when it is absent (criterion 3); the other
three tests, including the import-confinement guard, always run so criterion
6 cannot be accidentally silenced alongside the extension-gated test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from bess.models import BatterySpec
from bess.optimizer.rust import _load_engine, engine_available, optimize_dispatch_rust


def _default_battery() -> BatterySpec:
    return BatterySpec(power_mw=100.0, energy_mwh=200.0, charge_eff=0.927, discharge_eff=0.927)


def test_engine_info_reports_versions() -> None:
    """Acceptance criterion 2: engine_info() proves the highs-sys native link."""
    if not engine_available():
        pytest.skip(
            "bess_engine extension not built; run "
            "`uv run maturin develop --manifest-path rust/bess_engine/Cargo.toml`"
        )

    engine = _load_engine()
    info = engine.engine_info()

    assert set(info) >= {"crate_version", "highs_version"}
    assert isinstance(info["crate_version"], str) and info["crate_version"]
    assert isinstance(info["highs_version"], str) and info["highs_version"]


def test_optimize_dispatch_rust_is_not_implemented_yet() -> None:
    """Acceptance criterion 7: raises NotImplementedError naming M4b/M4c."""
    prices = np.array([10.0, 20.0, 30.0])

    with pytest.raises(NotImplementedError, match="M4b"):
        optimize_dispatch_rust(prices, dt_hours=1.0, battery=_default_battery())


def _imports_bess_engine(path: Path) -> bool:
    """True if `path` contains an `import bess_engine` or `from bess_engine import ...`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "bess_engine" for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "bess_engine":
            return True
    return False


def test_bess_engine_import_confined_to_rust_module() -> None:
    """Acceptance criterion 6: only optimizer/rust.py may import bess_engine."""
    src_root = Path(__file__).parent.parent / "src" / "bess"
    allowed_modules = {src_root / "optimizer" / "rust.py"}

    offenders = [
        path
        for path in src_root.rglob("*.py")
        if path not in allowed_modules and _imports_bess_engine(path)
    ]

    assert offenders == []


def test_confinement_guard_detects_a_doctored_module(tmp_path: Path) -> None:
    """Proves _imports_bess_engine actually flags a violation, not just passing vacuously."""
    doctored = tmp_path / "doctored.py"
    doctored.write_text("import bess_engine\n")
    clean = tmp_path / "clean.py"
    clean.write_text("import numpy as np\n")

    assert _imports_bess_engine(doctored) is True
    assert _imports_bess_engine(clean) is False

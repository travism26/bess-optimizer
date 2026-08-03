//! bess_engine: PyO3 extension module scaffold for the M4 Rust dispatch engine.
//!
//! specs/M4a_rust_scaffold.md: this slice is deliberately boilerplate. The
//! only Python-visible surface is `engine_info()`, a hello-world function
//! that proves the PyO3 -> maturin -> venv round trip and, by calling into
//! highs-sys directly, that the native HiGHS link works. No LP construction
//! or `optimize_dispatch` entry point lives here: that name and all solver
//! logic belong to specs/M4b_rust_lp_core.md.

use std::ffi::CStr;

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Read the linked HiGHS library version as a `String`.
///
/// # Safety
///
/// `Highs_version()` returns a pointer to a static, NUL-terminated C string
/// owned by the HiGHS library; it is never null and outlives the process, so
/// wrapping it in `CStr::from_ptr` and copying it into an owned `String` is
/// sound for the lifetime of this call.
fn highs_version() -> String {
    let c_version = unsafe { CStr::from_ptr(highs_sys::Highs_version()) };
    c_version.to_string_lossy().into_owned()
}

/// Hello-world entry point proving the PyO3 -> maturin -> venv -> pytest
/// round trip and the highs-sys native link, ahead of any LP logic (M4b).
#[pyfunction]
fn engine_info(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let info = PyDict::new(py);
    info.set_item("crate_version", env!("CARGO_PKG_VERSION"))?;
    info.set_item("highs_version", highs_version())?;
    Ok(info)
}

#[pymodule]
fn bess_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(engine_info, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::highs_version;

    #[test]
    fn highs_version_is_non_empty() {
        assert!(!highs_version().is_empty());
    }
}

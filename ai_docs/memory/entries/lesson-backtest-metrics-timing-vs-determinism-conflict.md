---
name: backtest-metrics-timing-vs-determinism-conflict
description: M1c spec requires a wall-clock solve_time_seconds in metrics JSON AND byte-identical output across runs; these conflict
type: lesson
source_adw_ids: [5dbaba17]
date: 2026-07-29
---

specs/M1c_backtest_cli.md AC-3 requires solve wall-time in the metrics JSON (mirroring the master spec's runtime field) while AC-4 requires two consecutive backtest runs on the fixture to produce byte-identical JSON. A raw wall-clock measurement is never identical across runs, so implementing both literally is impossible. When building run_backtest and its determinism test, exclude the timing field (or any wall-clock value) from the byte-identity comparison used to verify AC-4 (e.g. compare all keys except solve_time_seconds, or diff after stripping/rounding it), and document that choice explicitly rather than silently dropping determinism or timing. Likely to recur in any future spec asking for both a performance metric and reproducible output (e.g. M4 Rust engine parity tests).

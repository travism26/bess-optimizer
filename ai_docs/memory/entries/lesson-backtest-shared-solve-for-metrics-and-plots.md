---
name: backtest-shared-solve-for-metrics-and-plots
description: Frozen BacktestResult lacks per-interval dispatch arrays; share one LP solve for metrics and plots
type: lesson
source_adw_ids: [27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63]
date: 2026-07-30
---

The master-spec frozen `BacktestResult` (src/bess/models.py) does not carry per-interval charge/discharge/SoC arrays, but the dispatch-detail plot needs them. src/bess/backtest/runner.py splits `run_backtest` into two non-frozen helpers: `solve_dispatch` (runs optimize_dispatch once, times it) and `metrics_from_dispatch` (computes all metrics from that result). The CLI's `bess backtest` and `bess plot` commands both need this same solved dispatch, so cli.py factors a shared `_run_location` helper to solve once and reuse for both the metrics JSON and the dispatch plot rather than re-solving the LP twice per location. This 'frozen entry point + non-frozen solve helper, score via shared metrics_from_dispatch' pattern was reused again for M2a's rolling-horizon runner (src/bess/backtest/rolling.py), confirming it generalizes: follow it for any future command, mode, or engine (e.g. M4 Rust) that needs both aggregate metrics and raw dispatch arrays from the same optimizer run.

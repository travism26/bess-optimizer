# Task Runbook

The ordered queue of ADW pipeline runs for this project. One task = one spec =
one pipeline run = one PR. Work top to bottom: kick off the next unchecked
task, review its PR, merge, tick the box, move on. Do not start a task whose
dependencies are unmerged.

## How to run a task

From the repo root, with a clean working tree and `gh` authenticated:

```
uv run adws/travis/travis_sdlc.py specs/<task-spec>.md --worktree --draft-pr --dream --tui
```

What happens: the spec is used verbatim (planning is skipped for `specs/`
paths), the run executes in an isolated worktree under `trees/<adw-id>/` on
branch `adw/<adw-id>`, a draft PR opens with a live phase checklist, and on
success the PR flips to ready for review. Merging is always manual. `--dream`
consolidates a successful run into `ai_docs/memory/`, which rides the PR (and
is public; it only ever contains technical build notes).

Useful variations:

- Resume an interrupted run: add `--resume` with the same adw-id.
- Best-of-N on a hard task: add `--attempts 3 --test-command "uv run pytest -q"`.
- Keep noise down on a trivial task: `--skip-document`.

## M1: Python core

- [x] **T1: Data layer** `specs/M1a_data_layer.md`
  - Depends on: nothing (scaffold only).
  - Run: `uv run adws/travis/travis_sdlc.py specs/M1a_data_layer.md --worktree --draft-pr --dream --tui`
  - Note: the frozen fixture (`tests/fixtures/hb_north_2023_07.parquet`) is
    generated once via a real gridstatus fetch. The build agent needs network
    for that single step; tests and CI stay offline.
  - PR: #1  Merged: 2026-07-29 (adw 3c648beb)

- [x] **T2: LP optimizer** `specs/M1b_optimizer.md`
  - Depends on: nothing technically (independent of T1), sequenced after T1
    by choice so PRs land one at a time.
  - Run: `uv run adws/travis/travis_sdlc.py specs/M1b_optimizer.md --worktree --draft-pr --dream --tui`
  - PR: #2  Merged: 2026-07-29 (adw 3b9cf1a9)

- [x] **T3: Backtest, CLI, plots** `specs/M1c_backtest_cli.md`
  - Depends on: T1 AND T2 merged to main (integrates both).
  - Run: `uv run adws/travis/travis_sdlc.py specs/M1c_backtest_cli.md --worktree --draft-pr --dream --tui`
  - Note: finishes the M1 definition of done, including the README results
    section with real numbers from the fixture month.
  - PR: #4  Merged: 2026-07-29 (adw 27b2b22d; first attempt 5dbaba17 failed, PR #3 closed)

## M2: Rolling horizon + benchmarks

Master spec: `specs/M2_rolling_and_benchmarks.md` (approved 2026-07-29 via
lavish review; design decisions recorded there).

- [x] **T4: Rolling-horizon dispatch** `specs/M2a_rolling_horizon.md`
  - Depends on: M1 merged only. Independent of T5.
  - Run: `uv run adws/travis/travis_sdlc.py specs/M2a_rolling_horizon.md --worktree --draft-pr --dream --tui`
  - Headline goldens: two-day foresight case (perfect 275.0 vs persistence
    0.0, exact) and the M1 equivalence test.
  - PR: #5  Merged: 2026-07-30 (adw cea65174)

- [x] **T5: Benchmarks + sweeps** `specs/M2b_benchmarks.md`
  - Depends on: T4 merged (capture rate consumes rolling results).
  - Run: `uv run adws/travis/travis_sdlc.py specs/M2b_benchmarks.md --worktree --draft-pr --dream --tui`
  - Delivers the M2 headline: foresight capture rate, plus TB2/TB4, sweeps,
    README section.
  - PR: #7  Merged: 2026-07-31 (adw 325296bb; first attempt cbd77524 failed, PR #6 closed)

## M3: Ancillary-service co-optimization

Master spec: `specs/M3_ancillary_services.md` (authored 2026-08-01; scope
decision: AS co-opt chosen over DART two-settlement and over pulling Rust
forward). Headline: AS uplift, co-optimized revenue / energy-only revenue,
plus revenue mix by product. Capacity-awards-only model, perfect foresight;
assumptions documented in the master.

- [ ] **T6: AS data layer** `specs/M3a_as_data_layer.md`
  - Depends on: M2 merged only. Independent of T7.
  - Run: `uv run adws/travis/travis_sdlc.py specs/M3a_as_data_layer.md --worktree --draft-pr --dream --tui`
  - Note: the AS fixtures (July 2023 MCPCs plus the two DST raw samples)
    are generated once via a real gridstatus fetch, same procedure as T1.
    Verify `Ercot.get_as_prices` vs `get_mcpc_dam` for 2023-2024 history
    during research (the get_spp lesson applies).
  - PR: #8  Merged: 2026-08-01 (adw 6f498150)

- [ ] **T7: Co-optimization LP** `specs/M3b_as_cooptimizer.md`
  - Depends on: nothing technically (pure arrays), sequenced after T6 so
    PRs land one at a time. Uses T6's committed fixtures in property tests.
  - Run: `uv run adws/travis/travis_sdlc.py specs/M3b_as_cooptimizer.md --worktree --draft-pr --dream --tui`
  - Headline goldens: masked equivalence, pure REG_UP 240.0, additive
    250.0, REG_DOWN room 150.0 (all hand-derived in the slice spec).
  - PR: #9  Merged: 2026-08-01 (adw 3034ec63)

- [ ] **T8: AS backtest, CLI, README** `specs/M3c_as_backtest_cli.md`
  - Depends on: T6 AND T7 merged to main (integrates both).
  - Run: `uv run adws/travis/travis_sdlc.py specs/M3c_as_backtest_cli.md --worktree --draft-pr --dream --tui`
  - Note: finishes the M3 definition of done, including the README uplift
    headline and the honest assumptions note.
  - PR: #10  Merged: 2026-08-01 (adw d39c4d18)

## M4+ (specs not yet written)

Placeholders from the master plan; each needs a spec authored (or a planning
run) before it can enter the queue above.
- [ ] **M4: Rust engine.** Port `optimize_dispatch` to Rust via PyO3/maturin
  behind the frozen interface; benchmark vs Python. Prerequisite chore: re-run
  the ADW command tailoring and extend `adw_gates.json` for cargo
  build/test/clippy/fmt.
- [ ] **M5: Snowflake + AWS ingestion.** Warehouse schema for the canonical
  price table, Lambda + EventBridge daily pulls to S3, SQL analytics.
- [ ] **M6: Dashboard.** TypeScript/React visualization over the backtest
  outputs.

## Log

| Date | Task | adw-id | Result |
| ---- | ---- | ------ | ------ |
| 2026-07-29 | T1 M1a | 3c648beb | PR #1 merged |
| 2026-07-29 | T2 M1b | 3b9cf1a9 | PR #2 merged |
| 2026-07-29 | T3 M1c | 5dbaba17 | FAILED: silent no-op build; harness fixed (no-op guard, a1d9ac5); PR #3 closed |
| 2026-07-29 | T3 M1c | 27b2b22d | PR #4 merged; M1 complete |
| 2026-07-30 | T4 M2a | cea65174 | PR #5 merged |
| 2026-07-31 | T5 M2b | cbd77524 | FAILED: PR #6 closed, superseded by 325296bb |
| 2026-07-31 | T5 M2b | 325296bb | PR #7 merged; M2 complete |
| 2026-08-01 | T6 M3a | 6f498150 | PR #8 merged |
| 2026-08-01 | T7 M3b | 3034ec63 | PR #9 merged |
| 2026-08-01 | T8 M3c | d39c4d18 | PR #10 merged; M3 complete |

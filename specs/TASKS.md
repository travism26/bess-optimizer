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

- [ ] **T4: Rolling-horizon dispatch** `specs/M2a_rolling_horizon.md`
  - Depends on: M1 merged only. Independent of T5.
  - Run: `uv run adws/travis/travis_sdlc.py specs/M2a_rolling_horizon.md --worktree --draft-pr --dream --tui`
  - Headline goldens: two-day foresight case (perfect 275.0 vs persistence
    0.0, exact) and the M1 equivalence test.
  - PR: ______  Merged: ______

- [ ] **T5: Benchmarks + sweeps** `specs/M2b_benchmarks.md`
  - Depends on: T4 merged (capture rate consumes rolling results).
  - Run: `uv run adws/travis/travis_sdlc.py specs/M2b_benchmarks.md --worktree --draft-pr --dream --tui`
  - Delivers the M2 headline: foresight capture rate, plus TB2/TB4, sweeps,
    README section.
  - PR: ______  Merged: ______

## M3+ (specs not yet written)

Placeholders from the master plan; each needs a spec authored (or a planning
run) before it can enter the queue above.

- [ ] **M3: TBD** (reserved in the 6-milestone plan).
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

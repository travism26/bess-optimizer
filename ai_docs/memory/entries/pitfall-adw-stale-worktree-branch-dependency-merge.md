---
name: adw-stale-worktree-branch-dependency-merge
description: When a spec's slice depends on another slice merged to main, check the worktree branch isn't stale before building
type: pitfall
source_adw_ids: [3034ec63, d39c4d18]
date: 2026-08-01
---

ADW worktree branches are cut from main at pipeline start. When a spec's 'Depends on' section names a prerequisite slice as already merged (e.g. M3b's spec said 'M2 merged... sequenced after [M3a] so PRs land one at a time'), the worktree branch can still be stale: cut before that prerequisite's PR actually merged to origin/main. M3b's research phase found `tests/fixtures/as_mcpc_2023_07.parquet` and `src/bess/data/as_prices.py` (from M3a) simply absent from the branch even though the spec's property tests assumed they existed, because origin/main had advanced past the branch point after the worktree was created. Fix: merge origin/main into the worktree branch before implementing, not after discovering missing files mid-build. Expect a conflict on `.ports.env` during that merge (see [[adw-worktree-port-file-cleanup]]); resolve it by taking origin/main's value. Check this whenever a spec names another slice as a merged prerequisite, especially if slices are developed on parallel branches rather than strictly serially.

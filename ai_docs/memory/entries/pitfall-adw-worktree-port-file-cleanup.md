---
name: adw-worktree-port-file-cleanup
description: ADW port-allocation file (.ports.env) recurringly gets committed mid-pipeline; check git status and untrack before finalizing
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d]
date: 2026-07-29
---

`.ports.env`, the harness's port-allocation file, has now shown up modified/committed unrelated to the feature diff in at least two separate ADW runs (M1a and M1b), each time flagged in review as a skippable issue rather than fixed. No pipeline phase reliably cleans this up on its own, so it recurs across runs even after being documented. Before treating a branch as done or opening a PR, run `git status`/`git show --stat` on recent commits and explicitly restore or untrack `.ports.env` (or any other stray ADW-harness state file) if it appears in the diff; do not assume a later phase will handle it.

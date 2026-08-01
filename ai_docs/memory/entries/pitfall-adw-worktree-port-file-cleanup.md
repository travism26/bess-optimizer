---
name: adw-worktree-port-file-cleanup
description: ADW port-allocation file (.ports.env) recurringly gets committed mid-pipeline; check git status and untrack before finalizing
type: pitfall
source_adw_ids: [3c648beb, 3b9cf1a9, 27b2b22d, cea65174, 325296bb, 6f498150, 3034ec63, d39c4d18]
date: 2026-08-01
---

`.ports.env`, the harness's port-allocation file, has now shown up modified/committed unrelated to the feature diff in at least five separate ADW runs (M1a, M1b, M2a/cea65174, M3a/6f498150, and M3b/3034ec63 as a merge conflict), each time flagged in review as a skippable issue or resolved ad hoc rather than fixed at the source. No pipeline phase reliably cleans this up on its own. Before treating a branch as done or opening a PR, run `git status`/`git show --stat` on recent commits and explicitly restore or untrack `.ports.env` (or any other stray ADW-harness state file) if it appears in the diff. If it surfaces as a merge conflict (e.g. when merging origin/main into a stale worktree branch, see [[adw-stale-worktree-branch-dependency-merge]]), resolve by taking origin/main's value; do not assume documenting it once will make a later phase handle it.

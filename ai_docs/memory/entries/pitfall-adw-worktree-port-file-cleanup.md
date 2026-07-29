---
name: adw-worktree-port-file-cleanup
description: ADW port-allocation file can get committed mid-pipeline; check git status and untrack before finalizing
type: pitfall
source_adw_ids: [3c648beb]
date: 2026-07-29
---

During at least one ADW run, the harness's worktree port-allocation file got committed to the feature branch during the research phase, unrelated to the task's actual scope. Other worktrees show a later pipeline step (document/ship) untracking this file before finalizing, but it doesn't always happen. Before treating a branch as done or opening a PR, run `git status`/`git show --stat` on recent commits and untrack any stray port-allocation or other ADW-harness state file that isn't part of the feature's actual diff.

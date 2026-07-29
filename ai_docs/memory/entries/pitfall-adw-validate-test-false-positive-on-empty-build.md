---
name: adw-validate-test-false-positive-on-empty-build
description: Validate/test phase success does not mean Build produced an implementation; check the diff or Review, not those flags
type: pitfall
source_adw_ids: [5dbaba17]
date: 2026-07-29
---

In run 5dbaba17, the Build phase produced no implementation at all (branch diff against origin/main contained only a research doc and the usual stray .ports.env change), yet Validate still reported success (0 critical, only pre-existing markdown ruff-format nits unrelated to the task) and Test reported passing. Both gates check generic repo health (lint, types, whatever tests already exist), not whether the spec's acceptance criteria have new code behind them, so they pass trivially when Build no-ops or fails silently. Only the Review phase, which diffs against origin/main and checks the spec's acceptance criteria one by one, caught the missing implementation. When auditing or resuming a run, do not treat validate/test success as evidence that Build did anything; check `git diff origin/main --stat` or the Review phase's issue list first.

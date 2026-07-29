# Capture Eval Task

Turn a real agent failure into a permanent benchmark task. When the harness
produces a buggy/incomplete result on a **vendored eval target**
(`evals/target_app` or `evals/target_backend`) that a human had to fix, distill
that miss - and the human's fix - into a new `evals/tasks/NN-<slug>.yaml`.

This is the **eval-task** capture loop: it grows the benchmark so A/B comparisons
have teeth (de-saturation). It is distinct from `/capture_fixture`, which guards
the *harness itself* (parser/phase breaks → `tests/regression/`).

## Variables

- `adw_id`: $1 - the run that produced the buggy result (gives the prompt + plan_type)
- `description`: $ARGUMENTS - free-text: which target, what the agent got wrong, and where the human's fix lives (a commit, a diff, or the kept `--keep-tmp` target dir)

## Principles (do not skip)

- **Vendored, frozen targets only.** Never point a task at a live repo - scores must stay comparable across time. The realism comes from the target being a real codebase snapshot (`target_backend` is the grow app's backend).
- **The oracle is the human's fix, harvested - not invented.** Translate the fix (and any regression test) into a small set of **behavioral** `acceptance` shell checks that fail before the fix and pass after.
- **Behavioral, not interface-name, checks.** Assert observable behavior ("after delete-then-add, no id collision"), not `grep for functionName` - the #1 deterministic false-negative is a correct solution that uses different names than the test expected.
- **A task only helps if it's hard.** Run the saturation check at the end and *discard* the task if the current harness already aces it (pass^k full).

## Instructions

1. **Locate the run.** Confirm `agents/{adw_id}/` exists; read the spec/prompt the run was given and its `plan_type` (feature|bug|chore). Identify which vendored target it ran against (`app` or `backend`).

2. **Read the human's fix.** From the commit/diff/kept-target the operator pointed to, understand the root cause and what "correct" looks like. If the operator added a regression test, that test's *behavior* is the oracle.

3. **Decide on `setup:` (bug-planting).** Inspect the vendored baseline target:
   - If the bug is **already present** in the baseline (the agent just failed to fix it), no setup is needed.
   - If the bug is **not** in the baseline (it was agent-introduced, or the feature simply doesn't exist yet), write `--setup` shell commands that plant the gap/bug into the baseline so the agent has something to fix. Prefer a committed patch file under `evals/tasks/setup/` applied via `git apply`.

4. **Distill the oracle.** Write 1–3 `--acceptance` shell one-liners that:
   - Run from the target root and exit 0 only when the behavior is correct.
   - Fail on the *unfixed* baseline (sanity-check this) and pass on a correct fix.
   - For backend (TS) targets, prefer narrowing the test run (`npm test -- <pattern>`); for app, a `python -m ...` behavioral pipeline like the existing tasks.

5. **Write the task:**
   ```bash
   uv run evals/capture_eval_task.py \
       --slug <kebab-slug> \
       --plan-type <feature|bug|chore> \
       --target <app|backend> \
       --prompt @<path-to-prompt-file>   # or inline "..." \
       --acceptance "<behavioral check 1>" \
       --acceptance "<behavioral check 2>" \
       --setup "<plant-bug command>"     # omit if bug is already in baseline \
       --judge-focus "<one line: what correct looks like>"
   ```
   Use `--dry-run` first to eyeball the YAML.

6. **Saturation check (the keep/discard gate).** Run the new task 3× and read reliability:
   ```bash
   uv run evals/run_eval.py run --variant capture-check --tasks <NN> --trials 3
   uv run evals/compare.py --variants capture-check
   ```
   - **Keep** the task if `pass^k` is **not** full (some trials fail) - it discriminates.
   - **Discard** it (delete the yaml) if it scores 3/3 perfectly - it's already saturated and adds nothing. Say so explicitly.
   - Backend tasks need postgres+redis (local or docker) and an `npm ci`'d `target_backend/` - see `evals/run_eval.py` TARGETS.

7. **Hand back** the task path, the saturation verdict (pass@k / pass^k), and whether you kept or discarded it.

## Output

```
Captured eval task: <NN-slug>  (target=<app|backend>, plan_type=<...>)
  File:       evals/tasks/<NN-slug>.yaml
  Oracle:     <N> acceptance checks (+ setup patch | bug already in baseline)
  Saturation: pass@k=<x/1> pass^k=<x/1> over 3 trials
  Verdict:    KEEP (discriminates) | DISCARD (harness already aces it)
```

## Notes

- Idempotent-ish: the helper refuses to overwrite an existing `NN-slug.yaml`; bump the slug or let it auto-number.
- Sensitive data: the run dir and any kept target may contain secrets - never copy tokens/cookies/live data into the prompt or acceptance checks; rewrite hosts to `example.com`.
- Keep the baseline target **unsolved**: do not commit the human's solution into `target_*`. The task carries the oracle; the harness re-derives the fix each run.

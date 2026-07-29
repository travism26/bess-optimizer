# Bug Planning

Create a plan to resolve the `Bug` using the exact specified markdown `Plan Format`. Remember: you are writing the plan, not fixing the bug.

## Variables

adw_id: $1
prompt: $2

## Instructions

- Write a plan to resolve the bug that is thorough and precise, so the fix addresses the root cause and prevents regressions.
- Be surgical: plan the minimal number of changes that fix the bug at hand - don't fall off track.
- Create the plan in the `specs/` directory with filename: `bug-{adw_id}-{descriptive-name}.md` (short descriptive name, e.g. "fix-config-parse", "patch-memory-leak")
- Research the codebase (start with `README.md`, `CLAUDE.md`, and `specs/M1_python_core.md`), understand the bug, reproduce it, and put together the plan.
- Replace every <placeholder> in the `Plan Format` with the requested value. Keep each section tight - every sentence should help the developer fixing the bug.
- Use your reasoning model: THINK HARD about the bug, its root cause, and the steps to fix it properly.
- Don't use decorators. Keep it simple.
- If you need a new Python dependency, add it to `pyproject.toml` and report it in the `Notes` section of the plan.

## Relevant Files

- `README.md` - Project overview and instructions (start here)
- `CLAUDE.md` - Agent guidance: commands, frozen interfaces, gotchas
- `specs/M1_python_core.md` - Authoritative master spec
- `src/bess/models.py` - frozen interface dataclasses (do not change without a spec change)
- `src/bess/data/` - price ingestion, canonical schema, parquet cache (only home for gridstatus)
- `src/bess/optimizer/` - pure LP dispatch core (numpy + highspy only; no pandas, no I/O)
- `src/bess/backtest/` - backtest runner and metrics
- `src/bess/viz/` - matplotlib plots
- `tests/` - pytest suite driven entirely by frozen fixtures
- `specs/` - Specification and plan documents

- Read `.claude/commands/conditional_docs.md` to check if your task requires additional documentation
- If your task matches any of the conditions listed, include those documentation files in the `Plan Format: Relevant Files` section of your plan

Ignore all other files in the codebase.

## Plan Format

```md
# Bug: <bug name>

## Metadata

adw_id: `{adw_id}`
prompt: `{prompt}`

## Bug Description

<the bug's symptoms, expected vs actual behavior, and the proposed fix approach - one tight section>

## Steps to Reproduce

<list exact steps to reproduce the bug>

## Root Cause Analysis

<analyze and explain the root cause of the bug>

## Relevant Files

Use these files to fix the bug:

<find and list the files relevant to the bug with bullets explaining why. New files go under an h3 'New Files' section.>

## Step by Step Tasks

IMPORTANT: Execute every step in order, top to bottom.

<list step by step tasks as h3 headers plus bullet points. Start with foundational shared changes, then the specific fix. Include tests that validate the bug is fixed with zero regressions. Last step: run the `Validation Commands`.>

## Validation Commands

Execute every command to validate the bug is fixed with zero regressions.

<list commands that validate with 100% confidence the bug is fixed, including commands that reproduce the bug before and after the fix. Every command must execute without errors.>

- `uv run mypy` - Ensure the code compiles / type-checks
- `uv run pytest` - Run all tests to validate zero regressions
- `uv run mypy` - Run static analysis
- `<specific application command to verify the bug is fixed>`

## Notes

<optionally list any additional notes or context that are relevant to the bug that will be helpful to the developer>
```

## Bug

Extract the bug details from the `prompt` variable (the bug report text; it may start with an "Issue #N:" prefix when the bug originated from a tracked issue).

## Report

Return ONLY the relative path to the plan file created (e.g., `specs/bug-9dfe4a36-description.md`).

IMPORTANT: Do NOT include any summary, explanation, or additional text. Return only the file path.

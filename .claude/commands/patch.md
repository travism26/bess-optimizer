# Patch Plan

Create a **focused patch plan** to resolve a specific issue based on the `review_change_request`. Follow the `Instructions` to create a concise plan that addresses the issue with minimal, targeted changes.

## Variables

adw_id: $1
review_change_request: $2
spec_path: $3 if provided, otherwise leave it blank
agent_name: $4 if provided, otherwise use 'patch_agent'
issue_screenshots: $5 (optional) - comma-separated list of screenshot paths if provided

## Instructions

- IMPORTANT: You're creating a patch plan to fix a specific review issue. Keep changes small, focused, and targeted
- Read the original specification (spec) file at `spec_path` if provided to understand the context and requirements
- IMPORTANT Use the `review_change_request` to understand exactly what needs and use it as the basis for your patch plan
- If `issue_screenshots` are provided, examine them to better understand the visual context of the issue
- Create the patch plan in `specs/patch/` directory with filename: `patch-adw-{adw_id}-{descriptive-name}.md`
  - Replace `{descriptive-name}` with a short name based on the issue (e.g., "fix-validation", "update-handler", "correct-output")
- IMPORTANT: This is a PATCH - keep the scope minimal. Only fix what's described in the `review_change_request` and nothing more. Address only the `review_change_request`.
- Run `git diff --stat`. If changes are available, use them to understand what's been done in the codebase and so you can understand the exact changes you should detail in the patch plan.
- Ultra think about the most efficient way to implement the solution with minimal code changes
- Base your `Plan Format: Validation` on the validation steps from `spec_path` if provided
  - If any tests fail in the validation steps, you must fix them.
  - If not provided, READ `.claude/commands/test.md: ## Test Execution Sequence` and execute the tests to understand the tests that need to be run to validate the patch.
- Replace every <placeholder> in the `Plan Format` with specific implementation details
- IMPORTANT: When you finish writing the patch plan, return exclusively the path to the patch plan file created and nothing else.

## Relevant Files

Focus on the following files:

- `README.md` - Project overview and instructions (start here)
- `CLAUDE.md` - Agent guidance: commands, frozen interfaces, gotchas
- `specs/M1_python_core.md` - Authoritative master spec
- `adws/` - AI Developer Workflow scripts and modules
- `src/bess/models.py` - frozen interface dataclasses (do not change without a spec change)
- `src/bess/data/` - price ingestion, canonical schema, parquet cache (only home for gridstatus)
- `src/bess/optimizer/` - pure LP dispatch core (numpy + highspy only; no pandas, no I/O)
- `src/bess/backtest/` - backtest runner and metrics
- `src/bess/viz/` - matplotlib plots
- `tests/` - pytest suite driven entirely by frozen fixtures
- `.claude/commands/` - Claude command templates
- `specs/` - Specification and plan documents

- Read `.claude/commands/conditional_docs.md` to check if your task requires additional documentation
- If your task matches any of the conditions listed, include those documentation files in the `Plan Format: Relevant Files` section of your plan

Ignore all other files in the codebase.

## Plan Format

```md
# Patch: <concise patch title>

## Metadata

adw_id: `{adw_id}`
review_change_request: `{review_change_request}`

## Issue Summary

**Original Spec:** <spec_path>
**Issue:** <brief description of the review issue based on the `review_change_request`>
**Solution:** <brief description of the solution approach based on the `review_change_request`>

## Files to Modify

Use these files to implement the patch:

<list only the files that need changes - be specific and minimal>

## Implementation Steps

IMPORTANT: Execute every step in order, top to bottom.

<list 2-5 focused steps to implement the patch. Each step should be a concrete action.>

### Step 1: <specific action>

- <implementation detail>
- <implementation detail>

### Step 2: <specific action>

- <implementation detail>
- <implementation detail>

<continue as needed, but keep it minimal>

## Validation

Execute every command to validate the patch is complete with zero regressions.

<list 1-5 specific commands or checks to verify the patch works correctly>

## Patch Scope

**Lines of code to change:** <estimate>
**Risk level:** <low|medium|high>
**Testing required:** <brief description>
```

## Report

- IMPORTANT: Return exclusively the path to the patch plan file created and nothing else.

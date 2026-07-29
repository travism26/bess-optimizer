# Troubleshoot

Systematically troubleshoot an issue using structured debugging, log analysis, and root cause investigation. Delegates to specialized commands for fixes.

## Variables

issue_description: $1

## Instructions

1. **Understand the Issue**
   - Clarify the problem symptoms, affected components, and user impact
   - Identify when the issue started occurring
   - Determine if this is a regression or new issue

2. **Check Application Health**
   - Run `/validate` to confirm the project builds, type-checks, and lints cleanly
   - Run `/test` to confirm the unit test suite is green
   - Review recent changes: `git log --oneline -10`
   - Check git status for uncommitted changes: `git status`
   - **SRP note:** Troubleshoot is an orchestrator. Always delegate build/lint/test to `/validate` and `/test` rather than running their commands directly.

3. **Search Relevant Logs**
   - IMPORTANT: Use the `/search_logs` command to analyze logs systematically
   - Read `.claude/commands/search_logs.md` for guidance on log searching
   - Document correlation IDs, error patterns, and timestamps

4. **Analyze the Codebase**
   - Read `.claude/commands/conditional_docs.md` to identify relevant documentation
   - Based on the issue type, read the documentation that matches your conditions
   - Locate affected components using Grep/Glob tools
   - Review recent changes to those files: `git log --oneline <file-path> -5`

5. **Reproduce the Issue**
   - Identify the exact steps to reproduce the problem
   - Try to reproduce locally following those steps
   - Document what happens vs. what should happen
   - Capture any error messages, stack traces, or correlation IDs

6. **Root Cause Analysis**
   - Analyze the evidence from logs, code review, and reproduction
   - Identify the root cause (not just symptoms)

7. **Route the Fix**

   Classify the root cause, then route by this table. Trivial fixes (typo,
   config change, one-liner) are fixed directly regardless of class; anything
   needing planning or multiple changes is delegated.

   | Root cause class | Examples | Route |
   |---|---|---|
   | Bug | broken logic, error in code | `/bug <issue>` → `/implement <plan-file>` |
   | Chore / debt | refactoring, config drift, data state | `/chore <adw-id> <desc>` → `/implement <plan-file>` |
   | Feature gap | missing functionality | `/feature <adw-id> <desc>` → `/implement <plan-file>` |
   | Trivial (any class) | typo, one-liner, env var | fix directly, document what/why |
   | Infrastructure | external service, dependency outage | report findings; no code change |

   Delegated commands write their plan to `specs/`; review it before running
   `/implement`.

8. **Validate the Fix**
   - Delegate to the pipeline phases - run `/validate` then `/test`
   - Confirm the issue no longer reproduces (the original repro steps from step 5)
   - If `/test` reports failures, use `/resolve_failed_test` for each failure
   - If `/validate` reports violations, use `/resolve_validation_violation` for each one

## Codebase Structure

- `src/bess/` - the package: models, data, optimizer, backtest, viz, cli
- `tests/` - pytest suite; `tests/fixtures/` holds frozen parquet slices (no network in tests, ever)
- `specs/` - the authoritative M1 master spec (frozen; ruff excluded)
- `ai_docs/` - project context and per-feature ADW specs (frozen; ruff excluded)
- `data/` - local parquet price cache, gitignored
- `rust/` - empty until the M4 Rust engine

<!--
Replace with the project's actual directory layout, e.g.:
- `src/` - main source code
- `tests/` - test files
- `configs/` - configuration files
-->

### Documentation
- `README.md` - Project overview and setup
- `CLAUDE.md` - Agent guidance and architecture rules
- `specs/M1_python_core.md` - Authoritative master spec
- `specs/` - Active implementation plans
- `.claude/commands/conditional_docs.md` - Documentation reference guide

## Report

Provide a structured troubleshooting report with the following sections:

### Issue Summary
- Brief description of the problem
- Affected components/features
- User impact

### Investigation Findings
- Key evidence from logs (include correlation IDs if available)
- Relevant code locations
- Recent changes that may have contributed

### Root Cause
- Clear explanation of what's causing the issue
- Why it's happening

### Solution Applied (or Recommended)
- Specific changes made to fix the issue
- OR if not fixed: recommended next steps

### Validation Results
- Tests run and their results
- Confirmation that issue is resolved
- OR if not resolved: what still needs investigation

### Preventive Measures
- How to prevent this issue in the future
- Any monitoring or alerts to add

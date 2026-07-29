# Resolve Failed Test

Fix a specific failing Python test using the provided failure details.

## Instructions

1. **Analyze the Test Failure**
   - Review the test name, purpose, and error message from the `Test Failure Input`
   - Understand what the test is trying to validate
   - Identify the root cause from the error details

2. **Context Discovery**
   - Check recent changes: `git diff origin/main --stat --name-only`
   - If a relevant spec exists in `specs/*.md`, read it to understand requirements
   - Focus only on files that could impact this specific test

3. **Reproduce the Failure**
   - IMPORTANT: Use the `execution_command` provided in the test data
   - Run it to see the full error output and stack trace
   - Common Python test commands:
     - `uv run pytest tests/test_optimizer_golden.py::test_name -v` - Run specific test
     - `uv run pytest -v` - Run all tests verbose
   - Confirm you can reproduce the exact failure

4. **Fix the Issue**
   - Make minimal, targeted changes to resolve only this test failure
   - Ensure the fix aligns with the test purpose and any spec requirements
   - Do not modify unrelated code or tests
   - Follow Python best practices and conventions

5. **Verify the Fix**
   - Re-run the same `execution_command` to confirm the test now passes
   - Do NOT run the full test suite, `/validate`, or `uv run mypy` here - those are separate pipeline phases
   - Focus only on fixing this specific test

## Test Failure Input

$ARGUMENTS

## Report

Provide a concise summary of:
- Root cause identified
- Specific fix applied
- Confirmation that the test now passes

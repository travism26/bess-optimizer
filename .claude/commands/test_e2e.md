# E2E Test Runner

Execute end-to-end (E2E) tests for the Python application. E2E tests validate complete workflows by running the actual application and verifying outputs, exit codes, and generated artifacts.

## Variables

adw_id: $ARGUMENT if provided, otherwise generate a random 8 character hex string
agent_name: $ARGUMENT if provided, otherwise use 'test_e2e'
e2e_test_file: $ARGUMENT (can be specific file or empty for intelligent selection)
RUN_ALL_E2E: false (set to true via $ARGUMENTS --run-all-e2e to run all E2E tests)
DIFF_BASE: HEAD (can be overridden by $ARGUMENTS --diff-base flag)

## Prerequisites

IMPORTANT: E2E tests require the application to be built/prepared and external dependencies to be available.

Before running E2E tests:

1. **Build / Prepare the Application**:

   ```bash
   uv run mypy
   ```

2. **Verify the Build**:

   ```bash
   uv run bess --help
   ```

3. **Check External Tools** (if required by the test):

   ```bash
   # Check for any external dependencies required by your application
   which <dependency> 2>/dev/null || echo "Some external tools not installed"
   ```

4. **Ensure Test Directory Exists**:
   ```bash
   mkdir -p /tmp/e2e_test_workspace
   ```

If the application fails to build, E2E tests WILL FAIL.

## Instructions

### Intelligent E2E Test Selection

If `e2e_test_file` is NOT provided, use intelligent selection:

1. Parse command-line arguments from $ARGUMENTS:
   - If `--run-all-e2e` is present, set RUN_ALL_E2E to true
   - If `--diff-base <ref>` is present, set DIFF_BASE to the specified reference
2. Run the test selector: `python3 adws/adw_modules/test_selector.py ${DIFF_BASE} ${RUN_ALL_E2E ? '--run-all-tests' : ''}`
3. Extract the `e2e_files` list from the test selector output
4. If the list contains the e2e directory root, run ALL E2E tests
5. If the list contains specific files, run only those tests
6. If the list is empty, skip E2E tests (no relevant changes detected)

If `e2e_test_file` IS provided, run that specific test (legacy behavior for manual test execution).

**IMPORTANT**: The test selector maps source code changes to their corresponding E2E tests.

### Test Execution

IMPORTANT: Before executing any test steps:

- Verify the application is built (see Prerequisites above)
- If build fails, the tests MUST NOT proceed - display clear error message

Test Execution:

- If using intelligent selection, run the selected E2E test files
- If `e2e_test_file` is provided, read that specific test file
- Digest the `User Story` to first understand what we're validating
- IMPORTANT: Execute the `Test Steps` detailed in the test file(s)
- Review the `Success Criteria` and if any of them fail, mark the test as failed and explain exactly what went wrong
- Review the steps that say '**Verify**...' and if they fail, mark the test as failed and explain exactly what went wrong
- Capture command outputs and artifacts as specified
- IMPORTANT: Return results in the format requested by the `Output Format`
- Allow time for async operations (network requests, file I/O)
- IMPORTANT: After capturing outputs, save them to `Output Directory` with descriptive names
- Capture and report any errors encountered
- If you encounter an error, mark the test as failed immediately and explain exactly what went wrong and on what step it occurred.
- Use `pwd` or equivalent to get the absolute path to the codebase for writing and displaying the correct paths

## Setup

Read and Execute `.claude/commands/prepare_app.md` now to prepare the application for the test. This will ensure:

- Application is built and runnable
- Dependencies are available
- Configuration is valid

## Output Directory

<absolute path to codebase>/agents/<adw_id>/<agent_name>/output/<directory name based on test file name>/

Each output file should be saved with a descriptive name that reflects what is being captured. The directory structure ensures that:

- Outputs are organized by ADW ID (workflow run)
- They are stored under the specified agent name (e.g., e2e_test_runner_0)
- Each test has its own subdirectory based on the test file name

## Report

- Exclusively return the JSON output as specified in the test file
- Capture any unexpected errors
- IMPORTANT: Ensure all output artifacts are saved in the `Output Directory`

### Output Format

```json
{
  "test_name": "Test Name Here",
  "status": "passed|failed",
  "outputs": [
    "<absolute path to codebase>/agents/<adw_id>/<agent_name>/output/<test name>/01_<descriptive name>.txt",
    "<absolute path to codebase>/agents/<adw_id>/<agent_name>/output/<test name>/02_<descriptive name>.json"
  ],
  "error": null
}
```

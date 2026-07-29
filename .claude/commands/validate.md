# Python Code Validation

Run comprehensive Python code validation including compilation/type-checking, linting, static analysis, and formatting checks. Returns violations in a standardized JSON format.

## Purpose

Enforce code quality, security, and Python best practices by:

- Verifying code compiles / type-checks successfully (`uv run mypy`)
- Running static analysis (`uv run mypy`)
- Checking code formatting (`uv run ruff format --check .`)
- Running linter (`uv run ruff check .`)
- Identifying potential bugs, security issues, and code quality problems
- Returning actionable violation reports with file:line references

**Note:** This command runs all static analysis and linting checks. For running unit tests, use the `/test` command instead.

## Variables

VALIDATION_TIMEOUT: 5 minutes

## Code Quality & Linting Standards

The project enforces comprehensive code quality standards using `Ruff`.

### Enabled Linters / Checks

- Ruff lint, rule sets E, W, F (pycodestyle/pyflakes), I (import sorting), B (bugbear), UP (pyupgrade), SIM (simplify), RUF; line length 100
- Ruff format (Black-compatible); `specs/` and `ai_docs/` are excluded, they are frozen inputs and must never be rewritten
- mypy in strict-ish mode: disallow_untyped_defs, no_implicit_optional, warn_return_any, strict_equality; gridstatus and highspy have no stubs (ignore_missing_imports)

<!--
Replace with the linters and checks specific to this project.
Categorize where helpful (security, error handling, complexity,
bug detection, style, best practices).
-->

## Instructions

Execute Python validation and return results as a JSON array of violations.

### Execution Steps

1. **Verify compilation / type-check**
   ```bash
   uv run mypy
   ```
   This ensures all Python code compiles or type-checks successfully before running further checks.

2. **Run static analysis**
   ```bash
   uv run mypy
   ```

3. **Check formatting**
   ```bash
   uv run ruff format --check .
   ```

4. **Run linter**
   ```bash
   uv run ruff check .
   ```

5. **Parse the output**
   - Parse each tool's output
   - Categorize by severity (error vs warning)
   - Compilation / type errors are always errors
   - Static analysis issues are typically errors (potential bugs)
   - Formatting issues are typically warnings (style)
   - Linter categorizes based on the specific rule
   - Exit code 0 = no critical violations

6. **Return results**
   - IMPORTANT: Return ONLY the JSON array with violations
   - Do not include any additional text, explanations, or markdown formatting
   - We'll immediately run JSON.parse() on the output
   - If validation fails to run, return error as JSON

## Common Validation Issues & Fixes

### Unsorted imports (I001)

```python
# Bad
import pandas as pd
import numpy as np

# Good (stdlib, third-party, first-party; alphabetical within groups)
import numpy as np
import pandas as pd

from bess.models import BatterySpec
```

### Missing type annotations (mypy disallow_untyped_defs)

```python
# Bad
def annualize(revenue, hours):
    return revenue * 8760.0 / hours

# Good
def annualize(revenue: float, hours: float) -> float:
    return revenue * 8760.0 / hours
```

### Deprecated typing syntax (UP006/UP045)

```python
# Bad
from typing import Optional, List
def f(x: Optional[List[float]]) -> None: ...

# Good (Python 3.12)
def f(x: list[float] | None) -> None: ...
```

### Collapsible conditional (SIM108)

```python
# Bad
if status == "optimal":
    ok = True
else:
    ok = False

# Good
ok = status == "optimal"
```

<!--
Replace with language-specific examples of common violations and how to fix them.
-->

## Error Handling

If the validation fails to execute:
- Capture the error message
- Return as a single-item JSON array with a validation-error violation
- Example:
  ```json
  [
    {
      "rule": "validation-error",
      "file": "unknown",
      "line": null,
      "column": null,
      "severity": "error",
      "message": "Failed to run validation: <error message>",
      "fix_suggestion": null
    }
  ]
  ```

## Report

Return results exclusively as a JSON array matching the ValidationViolation schema:

### Output Structure

```json
[
  {
    "rule": "string",
    "file": "string",
    "line": number | null,
    "column": number | null,
    "severity": "error" | "warning",
    "message": "string",
    "fix_suggestion": "string" | null
  },
  ...
]
```

### Example Output - No Violations

```json
[]
```

### Example Output - With Violations

```json
[
  {
    "rule": "ruff/F401",
    "file": "src/bess/data/prices.py",
    "line": 45,
    "column": 12,
    "severity": "error",
    "message": "<short description of the violation>",
    "fix_suggestion": "<short description of how to fix>"
  }
]
```

## Notes

- Only critical violations (severity: "error") should fail the validation phase
- Warnings (severity: "warning") are informational and don't fail validation

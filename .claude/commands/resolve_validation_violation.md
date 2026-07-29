# Resolve Validation Violation

Fix a specific code validation violation by applying the minimal, targeted changes required to resolve the issue.

## Purpose

Automatically resolve code quality violations detected by the `/validate` command by:

- Analyzing the specific violation (rule, file, location, message)
- Understanding the context and current code structure
- Applying rule-specific fixes that maintain code quality standards
- Verifying the fix resolves the violation

## Arguments

This command expects a JSON violation object as an argument with the following structure:

```json
{
  "rule": "string",
  "file": "string",
  "line": number | null,
  "column": number | null,
  "severity": "error" | "warning",
  "message": "string",
  "fix_suggestion": "string" | null
}
```

## Instructions

### 1. Analyze the Violation

Parse the provided violation JSON to understand:
- **Rule**: Which code quality rule was violated
- **File**: The file containing the violation
- **Line/Column**: Exact location of the violation
- **Message**: Specific violation details
- **Fix Suggestion**: Guidance on how to fix (if available)

### 2. Context Discovery

Read the affected file to understand:
- Current code structure around the violation
- What packages/imports are being used incorrectly
- What the code is trying to accomplish

### 3. Determine Fix Strategy

Based on the rule violated, apply the appropriate fix.

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
Replace the section above with language-specific guidance for the most common
violations you expect, including:
- Static analysis violations (e.g., printf format mismatches, shadowed variables)
- Formatting violations (e.g., import grouping, line length)
- Linter violations (e.g., unchecked errors, unused variables, code simplification)
For each, show a "Before" and "After" example.
-->

### 4. Apply the Fix

Make the minimal necessary changes:
- Edit only the affected file(s)
- Keep changes focused on resolving the specific violation
- Don't refactor unrelated code
- Maintain Python idioms and patterns

### 5. Verify the Violation Is Resolved

After applying changes:
1. **CRITICAL**: Verify using `uv run ruff check . <file>` to confirm the specific violation is resolved
2. Verify the specific violation no longer appears in the output
3. Check that no new validation violations were introduced

**SRP note:** This command's only job is to fix the one validation violation. Do **not** run the test suite here - that belongs to `/test`. Re-running `/validate` or `/test` is the next phase's responsibility.

**Verification command**:
```bash
uv run ruff check . <file> 2>&1 | grep -i "<rule-name>"
# If no output, the violation is fixed
```

## Report Format

After fixing the violation, provide a concise report:

```markdown
### Violation Resolved

**Rule**: <rule-name>
**File**: <file-path>:<line>

**Changes Made**:
- <Brief description of what was changed>
- <Brief description of what was changed>

**Verification**:
- Re-ran validation: [PASS/FAIL]
- Violation resolved: [YES/NO]
- Tests passing: [YES/NO]
```

## Notes

- Focus on fixing ONE violation at a time
- Don't make changes beyond what's needed to fix the violation
- Follow Python best practices and idioms
- **ALWAYS verify using `uv run ruff check . <file>`** - never rely on a different formatter/linter for verification, as they may have different rules
- If the fix introduces new violations, adjust the approach
- Do **not** run the test suite here - `/test` is a separate pipeline phase

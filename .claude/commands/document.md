# Document Feature

Generate concise markdown documentation for implemented features by analyzing code changes and specifications. This command creates documentation in the `app_docs/` directory based on git diff analysis against the main branch and the original feature specification.

## Variables

adw_id: $1
spec_path: $2 if provided, otherwise leave it blank

## Instructions

### 1. Analyze Changes

- Run `git diff origin/main --stat` to see files changed and lines modified
- Run `git diff origin/main --name-only` to get the list of changed files
- For significant changes (>50 lines), run `git diff origin/main <file>` on specific files to understand the implementation details

### 2. Read Specification (if provided)

- If `spec_path` is provided, read the specification file to understand:
  - Original requirements and goals
  - Expected functionality
  - Success criteria
- Use this to frame the documentation around what was requested vs what was built

### 3. Generate Documentation

- Create a new documentation file in `app_docs/` directory
- Filename format: `feature-{adw_id}-{descriptive-name}.md`
  - Replace `{descriptive-name}` with a short feature name (e.g., "user-auth", "report-export", "config-loader")
- Follow the Documentation Format below
- Focus on:
  - What was built (based on git diff)
  - How it works (technical implementation)
  - How to use it (CLI commands and options)
  - Any configuration required

### 4. Update Conditional Documentation

- After creating the documentation file, read `.claude/commands/conditional_docs.md`
- Add an entry for the new documentation file with appropriate conditions
- The entry should help future developers know when to read this documentation
- Format the entry following the existing pattern in the file

### 5. Final Output

- When you finish writing the documentation and updating conditional_docs.md, return a JSON response

## Output Format

Return ONLY a JSON object (no markdown, no explanation) with this structure:

```json
{
  "success": true,
  "documentation_created": true,
  "documentation_path": "app_docs/feature-{adw_id}-{name}.md",
  "error_message": null
}
```

If documentation was not created (e.g., no significant changes):

```json
{
  "success": true,
  "documentation_created": false,
  "documentation_path": null,
  "error_message": "No significant changes requiring documentation"
}
```

If an error occurred:

```json
{
  "success": false,
  "documentation_created": false,
  "documentation_path": null,
  "error_message": "Description of the error"
}
```

## Documentation Format

```md
# <Feature Title>

**ADW ID:** <adw_id>
**Date:** <current date>
**Specification:** <spec_path or "N/A">

## Overview

<2-3 sentence summary of what was built and why>

## What Was Built

<List the main components/features implemented based on the git diff analysis>

- <Component/feature 1>
- <Component/feature 2>
- <etc>

## Technical Implementation

### Files Modified

<List key files changed with brief description of changes>

- `<file_path>`: <what was changed/added>
- `<file_path>`: <what was changed/added>

### Key Changes

<Describe the most important technical changes in 3-5 bullet points>

## Usage

<Document how to use the feature - CLI commands, API endpoints, or library functions>

### Examples

```python
```bash
uv run bess fetch --config config.toml      # pull + cache ERCOT DA prices (network, manual only)
uv run bess backtest --config config.toml   # metrics JSON + plots from cache (no network)
uv run bess plot                            # re-render PNGs from a backtest output
```
```

## Configuration

<Any configuration options, environment variables, or config file settings>

## Testing

<Brief description of how to test the feature>

```bash
uv run pytest
```

## Notes

<Any additional context, limitations, or future considerations>
```

## Conditional Docs Entry Format

After creating the documentation, add this entry to `.claude/commands/conditional_docs.md`:

```md
- app_docs/<your_documentation_file>.md
  - Conditions:
    - When working with <feature area>
    - When implementing <related functionality>
    - When troubleshooting <specific issues>
```

## Report

- IMPORTANT: Return ONLY the JSON object as specified in "Output Format" section above. No markdown code blocks, no explanation, just the raw JSON.

# Capture Regression Fixture

Turn a real-world pipeline break into a permanent regression test. Given an `adw_id` and a description of what broke (and where), locate the breaking input under `agents/{adw_id}/`, copy it into `tests/fixtures/regression/`, and scaffold a pytest replay under `tests/regression/`.

## Variables

- `adw_id`: $1 - the run that broke (e.g. `dd1485c4`)
- `description`: $ARGUMENTS - free-text from the operator. Should mention the phase, agent, and/or file involved. Examples:
  - `BREAKING_INPUT failed on phase plan`
  - `agent_output.txt didn't get parsed correctly in agent planner_agent`
  - `test_agent crashed on iteration 3, see iter_3/agent_output.txt`

## Instructions

1. **Locate the agent run directory.** It's `agents/{adw_id}/`. If it doesn't exist, abort and tell the operator the adw_id is wrong or the run was cleaned up.

2. **Parse the description** to extract:
   - **phase** - one of the directories under `agents/{adw_id}/` (e.g. `plan`, `build`, `test`, `review`). Match by substring against the description.
   - **agent** - typically a subdir name like `planner_agent`, `builder_agent`, `test_agent`. Match by substring.
   - **breaking input file(s)** - explicit filenames in the description (`agent_output.txt`, `INPUT_ABC.json`, etc.) OR, if none mentioned, the most recently-modified `agent_input.*` / `agent_output.*` / `cc_raw_output.jsonl` under the matched phase/agent dir.
   - **slug** - kebab-case summary of the bug, max ~40 chars (e.g. `plan-empty-task-list`, `test-agent-jsonl-truncated`).

3. **Confirm the source files** exist on disk before invoking the capture script. List them to the operator.

4. **Run the capture helper**:
   ```bash
   uv run adws/adw_modules/fixture_capture.py <adw_id> <slug> \
       --description "<one-line summary>" \
       --phase <phase> \
       --agent <agent> \
       --source <abs-or-repo-rel-path-1> \
       --source <abs-or-repo-rel-path-2>
   ```
   The helper:
   - Copies sources into `tests/fixtures/regression/{adw_id}_{slug}/`
   - Writes a `MANIFEST.md` describing what broke
   - Generates a `tests/regression/test_{slug}.py` stub with a skip-marked `test_replay`

5. **Wire the real replay.** Read the parser or agent module that failed and edit `tests/regression/test_{slug}.py`:
   - Replace the `@pytest.mark.skip` decorator with the real import + assertion
   - The test should fail today (proving the regression is real) and pass once the bug is fixed
   - If the breaking input was an LLM call, prefer asserting on the parser side (deterministic) rather than re-invoking the LLM

6. **Verify.** Run `uv run pytest tests/regression/test_{slug}.py -v` and report the result.

7. **Hand back** to the operator:
   - Path to the fixture directory
   - Path to the test file
   - Whether the replay test currently fails (expected if the bug is unfixed) or passes (the bug is already fixed and this is now a guard)

## Output

Concise summary to the operator:

```
Captured regression: <slug>
  Fixture:  tests/fixtures/regression/<adw_id>_<slug>/ (N files)
  Test:     tests/regression/test_<slug>.py
  Replay:   <FAIL - bug confirmed | PASS - already fixed | SKIPPED - wire it up>

Next: <one-line action - usually "fix the bug then re-run the test", or "the test passes, commit the regression guard">
```

## Notes

- Idempotent: re-running with the same `(adw_id, slug)` overwrites the fixture but does NOT clobber a hand-edited `test_{slug}.py`. The test stub is only written if the file doesn't exist.
- Sensitive data: `agents/{adw_id}/` may contain auth tokens / cookies / live data. Inspect the captured files before committing - strip secrets and rewrite host names to `example.com` if needed.
- Slug collisions: if the slug already exists for a different adw_id, append a short suffix (`-v2`, `-iter3`).

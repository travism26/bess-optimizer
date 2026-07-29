# Fix Gate

A deterministic quality gate failed. Fix the underlying problem it surfaced - 
this is the `/fix_gate` phase of a slim pipeline (`pipe_chore.py`): the
pipeline itself re-runs the gate after you finish, so your only job is to
make the failure go away.

## Variables

failure: $ARGUMENTS - a JSON object `{"gate": ..., "output_tail": ...}`

## Instructions

- Parse `failure` as JSON. `gate` is the name of the gate that failed;
  `output_tail` is the tail of its command output (stdout+stderr) - read it
  carefully, it tells you exactly what broke.
- Fix the underlying problem with the smallest change that addresses it.
  Do not refactor, do not restyle unrelated code, and do not fix unrelated
  issues you happen to notice - only what `output_tail` reports.
- You may re-run the failing command yourself if it is fast (e.g. a linter
  or a single unit-test command) to confirm your fix before finishing.
- IMPORTANT: Never run Docker, testcontainers, or any integration/slow test
  suite - the pipeline re-runs those deterministically on its own schedule;
  running them here only wastes time.
- If `output_tail` doesn't point to a clear cause, make your best targeted
  attempt based on `gate` rather than making broad speculative changes.

## Report

Return one short paragraph of free text describing what was wrong and what
you changed to fix it. This is a status note, not an artifact.

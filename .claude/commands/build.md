# Build

Implement the requested change directly in the current repository. This is the
build phase of a slim pipeline (`pipe_chore.py`): there is no plan file and no
review agent - deterministic gates check your work immediately after you
finish, and a `/fix_gate` agent handles any gate failure.

## Variables

prompt: $ARGUMENTS

## Instructions

- Implement the request described in `prompt` directly - do not write a plan
  file or spec file first.
- Keep the change small, surgical, and minimal: touch only what the prompt
  requires, and prefer the smallest diff that fully satisfies it.
- Follow the existing code style and conventions in the surrounding files
  (naming, formatting, structure) rather than introducing your own.
- IMPORTANT: Do NOT run test suites or linters. The pipeline's deterministic
  gates run after you finish and will report anything you broke - running
  them yourself only burns time and tokens.
- If `prompt` is missing or too vague to act on, stop and say so rather than
  guessing at scope.

## Report

Return one short paragraph of free text describing what changed and why. This
is a status note, not an artifact - the working tree itself is the
deliverable, so do not return a file path, a plan, or a JSON block.

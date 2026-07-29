# Install & Prime

Set up the Python project for development.

## Read

.env.sample (never read .env)
README.md
CLAUDE.md
specs/M1_python_core.md

## Read and Execute

.claude/commands/prime.md

## Run

- Think through each of these steps to make sure you don't miss anything.
- Remove the existing git remote: `git remote remove origin` (if needed)
- Initialize a new git repository: `git init` (if needed)
- Install dependencies: `uv sync`
- Verify the project is healthy by delegating to the pipeline phases:
  - Run `/validate` to confirm the project builds, type-checks, and lints cleanly
  - Run `/test` to confirm the unit test suite passes
- **SRP note:** `/install` only handles dependency installation and project priming. Build and test verification are delegated to `/validate` and `/test` so each phase keeps its single responsibility.

## Report

- Output the work you've just done in a concise bullet point list.
- Instruct the user to fill out the root level ./.env based on .env.sample if it exists.
- Mention: 'To setup your AFK Agent, be sure to update the remote repo url and push to a new repo so you have access to git issues and git prs:
  ```
  git remote add origin <your-new-repo-url>
  git push -u origin main
  ```'
- Mention the command to run the application (e.g., `uv run bess --help`)
- List any external dependencies that should be installed for full functionality (check README.md)

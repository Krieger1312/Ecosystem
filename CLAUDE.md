# CLAUDE.md

This file provides guidance to Claude Code (and other AI assistants) when working with code in this repository.

## Repository status

This repository is a **fresh scaffold**. As of now it contains only:

- `README.md` — a single-line placeholder (`# Ecosystem`)
- `.git/` — version control metadata

There is no source code, package manifest, build configuration, test suite, or CI pipeline yet. There are no established conventions or workflows to document because no code has been written.

## Working in this repository right now

- Before assuming any language, framework, or tooling, check the repository contents — do not infer a stack from the name "Ecosystem" alone.
- When the first real code is added (e.g. a `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, or similar manifest), this file should be updated to document:
  - The language/framework and why
  - Directory/module layout
  - How to install dependencies, build, run, lint, and test
  - Any project-specific conventions (naming, architecture patterns, error handling, etc.)
  - Branching/PR conventions if they differ from the defaults below
- Keep this file in sync with the actual state of the repo. Prefer accuracy over completeness — a short, correct CLAUDE.md is better than a long, speculative one.

## Git conventions

- Default branch: `main`
- Commit messages should be clear and descriptive, explaining *why* a change was made.
- Do not force-push or rewrite history on `main` without explicit instruction.

## Next steps for maintainers

When bootstrapping this project, consider adding:

1. A manifest file appropriate to the chosen language/runtime.
2. A `.gitignore` tailored to that stack.
3. Linting/formatting configuration.
4. A test runner and at least one test.
5. A CI workflow (e.g. GitHub Actions) to run lint/build/test on push and PR.

Once any of the above exists, update this CLAUDE.md to reflect it.

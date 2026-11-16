# Phase 0: Bootstrap

**Read first:** `CLAUDE.md`, `docs/SETUP.md`, and §6.3 of `docs/plan.md`.
**Branch:** work directly on `main`; this phase creates it.

## Goal

Turn this directory into a repository with tooling and a working command contract.
No application code yet.

## Build (commit units)

1. **`chore: add project guide, prompts and Claude Code configuration`**
   Check the prerequisites from `docs/SETUP.md` section 1 and report each version. If something is
   missing, stop and tell me what to install; do not install system-level tools yourself.
   Run `git init` if needed, with `main` as the default branch. Add a `.gitignore` covering Python,
   Node, `.env`, `data/`, model caches, `eval/results/`, and `.claude/settings.local.json`.
   Confirm `docs/plan.md` exists. Tell me whether `docs/schema.sql` exists.
   Commit the files that are already here.

2. **`chore: initialize Python project and tooling`**
   `pyproject.toml` managed by uv: Python 3.12+, `src/ats/` layout, an empty `ats` package.
   Dev group: `ruff`, `pyright`, `pytest`, `pytest-asyncio`, `httpx`.
   Configure ruff (lint and format), pyright (strict for `src/`), and pytest with the markers
   `integration` and `llm`. Exclude `.claude/` from ruff and pyright: the hook scripts are tooling,
   not project code. One trivial unit test so the test run is not empty.

3. **`chore: add Makefile command contract and env template`**
   A `Makefile` with every target listed in `docs/SETUP.md` section 3. Targets that belong to a
   later phase print which phase adds them and exit non-zero. `make check` and `make test` work now.
   `.env.example` with the variables from `docs/SETUP.md` section 4 that exist so far.
   A short `README.md` that points to `docs/SETUP.md`.

## Out of scope

Docker Compose, database, API, worker, frontend. Those are phase 1.1a.

## Done when

- [ ] `make check` passes on a clean checkout after `uv sync`.
- [ ] Editing a `.py` file triggers the format hook: a badly formatted line is reformatted after the edit.
- [ ] A commit attempt with a failing unit test is blocked by the pre-commit hook, and passes once the test is fixed.
- [ ] `git log --oneline` shows three commits, one per unit.
- [ ] `docs/PROGRESS.md` marks phase 0 as merged.

## Notes

- The hooks in `.claude/hooks/` are already written. Verify them; do not rewrite them.
- If the hooks do not fire, report it instead of working around it.

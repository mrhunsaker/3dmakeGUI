<!--
 Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.
 SPDX-License-Identifier: Apache-2.0
-->

# Contributing to 3DMake GUI Wrapper

Thank you for your interest in contributing. This document explains how to get
started, what is expected from contributors, and how the review process works.

## Code of Conduct

All participants are expected to follow the
[Python Community Code of Conduct](https://policies.python.org/python.org/code-of-conduct/).
Respectful, professional communication is required in all project spaces
(issues, pull requests, discussions, and commit messages).

## Security Issues

**Do not open public Issues for security vulnerabilities.** See
[SECURITY.md](SECURITY.md) for the private reporting process.

---

## Getting Started

### Prerequisites

| Tool                                            | Version | Purpose               |
| ----------------------------------------------- | ------- | --------------------- |
| Python                                          | 3.11+   | Runtime               |
| [uv](https://github.com/astral-sh/uv)           | latest  | Dependency management |
| [tdeck/3dmake](https://github.com/tdeck/3dmake) | latest  | The wrapped CLI       |

### Fork and Clone

```bash
# 1. Fork on GitHub, then:
git clone https://github.com/<your-username>/3dmakeGUI.git
cd 3dmakeGUI

# 2. Add the upstream remote
git remote add upstream https://github.com/mrhunsaker/3dmakeGUI.git
```

### Install Dependencies

```bash
uv sync --all-extras
```

This creates `.venv/` with all runtime, viewer, and development dependencies.

---

## Workflow

### Branch Naming

Use short, descriptive kebab-case names:

```plaintext
feat/word-wrap-persistence
fix/stream-command-slot-error
docs/container-setup
test/core-path-helpers
```

### Making Changes

1. Create a feature branch from `main`:

   ```bash
   git checkout -b feat/my-feature
   ```

2. Make focused, atomic commits. Each commit should compile and pass tests.

3. Before opening a pull request, run the full validation suite:

   ```bash
   # Compile check
   .venv/bin/python -m py_compile \
       src/tdmake_gui_wrapper/app.py \
       src/tdmake_gui_wrapper/core.py \
       src/tdmake_gui_wrapper/__main__.py

   # Lint
   uv run ruff check src/

   # Format check (does not modify files)
   uv run black --check src/ tests/ scripts/

   # Tests
   uv run pytest -q
   uv run pytest tests/test_bump_version.py -q
   ```

4. If lint or format checks fail, fix them:

   ```bash
   uv run ruff check --fix src/
   uv run black src/ tests/ scripts/
   ```

5. Update [README.md](README.md) and docstrings when you change observable
   behavior or add new features.

6. Open a pull request against `main` with a clear description of what changed
   and why.

### Pull Request Checklist

Before marking a PR ready for review:

- [ ] All compile, lint, format, and test checks pass locally
- [ ] New logic is covered by tests where practical
- [ ] Accessibility behavior is preserved (or explicitly improved)
- [ ] Keyboard shortcuts are preserved (or replaced with documented alternatives)
- [ ] GUI behavior stays aligned with the underlying `3dm` CLI behavior
- [ ] Documentation is updated if the change is user-visible
- [ ] Version is **not** bumped in the PR — maintainers handle releases

---

## Project Conventions

### Language and Runtime

- Python **3.11** or newer.
- Type annotations use the modern union syntax (`X | None`, not `Optional[X]`).
- No walrus operator (`:=`) in UI event callbacks — it creates slot-context issues with NiceGUI.
- Avoid `asyncio.create_task` inside NiceGUI button/event callbacks; run logic
  inline or use `async def` handlers directly.

### Formatting

Handled by **Black**. Configuration in `pyproject.toml`:

```toml
[tool.black]
line-length = 88
target-version = ["py311"]
```

Run: `uv run black src/ tests/ scripts/`

### Linting

Handled by **Ruff**. Configuration in `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "C4", "UP"]
ignore = ["E501"]
```

Run: `uv run ruff check src/`  
Auto-fix: `uv run ruff check --fix src/`

### Testing

- Tests live in `tests/` and are run with **pytest**.
- `asyncio_mode = "auto"` is set; mark async tests with `async def test_...`.
- Current suite coverage includes:
  - `tests/test_core.py` for core path and command helpers
  - `tests/test_bump_version.py` for version bump utility behavior
- GUI tests require a running NiceGUI server and are out of scope for CI at
  this time.

Run: `uv run pytest -q`

Targeted run: `uv run pytest tests/test_bump_version.py -q`

### Dependencies

- Runtime dependencies go in `[project].dependencies` in `pyproject.toml`.
- Optional extras go in `[project.optional-dependencies]`.
- Development-only tools go in `[dependency-groups].dev`.
- Avoid adding dependencies without discussion; keep the runtime footprint small.
- Pin only minimum versions (`>=x.y`), not exact versions, unless a specific
  bug fix is required.

### Versioning

This project uses calendar versioning: `YYYY.MM.DD`.

Do **not** bump the version in contributor PRs. Maintainers run the bump
script before a release:

```bash
.venv/bin/python scripts/bump_version.py
```

### Accessibility

Accessibility is a first-class concern for this project. All contributions must:

- preserve or improve keyboard navigation
- preserve or improve screen-reader announcements (`aria-label`, `aria-live`, focus management)
- not remove named regions, shortcut keys, or accessible dialogs
- test with at least one screen reader if the change touches the UI

---

## Style Details

See [STYLE.md](STYLE.md) for detailed naming conventions, file structure, and
NiceGUI-specific patterns used in this codebase.

---

## Commit Messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```plaintext
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

Common types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

Examples:

```plaintext
feat(editor): add word wrap toggle with persistence
fix(core): handle missing PATH variable on first run
docs(readme): add container usage section
test(core): add tests for add_app_to_user_path on Linux
```

---

## Releasing (Maintainers Only)

1. Run `scripts/bump_version.py` and commit the version bump.
2. Tag the commit: `git tag v2026.05.01 && git push origin v2026.05.01`
3. The GitHub Actions release workflow builds and publishes release artifacts
   automatically.

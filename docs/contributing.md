# Contributing

Contributor expectations are documented in [CONTRIBUTING.md](https://github.com/mrhunsaker/3dmakeGUI/blob/main/CONTRIBUTING.md).

## Quick Workflow

1. Fork and clone the repository.
2. Create a focused feature branch.
3. Install dependencies with `uv sync --all-extras`.
4. Run lint, format, and test checks.
5. Open a pull request with a clear summary.

## Required Checks

```bash
uv run ruff check src/
uv run black --check src/ tests/ scripts/
uv run pytest -q
uv run pytest tests/test_bump_version.py -q
```

Current pytest modules:

- `tests/test_core.py`
- `tests/test_bump_version.py`

## Accessibility Requirement

Accessibility is a release-quality requirement. Contributions that affect UI
must preserve keyboard navigation and screen-reader behavior.

## Code of Conduct

The project follows the [Python Code of Conduct](https://policies.python.org/python.org/code-of-conduct/).

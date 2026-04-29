# Style Guide

The canonical style rules are in [STYLE.md](https://github.com/mrhunsaker/3dmakeGUI/blob/main/STYLE.md). This page summarizes
project-critical conventions.

## Formatting and Linting

- Black line length: 88
- Ruff rule families: `E`, `F`, `W`, `I`, `B`, `C4`, `UP`

Commands:

```bash
uv run black src/ tests/ scripts/
uv run ruff check src/
```

## Type Hints

Use Python 3.11 style annotations:

- `X | None` instead of `Optional[X]`
- `list[str]`, `dict[str, int]` instead of legacy typing aliases

## NiceGUI Patterns

- Avoid detached UI mutations outside slot context.
- Prefer direct async handlers over `asyncio.create_task` in button callbacks.
- Use explicit focus management in dialogs for screen-reader compatibility.

## Structure

- `core.py` for platform/process utility logic
- `app.py` for NiceGUI interface orchestration
- `__main__.py` for module entrypoint

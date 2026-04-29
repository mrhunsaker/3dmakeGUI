<!--
 Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.
 SPDX-License-Identifier: Apache-2.0
-->

# Style Guide

This document describes the coding style and patterns used in this project.
Follow these conventions when contributing so that the codebase stays
consistent and accessible.

Automated enforcement is provided by **Black** (formatting) and **Ruff**
(linting). The guidance here covers intent, patterns, and project-specific
decisions that go beyond what a linter can check.

---

## Python Version and Type Annotations

- Target **Python 3.11+** in all new code.
- Use the modern union syntax for optional and union types:

  ```python
  # Correct
  def foo(name: str | None = None) -> int | str: ...

  # Wrong — triggers ruff UP045 / UP007
  from typing import Optional, Union
  def foo(name: Optional[str] = None) -> Union[int, str]: ...
  ```

- Use built-in generic types directly (`list[str]`, `dict[str, int]`,
  `tuple[int, ...]`) instead of `List`, `Dict`, `Tuple` from `typing`.

- Annotate all function parameters and return types in `core.py`. Annotations
  in `app.py` are encouraged but optional for private helpers.

---

## Formatting (Black)

| Setting        | Value   |
| -------------- | ------- |
| Line length    | 88      |
| Target version | `py311` |

Black is not negotiable — run it before every commit:

```bash
uv run black src/ tests/ scripts/
```

### Strings

Black normalizes quote style. Do not fight it. Use double quotes in your
source; Black will normalize the rest.

### Trailing commas

Use trailing commas in multi-line collections and function signatures so that
Black formats them consistently:

```python
result = some_function(
    first_argument,
    second_argument,
    third_argument,
)
```

---

## Linting (Ruff)

Active rule sets: `E`, `F`, `W`, `I`, `B`, `C4`, `UP`.

`E501` (line too long) is ignored because Black handles line length.

Run the linter:

```bash
uv run ruff check src/
uv run ruff check --fix src/   # auto-fix safe issues
```

### Common rules to be aware of

| Code    | Rule                        | Notes                                              |
| ------- | --------------------------- | -------------------------------------------------- |
| `F841`  | Unused variable             | Remove or replace with `_`                         |
| `E731`  | Lambda assignment           | Use `def` instead                                  |
| `B006`  | Mutable default argument    | Use `None` sentinel and assign inside the function |
| `UP045` | `Optional[X]` → `X \| None` | Use modern union syntax                            |
| `UP007` | `Union[X, Y]` → `X \| Y`    | Use modern union syntax                            |
| `I001`  | Import order                | Ruff auto-fixes; stdlib → third-party → local      |

---

## Naming Conventions

Follow [PEP 8](https://peps.python.org/pep-0008/):

| Construct                                    | Convention         | Example                       |
| -------------------------------------------- | ------------------ | ----------------------------- |
| Module                                       | `snake_case`       | `core.py`                     |
| Class                                        | `PascalCase`       | `AppConfig`                   |
| Function / method                            | `snake_case`       | `get_project_root`            |
| Variable                                     | `snake_case`       | `file_path`                   |
| Constant                                     | `UPPER_SNAKE_CASE` | `DEFAULT_PORT`                |
| Private helper                               | leading underscore | `_build_cli_parser`           |
| "ref" holders (mutable single-element lists) | `_name_ref`        | `_log_ref`, `_popup_host_ref` |

### NiceGUI UI element references

When a UI element needs to be referenced from a nested or deferred context,
store it in a single-element list (`ref = [None]`) and assign at creation:

```python
_log_ref: list = [None]

# later, inside the page layout:
_log_ref[0] = ui.log().classes("w-full")
```

This pattern avoids Python closure/late-binding issues with lambda and async handlers.

---

## File and Module Structure

```
src/tdmake_gui_wrapper/
├── __init__.py      # version, author — no imports of app or core
├── __main__.py      # entry point — one import, calls main()
├── app.py           # all NiceGUI page and UI logic
└── core.py          # pure utility functions, no NiceGUI imports
```

Rules:

- `core.py` must **not** import from `app.py` or `nicegui`.
- `app.py` may import from `core.py` but not from `__main__.py`.
- `__main__.py` uses absolute imports only (required for PyInstaller).
- Do not add new top-level modules without discussion.

---

## NiceGUI Patterns

### Slot context

NiceGUI renders UI inside a per-request "slot context". Code that creates or
modifies UI elements **must** run inside that context. Breaking this causes
a `RuntimeError: No slot found`.

**Never** schedule UI creation from a detached coroutine or background thread:

```python
# Wrong — asyncio.create_task detaches from the slot context
async def on_click():
    asyncio.create_task(_do_something_that_touches_ui())

# Correct — await directly inside the event handler
async def on_click():
    await _do_something_that_touches_ui()

# Also correct — synchronous handler, no async needed
def on_click():
    _do_something_synchronous()
```

### Background work with UI updates

Use `asyncio.Queue` to pass results from background work back to the UI:

```python
queue: asyncio.Queue = asyncio.Queue()

async def _produce():
    # runs off the main event loop if needed
    await queue.put("line of output")

async def _consume(log_element):
    while True:
        line = await queue.get()
        log_element.push(line)
```

### Dialogs and modals

Create dialogs inside a stable container element that is part of the page
layout. A hidden zero-size host div is used for this:

```python
_popup_host_ref: list = [None]

# in the page layout:
_popup_host_ref[0] = ui.element("div").classes("w-0 h-0 overflow-hidden")

# in a helper:
with _popup_host_ref[0]:
    with ui.dialog() as dlg:
        ...
    dlg.open()
```

### Accessibility requirements

Every interactive UI element must have an accessible label:

```python
# Buttons
ui.button("Build STL", on_click=...).props('aria-label="Build STL"')

# Inputs
ui.input(label="Project file").props('aria-label="Project file path"')

# Upload
ui.upload(...).props("aria-label='Upload a .scad or .stl file'")
```

Focus management in dialogs: move focus into the dialog content immediately
after opening so screen-reader users receive context without navigating manually.

---

## Import Order

Ruff (`I` rules) enforces this order automatically:

1. Standard library (`import os`, `from pathlib import Path`)
2. Third-party (`import nicegui`, `from nicegui import ui`)
3. Local (`from tdmake_gui_wrapper.core import get_project_root`)

Separate each group with a blank line. Do not mix groups.

---

## Comments and Docstrings

- Write docstrings for all public functions in `core.py` using the one-line
  or Google-style format.
- Inline comments should explain **why**, not **what**. Avoid restating the code.
- Keep TODO comments short and actionable; link to an issue when possible.

```python
# Good
# NiceGUI requires the dialog to be created inside a slot-context container;
# using a hidden host div avoids RuntimeError when called from async callbacks.

# Bad
# create the dialog
```

---

## Testing

- One test file per module: `tests/test_core.py`, `tests/test_app.py` (future).
- Test function names describe the scenario: `test_get_project_root_returns_parent`.
- Use `pytest.mark.parametrize` for multiple input cases instead of loops.
- Do not mock the file system unless absolutely necessary; use `tmp_path` fixtures.
- Async test functions are handled automatically (`asyncio_mode = "auto"`).

---

## Container / Packaging Style

- The `Dockerfile` uses a multi-stage build. Keep the `builder` stage lean;
  only copy artifacts needed at runtime into the `runtime` stage.
- Always run as a non-root user in container images (UID 1001).
- Drop all Linux capabilities in Compose and Pod specs unless a specific
  capability is required and documented.
- Bind published ports to `127.0.0.1` by default in all Compose files.

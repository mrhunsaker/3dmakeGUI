# 3DMake GUI Wrapper

A **NiceGUI**-based GUI wrapper for [tdeck/3dmake](https://github.com/tdeck/3dmake),
designed for **screenreader accessibility** and **terminal-first workflows**.

---

## Features

- High-contrast, keyboard-navigable UI
- Discovers the `3dm` binary automatically (PATH, env var, or common install dirs)
- One-click quick actions: Describe, Render, Slice, Orient, Preview
- Custom command input with live streaming output
- Built-in CodeMirror editor for `.scad` files with load/save
- Fully compilable to a standalone desktop app via **PyInstaller**

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| Python 3.9+ | Runtime |
| [uv](https://github.com/astral-sh/uv) | Dependency management |
| [tdeck/3dmake](https://github.com/tdeck/3dmake) | The CLI tool being wrapped |

---

## Setup

```bash
# 1. Clone this repo
git clone https://github.com/mrhunsaker/3dmake-gui-wrapper.git
cd 3dmake-gui-wrapper

# 2. Install dependencies (creates .venv automatically)
uv sync

# 3. Run the GUI
uv run python -m dmake_gui_wrapper
```

The app opens at **http://localhost:8080** in your default browser.

To open a **native desktop window** instead of a browser tab, edit `app.py` and
change `ui.run(...)` to include `native=True`. This requires `pywebview` (already
in the dependencies).

---

## Locating the `3dm` Binary

The app searches in this order:

1. `THREE_DM_PATH` environment variable (set to the absolute path of `3dm`)
2. Your system `PATH` via `shutil.which`
3. Common install directories (`~/3dmake/`, `/usr/local/bin/`, `%LOCALAPPDATA%\3dmake\`)

If not found, the header will show a warning and commands will fail gracefully.

```bash
# Example: explicitly point to your 3dmake installation
export THREE_DM_PATH="/home/user/3dmake/3dm"
uv run python -m dmake_gui_wrapper
```

---

## Project Structure

```
3dmake-gui-wrapper/
├── src/
│   └── dmake_gui_wrapper/   # Main package (note: no leading digit)
│       ├── __init__.py
│       ├── __main__.py      # python -m entry point
│       ├── app.py           # NiceGUI page layout & UI logic
│       └── core.py          # Binary discovery & async command runner
├── tests/
│   ├── conftest.py
│   └── test_core.py
├── .github/
│   └── workflows/
│       └── ci.yml           # CI + PyInstaller build matrix
├── docs/
├── 3dmake_gui.spec          # PyInstaller build spec
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## Running Tests

```bash
uv run pytest -v
```

---

## Building a Standalone Desktop App (PyInstaller)

```bash
# Install dev dependencies (includes pyinstaller)
uv sync --all-extras

# Build (output → dist/3dmake-gui/)
uv run pyinstaller 3dmake_gui.spec
```

The resulting `dist/3dmake-gui/` folder is self-contained — copy it anywhere and
run `./3dmake-gui` (Linux) or `3dmake-gui.exe` (Windows). No Python installation
required on the target machine.

> **Note on NiceGUI + PyInstaller**: NiceGUI ships its static web assets (JS, CSS,
> fonts) inside the Python package. The `.spec` file explicitly calls
> `collect_data_files("nicegui")` to bundle them. If you upgrade NiceGUI, re-test
> the build.

---

## Known Issues / Limitations

- The **Browse** button uses `app.native.main_window.create_file_dialog()`, which
  only works in `native=True` mode. In browser mode it shows a notification.
  As a workaround, type the path directly or use drag-and-drop upload.
- `ui.monaco_editor` does not exist in NiceGUI ≥1.4 — the original `main.py` used
  this erroneously. This project uses `ui.codemirror` instead, which is the correct
  NiceGUI API.
- PyInstaller builds are per-platform; you must build on Windows to get a `.exe`.

---

## License

Apache 2,0

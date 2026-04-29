# Getting Started

## Requirements

| Tool                                      | Version | Purpose                               |
| ----------------------------------------- | ------- | ------------------------------------- |
| Python                                    | 3.11+   | Runtime                               |
| [uv](https://github.com/astral-sh/uv)     | latest  | Environment and dependency management |
| [3dmake](https://github.com/tdeck/3dmake) | latest  | Wrapped CLI (`3dm`)                   |

Optional:

- `trimesh` for richer STL dimension support
- `pywebview` for native window mode in packaged builds

## Install From Source

```bash
git clone https://github.com/mrhunsaker/3dmakeGUI.git
cd 3dmakeGUI
uv sync --all-extras
```

## Run

```bash
uv run python -m tdmake_gui_wrapper
```

Or, after package installation:

```bash
3dmake-gui
```

## CLI Flags

- `--help` (also `--hrlp` alias)
- `--version`

## Typical Workflow

1. Select a project file/folder.
2. Pick command options (model/view/profile/overlay/scale/copies).
3. Run a quick action (`build`, `preview`, `slice`, etc.).
4. Review streamed output and the line-numbered output popup.
5. Inspect generated SVG or STL outputs.

## Configuration Paths

The app locates the `3dm` binary in this order:

1. `THREE_DM_PATH`
2. System `PATH`
3. Known installation locations

The 3dmake config directory resolves by platform, unless overridden by
`THREEDMAKE_CONFIG_DIR`.

## Local Validation Commands

```bash
uv run ruff check src/
uv run black --check src/ tests/ scripts/
uv run pytest -q
uv run pytest tests/test_bump_version.py -q
```

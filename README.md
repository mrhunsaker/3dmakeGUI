# 3DMake GUI Wrapper

3DMake GUI Wrapper is an accessibility-focused NiceGUI frontend for
[tdeck/3dmake](https://github.com/tdeck/3dmake). It gives keyboard and screen-reader
users a practical way to create, inspect, preview, export, and print 3DMake models
without losing direct access to the underlying `3dm` command-line workflow.

## What This Program Does

The application wraps the `3dm` CLI in a two-panel desktop-style interface with:

- project and file selection
- one-click quick actions for common `3dm` workflows
- a built-in source editor for `.scad` and config files
- streamed command output in a live log
- accessible popup windows for text command results
- SVG preview viewing
- interactive STL viewing
- printer and overlay/profile management
- release-friendly packaging through PyInstaller

The GUI is designed to complement the CLI, not replace it. You can use the GUI for
the common workflow and still drop down to custom `3dm` commands when you need to.

## Documentation

Comprehensive project documentation is generated with MkDocs and published to
GitHub Pages.

- Published docs site: <https://mrhunsaker.github.io/3DMAKEGUI/>
- Docs workflow: [.github/workflows/documentation.yml](.github/workflows/documentation.yml)
- Docs configuration: [mkdocs.yml](mkdocs.yml)

### Documentation Index

| Topic                  | GitHub Pages                                              | Source                                             |
| ---------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| Home                   | <https://mrhunsaker.github.io/3DMAKEGUI/>                 | [docs/index.md](docs/index.md)                     |
| Getting Started        | <https://mrhunsaker.github.io/3DMAKEGUI/getting-started/> | [docs/getting-started.md](docs/getting-started.md) |
| Security               | <https://mrhunsaker.github.io/3DMAKEGUI/security/>        | [docs/security.md](docs/security.md)               |
| Containers             | <https://mrhunsaker.github.io/3DMAKEGUI/containers/>      | [docs/containers.md](docs/containers.md)           |
| Contributing           | <https://mrhunsaker.github.io/3DMAKEGUI/contributing/>    | [docs/contributing.md](docs/contributing.md)       |
| Style Guide            | <https://mrhunsaker.github.io/3DMAKEGUI/style-guide/>     | [docs/style-guide.md](docs/style-guide.md)         |
| API: Core Utilities    | <https://mrhunsaker.github.io/3DMAKEGUI/api/core/>        | [docs/api/core.md](docs/api/core.md)               |
| API: GUI Application   | <https://mrhunsaker.github.io/3DMAKEGUI/api/app/>         | [docs/api/app.md](docs/api/app.md)                 |
| API: Versioning Script | <https://mrhunsaker.github.io/3DMAKEGUI/api/versioning/>  | [docs/api/versioning.md](docs/api/versioning.md)   |

### Build Documentation Locally

```bash
uv sync --group docs
uv run --group docs mkdocs serve
```

Then open: <http://127.0.0.1:8000>

For a strict production build:

```bash
uv run --group docs mkdocs build --strict
```

## Feature Overview

### Accessibility And Keyboard Support

- named application regions for fast navigation
- F6 and Shift+F6 region cycling
- Ctrl+, keyboard help dialog
- Ctrl+Shift+E/F/C/L/S shortcuts for editor, file path, command input, log, and settings
- global Ctrl+S save behavior
- screen-reader announcements for editor entry and focus changes
- accessible command output dialogs with focus moved into the popup automatically
- popup dismissal via OK button or Escape
- line-numbered, monospace text output for easier screen-reader review

### 3DMake Command Support

The GUI exposes direct buttons and settings for these workflows:

- `3dm info`
- `3dm build`
- `3dm slice`
- `3dm orient`
- `3dm preview`
- `3dm new`
- `3dm build slice`
- `3dm build orient slice`
- `3dm print`
- `3dm image`
- `3dm setup`
- `3dm list-libraries`
- `3dm install-libraries`
- `3dm list-profiles`
- `3dm list-overlays`
- `3dm version`
- `3dm self-update`
- `3dm help`
- arbitrary custom commands through the command box

### Command Options Panel

The Command Options panel lets you build common flags without typing them manually:

- model name
- view
- profile
- overlays
- scale
- copies
- debug
- interactive info mode

These options are appended to compatible quick actions automatically.

### Editor Features

The built-in CodeMirror editor supports:

- loading and saving model files
- loading global `defaults.toml`
- loading project `3dmake.toml`
- opening overlay, profile, and prompt files directly in the editor
- runtime font size changes
- runtime word wrap toggle
- persistent word wrap preference across restarts

### Preview And Viewer Features

- SVG preview dialog after successful `3dm preview`
- “View Last SVG” button for reopening generated SVG output
- STL viewer dialog with Three.js rendering
- keyboard-accessible STL rotation and zoom controls
- bounding-box dimensions for STL files

### Packaging And Release Features

- PyInstaller build spec for Linux and Windows
- GitHub Actions workflow that builds release artifacts on Linux and Windows
- local end-to-end maintenance/release workflow via [update_system.py](update_system.py)
- Linux release asset packaged as `3dmake-gui.tar.gz`
- Windows release asset packaged as `3dmake-gui.zip`
- versioned GitHub Releases created from tags or manual workflow input

### Versioning Utilities

- date-based versioning using `YYYY.MM.DD`
- interactive version bump script in [scripts/bump_version.py](scripts/bump_version.py)
- synchronized version updates for [pyproject.toml](pyproject.toml) and [src/tdmake_gui_wrapper/**init**.py](src/tdmake_gui_wrapper/__init__.py)

## Requirements

| Tool                                            | Purpose               |
| ----------------------------------------------- | --------------------- |
| Python 3.11+                                    | Runtime               |
| [uv](https://github.com/astral-sh/uv)           | Dependency management |
| [tdeck/3dmake](https://github.com/tdeck/3dmake) | Core modeling CLI     |

Optional:

- `trimesh` for richer STL dimension support
- `pywebview` for native-window mode and packaged desktop builds

## Installation

```bash
git clone https://github.com/mrhunsaker/3dmakeGUI.git
cd 3dmakeGUI
uv sync --all-extras
```

## Running The Application

### Launch From Source

```bash
uv run python -m tdmake_gui_wrapper
#or
uv run 3dmake-gui
```

Or after installing the package:

```bash
3dmake-gui
```

By default the app starts the NiceGUI server and opens the interface in a browser.

### CLI Options

The launcher now supports these options before the GUI starts:

- `3dmake-gui --help`
- `3dmake-gui --version`

`--help` prints usage help. `--version` prints the package version and exits.

## Locating The `3dm` Binary

The app looks for `3dm` in this order:

1. `THREE_DM_PATH`
2. the system `PATH`
3. known install folders resolved by the app

You can also set the binary path from the Settings section inside the GUI.

Example:

```bash
export THREE_DM_PATH="/home/user/3dmake/3dm"
uv run python -m tdmake_gui_wrapper
```

## Using The GUI

### Typical Workflow

1. Choose a project file or project directory.
2. Adjust Command Options if needed.
3. Run a quick action like Build STL, Preview, or Full Pipeline.
4. Review the Output Log and the accessible popup dialog.
5. Open generated SVG or STL assets in the built-in viewers.
6. Edit model or config files in the editor and save changes.

### Settings Section

The Settings section provides commands and file-loading helpers for:

- setup
- global config
- project config
- 3dm path override
- library listing and installation
- profile and overlay listing
- version info
- self update
- CLI help
- overlay/profile/prompt editing in the embedded editor

### Custom Command Section

The Custom Command box is for direct `3dm` invocation when a button does not cover
your use case. Output is still streamed to the log and shown in the accessible popup.

## Running With Docker

The repository ships a production-ready [Dockerfile](Dockerfile) and
[docker-compose.yml](docker-compose.yml).

### Quick start

```bash
# Build the image
docker compose build

# Start in the foreground (Ctrl-C to stop)
docker compose up

# Start in the background
docker compose up -d

# Stop and remove containers
docker compose down
```

The NiceGUI interface is available at **http://localhost:8080**.
The port is bound to `127.0.0.1` only; change the `ports` entry in
`docker-compose.yml` to expose it externally (and place an authenticating
reverse proxy in front of it when you do).

### Volumes

Two named Docker volumes are created automatically:

| Volume     | Mount path                         | Purpose                      |
| ---------- | ---------------------------------- | ---------------------------- |
| `projects` | `/home/appuser/projects`           | Your 3D-project files        |
| `settings` | `/home/appuser/.config/3dmake-gui` | GUI settings and preferences |

Replace a named volume with a host-path bind mount in `docker-compose.yml` to
work on files that live on your host machine:

```yaml
volumes:
  - /home/youruser/projects:/home/appuser/projects
```

### Security posture

The Docker image runs with:

- a non-root user (`appuser`, UID 1001)
- all Linux capabilities dropped
- a read-only root filesystem (`/tmp` is a tmpfs)
- `no-new-privileges` enforced

See [SECURITY.md](SECURITY.md) for the full policy.

---

## Running With Podman

Two Podman-specific files are provided:

| File                                     | Usage                                     |
| ---------------------------------------- | ----------------------------------------- |
| [podman-compose.yml](podman-compose.yml) | `podman-compose` (Compose-style workflow) |
| [container.yaml](container.yaml)         | `podman play kube` (Kubernetes Pod spec)  |

### podman-compose

```bash
# Install podman-compose if needed
pip install podman-compose

# Build and start
podman build -t 3dmake-gui-wrapper:2026.04.29 .
podman-compose up -d

# Stop and remove
podman-compose down
```

### podman play kube

```bash
podman build -t 3dmake-gui-wrapper:2026.04.29 .
podman play kube container.yaml

# Stop and clean up
podman play kube --down container.yaml
```

The Podman configs mirror the Docker security posture (non-root, dropped
capabilities, read-only FS) and additionally set `user: "1001:1001"` explicitly
for rootless Podman environments.

---

## Building A Desktop Bundle

```bash
uv sync --all-extras
uv run pyinstaller 3dmake_gui.spec
```

Output is written to `dist/3dmake-gui/`.

On Linux, run:

```bash
./dist/3dmake-gui/3dmake-gui
```

On Windows, run `3dmake-gui.exe` from the generated folder.

## GitHub Release Automation

The repository includes a release workflow at [.github/workflows/release.yml](.github/workflows/release.yml).

It supports:

- tag-triggered releases for tags like `v2026.04.29`
- manual workflow dispatch with a version input
- Linux packaging to `3dmake-gui.tar.gz`
- Windows packaging to `3dmake-gui.zip`
- automatic GitHub Release creation with those assets attached

## Documentation Site (GitHub Pages)

Project documentation is published at:

- <https://mrhunsaker.github.io/3DMAKEGUI/>

The docs use MkDocs + Material + mkdocstrings and render API content from
NumPy-style docstrings in source code.

### Build docs locally

```bash
uv sync --group docs
uv run --group docs mkdocs serve
```

or for a one-time static build:

```bash
uv run --group docs mkdocs build --strict
```

The GitHub Actions workflow at [.github/workflows/documentation.yml](.github/workflows/documentation.yml)
builds and deploys docs to GitHub Pages on pushes to `main`.

## Version Management

Use the bump script to update versions interactively:

```bash
.venv/bin/python scripts/bump_version.py
```

The script prompts for which aspect to increase:

- year
- month
- day
- revision

It updates:

- [pyproject.toml](pyproject.toml)
- [src/tdmake_gui_wrapper/\_\_init\_\_.py](src/tdmake_gui_wrapper/__init__.py)

## Update Workflow Script

The repository includes [update_system.py](update_system.py) to run the common
maintenance and release workflow in the expected order.

Run the full workflow:

```bash
uv run python update_system.py
```

By default it performs:

- dependency sync with all extras
- lint and format (auto-fix + strict check)
- test suite
- strict docs build
- interactive version bump
- PyInstaller build

Common skip flags:

- `--no-checks`
- `--no-docs`
- `--no-bump`
- `--no-pyinstaller`

Example (run checks/tests only):

```bash
uv run python update_system.py --no-docs --no-bump --no-pyinstaller
```

## Development

### Running Tests

```bash
uv run pytest -q
```

Current pytest modules:

- `tests/test_core.py`
- `tests/test_bump_version.py`

Run the version bump tests directly:

```bash
uv run pytest tests/test_bump_version.py -q
```

### Useful Validation Commands

```bash
.venv/bin/python -m py_compile src/tdmake_gui_wrapper/app.py src/tdmake_gui_wrapper/core.py src/tdmake_gui_wrapper/__main__.py
uv run pytest tests/test_core.py -q
uv run pytest tests/test_bump_version.py -q
```

## Project Structure

```text
3dmakeGUI/
├── .github/workflows/release.yml
├── scripts/bump_version.py
├── update_system.py
├── src/tdmake_gui_wrapper/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py
│   └── core.py
├── tests/test_bump_version.py
├── tests/test_core.py
├── 3dmake_gui.spec
├── container.yaml          # Podman play kube Pod spec
├── docker-compose.yml      # Docker Compose
├── Dockerfile              # Multi-stage container build
├── podman-compose.yml      # podman-compose equivalent
├── pyproject.toml
├── CONTRIBUTING.md
├── SECURITY.md
├── STYLE.md
├── README.md
└── LICENSE
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide, and
[STYLE.md](STYLE.md) for code style conventions.

Quick summary:

1. Fork → feature branch → `uv sync --all-extras` → focused change → tests → PR.
2. Format with **Black** (line length 88) and lint with **Ruff** before pushing (save time by running `ruff check --fix`).
3. Preserve accessibility behavior and keyboard shortcuts unless a change explicitly improves them.
4. Follow the [Python Code of Conduct](https://policies.python.org/python.org/code-of-conduct/).

See [SECURITY.md](SECURITY.md) to report vulnerabilities privately.

## Known Limitations

- PyInstaller builds are platform-specific.
- Native-folder dialogs depend on the runtime environment.
- Browser sandbox warnings can appear depending on the host environment and are not always application bugs.

## License

This project is licensed under the Apache License, Version 2.0.

You may use, modify, and distribute this software under the terms of the Apache 2.0 license. See the [LICENSE](LICENSE) file for the full license text.

---

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)  
[![MkDocs](https://img.shields.io/badge/MkDocs-526CFE?logo=materialformkdocs&logoColor=fff)](https://github.com/mrhunsaker/3dmakeGUI/actions/workflows/documentation.yml) [![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://mrhunsaker.github.io/3DMAKEGUI/)  
[![FastAPI](https://img.shields.io/badge/FastAPI-009485.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) [![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-%2338B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)  
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=000)](https://developer.mozilla.org/docs/Web/JavaScript) [![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/)  
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=fff)](https://www.docker.com/)

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)

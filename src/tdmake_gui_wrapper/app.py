# Copyright 2026 Michael Ryan Hunsaker, M.Ed., Ph.D.
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     https://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
3DMake GUI Wrapper
==================
NiceGUI-based frontend for the tdeck/3dmake CLI tool.

Run with:
    uv run python -m tdmake_gui_wrapper.app
or (after installing the package):
    3dmake-gui
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from nicegui import app, ui

from .core import (
    find_3dm_binary,
    get_3dmake_defaults_toml_path,
    resolve_3dm_binary_path,
    run_command_async,
)

# ──────────────────────────────────────────────────────────────────────────────
# App-wide state
# ──────────────────────────────────────────────────────────────────────────────

_3dm_path: Optional[str] = None
_current_file: Optional[Path] = None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _log(output_log: ui.log, message: str) -> None:
    """Push a message to the output log widget."""
    output_log.push(message)


async def _stream_command(
    cmd: str, output_log: ui.log, cwd: Optional[str] = None
) -> None:
    """Stream a shell command's output into the NiceGUI log widget."""
    _log(output_log, f"▶ {cmd}")
    async for line in run_command_async(cmd, cwd=cwd):
        if line.startswith("[done]"):
            rc = line.split()[-1]
            status = "✅ Done" if rc == "0" else f"❌ Exited with code {rc}"
            _log(output_log, status)
        elif line.startswith("[stderr]"):
            _log(output_log, line[9:])  # strip tag
        else:
            _log(output_log, line[9:])  # strip [stdout]


def _find_project_root(path_value: str) -> Optional[Path]:
    """Return project root if *path_value* is inside a 3dmake project."""
    if not path_value:
        return None

    raw = Path(path_value).expanduser()
    search = raw if raw.is_dir() else raw.parent
    for candidate in [search, *search.parents]:
        if (candidate / "3dmake.toml").exists():
            return candidate
    return None


def _ensure_project_layout(project_root: Path, project_name: str) -> None:
    """Create required 3dmake folders/files if they don't exist yet."""
    (project_root / "src").mkdir(parents=True, exist_ok=True)
    (project_root / "build").mkdir(parents=True, exist_ok=True)

    cfg = project_root / "3dmake.toml"
    if not cfg.exists():
        cfg.write_text(
            "\n".join(
                [
                    "[project]",
                    f'name = "{project_name}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _normalize_scad_filename(name: str) -> str:
    """Ensure the filename is non-empty and ends with .scad."""
    cleaned = (name or "").strip() or "model.scad"
    if not cleaned.lower().endswith(".scad"):
        cleaned = f"{cleaned}.scad"
    return cleaned


def _pick_directory_native(initial_dir: Optional[str] = None) -> Optional[str]:
    """Open a native directory picker dialog and return selected path."""
    # Prefer pywebview's native dialog when available; this matches the
    # host platform's file-picker look/scale better than Tk on HiDPI displays.
    try:
        import webview

        if getattr(webview, "windows", None):
            selected = webview.windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initial_dir or str(Path.home()),
            )
            if selected:
                return str(selected[0])
    except (ImportError, ModuleNotFoundError, AttributeError, RuntimeError, TypeError):
        pass

    # Fallback for non-native mode.
    try:
        import tkinter as tk
        from tkinter import filedialog
    except (ImportError, ModuleNotFoundError):
        return None

    root = tk.Tk()
    root.withdraw()
    # Scale Tk dialogs on HiDPI screens so the folder picker is readable.
    try:
        dpi = float(root.winfo_fpixels("1i"))
        root.tk.call("tk", "scaling", max(dpi / 72.0, 1.5))
    except (tk.TclError, ValueError):
        root.tk.call("tk", "scaling", 1.5)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    try:
        chosen = filedialog.askdirectory(
            initialdir=initial_dir or str(Path.home()),
            title="Select project location",
        )
    finally:
        root.destroy()

    return chosen or None


# ──────────────────────────────────────────────────────────────────────────────
# Page layout
# ──────────────────────────────────────────────────────────────────────────────


@ui.page("/")
def index() -> None:
    global _3dm_path

    _3dm_path = find_3dm_binary()

    # ── Header ────────────────────────────────────────────────────────────────
    # ── Appearance state (font size + theme) ─────────────────────────────────
    _font_state = {"size": "medium"}  # "medium" | "large" | "xlarge"
    EDITOR_PX = {"medium": 14, "large": 17, "xlarge": 20}
    FONT_SIZES = [
        ("Medium", "medium"),
        ("Large", "large"),
        ("X-Large", "xlarge"),
    ]
    # font radio buttons wired after the drawer is built
    _font_radio: list = [None]

    def _apply_font_size(size: str) -> None:
        """Toggle body font class and resize CodeMirror."""
        _font_state["size"] = size
        px = EDITOR_PX[size]
        ui.run_javascript(f"""
            const b = document.body;
            b.classList.remove('font-medium', 'font-large', 'font-xlarge');
            b.classList.add('font-{size}');
            const ed = document.querySelector('.cm-editor');
            if (ed) ed.style.fontSize = '{px}px';
        """)

    # ── Header ────────────────────────────────────────────────────────────────
    with ui.header().classes(
        "items-center justify-between bg-gray-900 text-white px-4 py-2"
    ):
        ui.label("3DMake GUI").classes("text-xl font-bold tracking-wide")

        if _3dm_path:
            ui.label(f"3dm: {_3dm_path}").classes("text-xs text-green-400 font-mono")
        else:
            ui.label("⚠ 3dm not found").classes("text-xs text-yellow-400")

        # ⚙ Settings button — opens the right drawer
        ui.button(icon="settings", on_click=lambda: settings_drawer.toggle()).props(
            "flat round color=white"
        ).tooltip("Appearance settings (theme & font size)")

    # ── Settings drawer (right side, opened by ⚙ button above) ───────────────
    # Declared here so the header button can reference it; content filled below
    # after THEMES is defined in the right-panel block.
    with (
        ui.right_drawer(value=False, fixed=True, elevated=True)
        .classes("q-pa-md")
        .style("width: 300px; overflow-y: auto;") as settings_drawer
    ):
        ui.label("⚙  Appearance").classes("text-lg font-bold mb-4")

        # ── Font size ─────────────────────────────────────────────────────────
        ui.label("Text Size").classes("text-sm font-semibold mb-1")
        ui.separator().classes("mb-2")

        font_radio = ui.radio(
            {sz: lbl for lbl, sz in FONT_SIZES},
            value="medium",
            on_change=lambda e: _apply_font_size(e.value),
        ).props("color=primary")
        _font_radio[0] = font_radio

        ui.separator().classes("my-4")

        # ── Theme picker placeholder label ────────────────────────────────────
        # The actual theme select is injected below after THEMES is defined,
        # because we need the right-panel scope.  We use a column container
        # as the mount point.
        ui.label("Editor & App Theme").classes("text-sm font-semibold mb-1")
        ui.separator().classes("mb-2")
        _theme_mount = ui.column().classes("w-full gap-1")

    # ── Layout constants (px) ─────────────────────────────────────────────────
    # Header and footer heights are set in the ui.header/footer calls above.
    # We hard-code the same values here so calc() can reference them.
    HDR = 48  # px  – matches py-3 on the header
    FTR = 32  # px  – matches py-2 on the footer
    GAP = 12  # px  – gap between cards
    PAD = 12  # px  – outer left/right/top padding
    # Fixed right-column heights (px):
    CMD_H = 104  # Custom Command card (default)
    LOG_H = 200  # Output Log card
    # Editor gets everything that's left:
    # BODY_H = 100dvh - HDR - FTR
    # EDITOR_H = BODY_H - CMD_H - LOG_H - 3*GAP - 2*PAD

    ui.add_head_html(f"""
    <style>
      /* ── reset NiceGUI defaults that cause scrollbars ── */
      html, body {{ overflow: hidden; height: 100%; }}
      .nicegui-content {{ padding: 0 !important; overflow: hidden !important; }}

      /* ── layout shell ── */
      .app-body {{
                --cmd-card-h: {CMD_H}px;
        display: flex;
        flex-direction: row;
                width: 100%;
                max-width: 100%;
        gap: {GAP}px;
        padding: {PAD}px;
        height: calc(100dvh - {HDR}px - {FTR}px);
        overflow: hidden;
        box-sizing: border-box;
      }}

      /* ── left panel: 25% width, scroll if content overflows ── */
            .left-panel {{
                width: 25%;
        min-width: 220px;
                max-width: 420px;
        display: flex;
        flex-direction: column;
        gap: {GAP}px;
        overflow-y: auto;
        overflow-x: hidden;
        flex-shrink: 0;
      }}

            /* X-Large mode gives the control column more room for larger labels */
            body.font-xlarge .left-panel {{
                width: 30%;
                --cmd-card-h: 126px;
            }}

      /* ── right panel: 75% width, all children stretch to full width ── */
      .right-panel {{
        width: 75%;
        flex: 1 1 0;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: {GAP}px;
        overflow: hidden;
        box-sizing: border-box;
      }}
            body.font-xlarge .right-panel {{
                width: 70%;
            }}
      /* Force every direct card child of right-panel to fill the full width */
      .right-panel > div,
      .right-panel > .q-card {{
        width: 100% !important;
        min-width: 0 !important;
        box-sizing: border-box;
      }}

      /* ── editor card: explicit height so codemirror has room ── */
      .editor-card {{
        overflow: hidden;
        display: flex;
        flex-direction: column;
        width: 100% !important;
        box-sizing: border-box;
        /* total right column height minus the two fixed cards and gaps */
                height: calc(100dvh - {HDR}px - {FTR}px - var(--cmd-card-h) - {LOG_H}px - {
        3 * GAP
    }px - {2 * PAD}px);
        min-height: 200px;
      }}
      /* codemirror sits directly inside the card; give it all remaining space */
      .editor-card .nicegui-codemirror {{
        flex: 1 1 0;
        min-height: 0;
        overflow: hidden;
      }}
      .editor-card .nicegui-codemirror .cm-editor {{
        height: 100% !important;
      }}

      /* ── log card: fixed height, inner log element fills it ── */
      .log-card {{
        height: {LOG_H}px;
        min-height: {LOG_H}px;
        max-height: {LOG_H}px;
        width: 100% !important;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }}
      .log-card .nicegui-log {{
        flex: 1 1 0;
        min-height: 0;
        overflow-y: auto;
      }}

      /* ── command card: fixed height ── */
      .cmd-card {{
                height: var(--cmd-card-h);
                min-height: var(--cmd-card-h);
                max-height: var(--cmd-card-h);
        width: 100% !important;
        box-sizing: border-box;
        overflow: hidden;
                padding: 12px 14px;
      }}
            .cmd-row {{
                flex-wrap: nowrap;
                align-items: stretch;
            }}
            .cmd-input .q-field__control {{
                min-height: 44px;
            }}
            body.font-xlarge .cmd-input .q-field__control {{
                min-height: 54px;
            }}
            .cmd-run-btn {{
                min-width: 88px;
            }}
            body.font-xlarge .cmd-run-btn {{
                min-width: 112px;
            }}
      /* ── font size tiers ── */
      /* Medium (default) — no class needed, these are the baseline values */
    body.font-medium {{font-size: 14px; }}
    body.font-large  {{font-size: 17px; }}
    body.font-xlarge {{font-size: 20px; }}

      /* Scale every text-bearing element that NiceGUI/Quasar renders */
      body.font-large  .q-field__label,
      body.font-large  .q-field__native,
      body.font-large  .q-field__prefix,
      body.font-large  .q-field__suffix,
      body.font-large  .q-btn__content,
      body.font-large  .q-item__label,
      body.font-large  .q-card,
      body.font-large  label,
      body.font-large  button,
    body.font-large  .nicegui-log {{font-size: 17px !important; }}

      body.font-xlarge .q-field__label,
      body.font-xlarge .q-field__native,
      body.font-xlarge .q-field__prefix,
      body.font-xlarge .q-field__suffix,
      body.font-xlarge .q-btn__content,
      body.font-xlarge .q-item__label,
      body.font-xlarge .q-card,
      body.font-xlarge label,
      body.font-xlarge button,
    body.font-xlarge .nicegui-log {{font-size: 20px !important; }}

      /* CodeMirror editor font — targeted separately via inline style from JS */

      /* ── runtime CSS variables set by _apply_site_theme() ── */
            :root {{
                --site-bg:      #282a36;   /* Dracula defaults */
        --site-surface: #44475a;
        --site-text:    #f8f8f2;
            }}
      /* Apply surface colour to all cards */
            .q-card {{
                background-color: var(--site-surface) !important;
        color: var(--site-text) !important;
            }}
      /* Apply bg colour to page body */
      body.body--dark,
            body.body--light {{
                background-color: var(--site-bg) !important;
            }}
    </style>
    """)

    # ── Two-column body ────────────────────────────────────────────────────────
    with ui.row().classes("app-body"):
        # ── LEFT PANEL ────────────────────────────────────────────────────────
        with ui.column().classes("left-panel"):
            # 1. Project / File ────────────────────────────────────────────────
            with (
                ui.card()
                .classes("w-full")
                .props('id="section-file" aria-label="Project and file selection"')
            ):
                ui.label("Project / File").classes("text-base font-semibold mb-1")

                file_input = ui.input(
                    label="File or project directory",
                    placeholder="/home/user/model/src/model.scad",
                ).classes("w-full text-sm")

                _editor_path_label_ref: list[Optional[ui.label]] = [None]

                def _update_editor_filepath(path_value: Optional[str] = None) -> None:
                    value = (path_value if path_value is not None else file_input.value)
                    text = value.strip() if value else ""
                    display = text if text else "No Project Slected"
                    if _editor_path_label_ref[0] is not None:
                        _editor_path_label_ref[0].set_text(f"Filepath: {display}")

                file_input.on_value_change(lambda e: _update_editor_filepath(e.value))

                # handle_upload fires when the user picks a file via the upload
                # widget (either Browse… or drag-and-drop).
                def handle_upload(e):
                    # Prefer the full temp path exposed on newer NiceGUI versions;
                    # fall back to just the filename so the field always updates.
                    resolved = (
                        getattr(getattr(e, "content", None), "name", None) or e.name
                    )
                    file_input.set_value(resolved)
                    _update_editor_filepath(resolved)
                    ui.notify(f"Selected: {e.name}", type="positive")

                file_upload = (
                    ui.upload(
                        label="Drop a .scad / .stl here",
                        on_upload=handle_upload,
                        max_file_size=50_000_000,
                    )
                    .props("accept=.scad,.stl,.3mf flat")
                    .classes("w-full mt-2")
                )

                # Browse… programmatically clicks the hidden <input type=file>
                # that Quasar renders inside the upload widget.
                ui.button(
                    "Browse…",
                    on_click=lambda: ui.run_javascript(
                        "document.querySelector('.q-uploader input[type=file]').click()"
                    ),
                ).props("outline size=sm").classes("w-full mt-1")

            # 2. Quick Actions ─────────────────────────────────────────────────
            with (
                ui.card()
                .classes("w-full")
                .props('id="section-quick" aria-label="Quick actions"')
            ):
                ui.label("Quick Actions").classes("text-base font-semibold mb-1")
                ui.label("Runs against the file path above.").classes(
                    "text-xs text-gray-500 mb-2"
                )

                output_log: ui.log  # forward-declared; assigned in right panel below

                quick_cmds = [
                    ("Describe", "3dm describe {file}", "Describe shape with AI"),
                    ("Render STL", "3dm render {file}", "Render .scad → .stl"),
                    ("Slice", "3dm slice {file}", "Slice .stl for printing"),
                    ("Orient", "3dm orient {file}", "Auto-orient for printing"),
                    ("Preview", "3dm preview {file}", "Generate 2-D tactile preview"),
                    ("New Project", "3dm new", "Scaffold a new 3dmake project"),
                ]

                with ui.grid(columns=2).classes("w-full gap-2"):
                    for btn_label, cmd_tpl, tip in quick_cmds:

                        def _make_handler(tpl=cmd_tpl):
                            async def handler():
                                path = file_input.value.strip()
                                if not path and "{file}" in tpl:
                                    ui.notify(
                                        "Enter a file path first.", type="warning"
                                    )
                                    return
                                cmd = tpl.replace("{file}", f'"{path}"')
                                if _3dm_path:
                                    cmd = cmd.replace("3dm ", f'"{_3dm_path}" ', 1)
                                await _stream_command(cmd, output_log)

                            return handler

                        ui.button(btn_label, on_click=_make_handler()).tooltip(
                            tip
                        ).props("size=sm").classes("w-full")

            # ── Settings card ─────────────────────────────────────────────────
            with (
                ui.card()
                .classes("w-full")
                .props('id="section-settings" aria-label="Settings"')
            ):
                ui.label("Settings").classes("text-base font-semibold mb-1")

                # Global config (defaults.toml) — load into editor
                async def open_global_config():
                    # Match 3dm's own config-dir resolution:
                    # THREEDMAKE_CONFIG_DIR override, otherwise OS-specific
                    # user config dir (Linux ~/.config/3dmake, etc.).
                    cfg = get_3dmake_defaults_toml_path()
                    if cfg.exists():
                        try:
                            content = cfg.read_text(encoding="utf-8")
                            editor.set_value(content)
                            file_input.set_value(str(cfg))
                            _update_editor_filepath(str(cfg))
                            ui.notify(f"Loaded global config: {cfg}", type="positive")
                        except OSError as exc:
                            ui.notify(f"Could not read {cfg}: {exc}", type="negative")
                    else:
                        ui.notify(
                            f"defaults.toml not found at {cfg}. "
                            "Run '3dm edit-global-config' once to create it. "
                            "Profiles and overlays live in sibling folders under "
                            "the same config directory.",
                            type="warning",
                        )

                # Project config (3dmake.toml) — load into editor
                async def open_project_config():
                    path = file_input.value.strip()
                    if not path:
                        ui.notify("Set a project path first.", type="warning")
                        return
                    # Walk up from file_input path to find 3dmake.toml
                    search = Path(path)
                    if search.is_file():
                        search = search.parent
                    cfg = None
                    for candidate in [search, *search.parents]:
                        t = candidate / "3dmake.toml"
                        if t.exists():
                            cfg = t
                            break
                    if cfg:
                        try:
                            content = cfg.read_text(encoding="utf-8")
                            editor.set_value(content)
                            file_input.set_value(str(cfg))
                            _update_editor_filepath(str(cfg))
                            ui.notify(f"Loaded project config: {cfg}", type="positive")
                        except OSError as exc:
                            ui.notify(f"Could not read {cfg}: {exc}", type="negative")
                    else:
                        ui.notify(
                            "No 3dmake.toml found in this directory or any parent. "
                            "Run '3dm new' to create a project first.",
                            type="warning",
                        )

                # 3dm path override dialog
                def open_path_dialog():
                    with ui.dialog() as dlg, ui.card().classes("w-96"):
                        ui.label("Set 3dm Binary Path").classes(
                            "text-base font-semibold mb-2"
                        )
                        ui.label(
                            "Override the path to the 3dm binary file or folder. "
                            "This sets the THREE_DM_PATH environment variable "
                            "for this session."
                        ).classes("text-xs text-gray-500 mb-3")
                        path_field = ui.input(
                            label="Path to 3dm binary or folder",
                            value=_3dm_path or "",
                            placeholder="~/Applications/3dmake  or  /usr/local/bin/3dm",
                        ).classes("w-full")

                        def apply_path():
                            import os

                            new_path = path_field.value.strip()
                            resolved_path = resolve_3dm_binary_path(new_path)
                            if resolved_path:
                                os.environ["THREE_DM_PATH"] = resolved_path
                                global _3dm_path
                                _3dm_path = resolved_path
                                ui.notify(
                                    f"3dm path set to: {resolved_path}",
                                    type="positive",
                                )
                                dlg.close()
                            else:
                                ui.notify(
                                    "No 3dm binary found at that path. "
                                    "You can provide either the binary file path "
                                    "or a folder that contains 3dm.",
                                    type="negative",
                                )

                        with ui.row().classes("gap-2 mt-2"):
                            ui.button("Apply", on_click=apply_path).props(
                                "color=primary size=sm"
                            )
                            ui.button("Cancel", on_click=dlg.close).props(
                                "flat size=sm"
                            )
                    dlg.open()

                with ui.grid(columns=2).classes("w-full gap-2"):
                    ui.button("Global Config", on_click=open_global_config).tooltip(
                        "Load defaults.toml into the editor"
                    ).props("size=sm").classes("w-full")
                    ui.button("Project Config", on_click=open_project_config).tooltip(
                        "Load this project's 3dmake.toml into the editor"
                    ).props("size=sm").classes("w-full")
                    ui.button("Set 3dm Path", on_click=open_path_dialog).tooltip(
                        "Override the path to the 3dm binary"
                    ).props("size=sm").classes("w-full")
                    ui.button("List Libraries", on_click=lambda: None).tooltip(
                        "Run 3dm list-libraries"
                    ).props("size=sm").classes("w-full").on(
                        "click",
                        lambda: asyncio.create_task(
                            _stream_command(
                                f'"{_3dm_path}" list-libraries'
                                if _3dm_path
                                else "3dm list-libraries",
                                output_log,
                            )
                        ),
                    )

        # ── RIGHT PANEL ───────────────────────────────────────────────────────
        with ui.column().classes("right-panel"):
            # ── Theme definitions ────────────────────────────────────────────
            # Each entry: (display label, codemirror theme id, is_dark, site palette)
            # Site palette keys map to ui.colors() / ui.dark_mode() parameters.
            # Colors are extracted from each theme's published spec so the UI chrome
            # (cards, inputs, header, buttons) matches the editor visually.
            THEMES: list[tuple[str, str, bool, dict]] = [
                # ── Dark / cozy ───────────────────────────────────────────────
                (
                    "Tokyo Night",
                    "tokyoNight",
                    True,
                    {
                        "primary": "#7aa2f7",
                        "secondary": "#bb9af7",
                        "bg": "#1a1b26",
                        "surface": "#24283b",
                        "text": "#c0caf5",
                    },
                ),
                (
                    "Tokyo Night Storm",
                    "tokyoNightStorm",
                    True,
                    {
                        "primary": "#7aa2f7",
                        "secondary": "#bb9af7",
                        "bg": "#24283b",
                        "surface": "#2f3549",
                        "text": "#c0caf5",
                    },
                ),
                (
                    "One Dark",
                    "oneDark",
                    True,
                    {
                        "primary": "#61afef",
                        "secondary": "#c678dd",
                        "bg": "#282c34",
                        "surface": "#2c313a",
                        "text": "#abb2bf",
                    },
                ),
                (
                    "Aura",
                    "aura",
                    True,
                    {
                        "primary": "#a277ff",
                        "secondary": "#61ffca",
                        "bg": "#15141b",
                        "surface": "#1c1a27",
                        "text": "#edecee",
                    },
                ),
                (
                    "Andromeda",
                    "andromeda",
                    True,
                    {
                        "primary": "#00e8c6",
                        "secondary": "#e9a66c",
                        "bg": "#23262e",
                        "surface": "#292d35",
                        "text": "#d5ced9",
                    },
                ),
                (
                    "Nord",
                    "nord",
                    True,
                    {
                        "primary": "#88c0d0",
                        "secondary": "#81a1c1",
                        "bg": "#2e3440",
                        "surface": "#3b4252",
                        "text": "#eceff4",
                    },
                ),
                (
                    "Dracula",
                    "dracula",
                    True,
                    {
                        "primary": "#bd93f9",
                        "secondary": "#ff79c6",
                        "bg": "#282a36",
                        "surface": "#44475a",
                        "text": "#f8f8f2",
                    },
                ),
                (
                    "Monokai",
                    "monokai",
                    True,
                    {
                        "primary": "#a6e22e",
                        "secondary": "#66d9e8",
                        "bg": "#272822",
                        "surface": "#3e3d32",
                        "text": "#f8f8f2",
                    },
                ),
                (
                    "Monokai Dimmed",
                    "monokaiDimmed",
                    True,
                    {
                        "primary": "#9fca56",
                        "secondary": "#55b5db",
                        "bg": "#1e1e1e",
                        "surface": "#2a2a2a",
                        "text": "#d4d4d4",
                    },
                ),
                (
                    "Gruvbox Dark",
                    "gruvboxDark",
                    True,
                    {
                        "primary": "#b8bb26",
                        "secondary": "#fabd2f",
                        "bg": "#282828",
                        "surface": "#3c3836",
                        "text": "#ebdbb2",
                    },
                ),
                (
                    "Atom One",
                    "atomone",
                    True,
                    {
                        "primary": "#61afef",
                        "secondary": "#c678dd",
                        "bg": "#1e2127",
                        "surface": "#282c34",
                        "text": "#abb2bf",
                    },
                ),
                (
                    "VS Code Dark",
                    "vscodeDark",
                    True,
                    {
                        "primary": "#569cd6",
                        "secondary": "#c586c0",
                        "bg": "#1e1e1e",
                        "surface": "#252526",
                        "text": "#d4d4d4",
                    },
                ),
                (
                    "Solarized Dark",
                    "solarizedDark",
                    True,
                    {
                        "primary": "#268bd2",
                        "secondary": "#2aa198",
                        "bg": "#002b36",
                        "surface": "#073642",
                        "text": "#839496",
                    },
                ),
                (
                    "GitHub Dark",
                    "githubDark",
                    True,
                    {
                        "primary": "#58a6ff",
                        "secondary": "#bc8cff",
                        "bg": "#0d1117",
                        "surface": "#161b22",
                        "text": "#e6edf3",
                    },
                ),
                (
                    "Xcode Dark",
                    "xcodeDark",
                    True,
                    {
                        "primary": "#4eb0cc",
                        "secondary": "#ff8170",
                        "bg": "#1c1c1e",
                        "surface": "#2c2c2e",
                        "text": "#ffffff",
                    },
                ),
                # ── Dark / high contrast ──────────────────────────────────────
                (
                    "Abyss",
                    "abyss",
                    True,
                    {
                        "primary": "#6688cc",
                        "secondary": "#ddbb88",
                        "bg": "#000c18",
                        "surface": "#051221",
                        "text": "#6688cc",
                    },
                ),
                (
                    "Tomorrow Night",
                    "tomorrowNightBlue",
                    True,
                    {
                        "primary": "#7285b7",
                        "secondary": "#9854fb",
                        "bg": "#002451",
                        "surface": "#00346e",
                        "text": "#ffffff",
                    },
                ),
                (
                    "Sublime",
                    "sublime",
                    True,
                    {
                        "primary": "#66d9e8",
                        "secondary": "#a6e22e",
                        "bg": "#272822",
                        "surface": "#383830",
                        "text": "#f8f8f2",
                    },
                ),
                (
                    "Darcula",
                    "darcula",
                    True,
                    {
                        "primary": "#cc7832",
                        "secondary": "#6897bb",
                        "bg": "#2b2b2b",
                        "surface": "#3c3f41",
                        "text": "#a9b7c6",
                    },
                ),
                (
                    "Okaidia",
                    "okaidia",
                    True,
                    {
                        "primary": "#a6e22e",
                        "secondary": "#66d9e8",
                        "bg": "#272822",
                        "surface": "#383830",
                        "text": "#f8f8f2",
                    },
                ),
                (
                    "Android Studio",
                    "androidstudio",
                    True,
                    {
                        "primary": "#629755",
                        "secondary": "#6897bb",
                        "bg": "#282b2e",
                        "surface": "#313335",
                        "text": "#a9b7c6",
                    },
                ),
                (
                    "Copilot",
                    "copilot",
                    True,
                    {
                        "primary": "#79c0ff",
                        "secondary": "#d2a8ff",
                        "bg": "#0d1117",
                        "surface": "#161b22",
                        "text": "#e6edf3",
                    },
                ),
                (
                    "Kimbie",
                    "kimbie",
                    True,
                    {
                        "primary": "#dc3958",
                        "secondary": "#f79a32",
                        "bg": "#221a0f",
                        "surface": "#362712",
                        "text": "#d3af86",
                    },
                ),
                (
                    "Bespin",
                    "bespin",
                    True,
                    {
                        "primary": "#9d7a4a",
                        "secondary": "#cf6a4c",
                        "bg": "#28211c",
                        "surface": "#36312c",
                        "text": "#9d9b97",
                    },
                ),
                (
                    "ABCDEF",
                    "abcdef",
                    True,
                    {
                        "primary": "#6767ff",
                        "secondary": "#ff6767",
                        "bg": "#0f0f0f",
                        "surface": "#1a1a1a",
                        "text": "#defdef",
                    },
                ),
                (
                    "Duotone Dark",
                    "duotoneDark",
                    True,
                    {
                        "primary": "#9a86fd",
                        "secondary": "#7a63ee",
                        "bg": "#2b2a3b",
                        "surface": "#35334a",
                        "text": "#b9b6c1",
                    },
                ),
                # ── Light / soft ─────────────────────────────────────────────
                (
                    "Tokyo Night Day",
                    "tokyoNightDay",
                    False,
                    {
                        "primary": "#2e7de9",
                        "secondary": "#9854fb",
                        "bg": "#e1e2e7",
                        "surface": "#d0d5e3",
                        "text": "#3760bf",
                    },
                ),
                (
                    "GitHub Light",
                    "githubLight",
                    False,
                    {
                        "primary": "#0969da",
                        "secondary": "#8250df",
                        "bg": "#ffffff",
                        "surface": "#f6f8fa",
                        "text": "#24292f",
                    },
                ),
                (
                    "Quiet Light",
                    "quietlight",
                    False,
                    {
                        "primary": "#6c71c4",
                        "secondary": "#2aa198",
                        "bg": "#f5f5f5",
                        "surface": "#eaeaea",
                        "text": "#333333",
                    },
                ),
                (
                    "Noctis Lilac",
                    "noctisLilac",
                    False,
                    {
                        "primary": "#4d9e93",
                        "secondary": "#b069d4",
                        "bg": "#f2f1f8",
                        "surface": "#e8e7f2",
                        "text": "#0c006b",
                    },
                ),
                (
                    "Duotone Light",
                    "duotoneLight",
                    False,
                    {
                        "primary": "#b29762",
                        "secondary": "#063289",
                        "bg": "#faf8f5",
                        "surface": "#ede8d5",
                        "text": "#696c77",
                    },
                ),
                (
                    "Solarized Light",
                    "solarizedLight",
                    False,
                    {
                        "primary": "#268bd2",
                        "secondary": "#2aa198",
                        "bg": "#fdf6e3",
                        "surface": "#eee8d5",
                        "text": "#657b83",
                    },
                ),
                (
                    "Material Light",
                    "materialLight",
                    False,
                    {
                        "primary": "#80cbc4",
                        "secondary": "#c792ea",
                        "bg": "#fafafa",
                        "surface": "#e7eaec",
                        "text": "#546e7a",
                    },
                ),
                (
                    "Gruvbox Light",
                    "gruvboxLight",
                    False,
                    {
                        "primary": "#79740e",
                        "secondary": "#b57614",
                        "bg": "#f9f5d7",
                        "surface": "#ebdbb2",
                        "text": "#3c3836",
                    },
                ),
                (
                    "Xcode Light",
                    "xcodeLight",
                    False,
                    {
                        "primary": "#0f68a2",
                        "secondary": "#ad3da4",
                        "bg": "#ffffff",
                        "surface": "#f2f2f7",
                        "text": "#000000",
                    },
                ),
                (
                    "VS Code Light",
                    "vscodeLight",
                    False,
                    {
                        "primary": "#0070c1",
                        "secondary": "#af00db",
                        "bg": "#ffffff",
                        "surface": "#f3f3f3",
                        "text": "#000000",
                    },
                ),
                (
                    "GitHub Dark",
                    "githubDark",
                    True,
                    {
                        "primary": "#58a6ff",
                        "secondary": "#bc8cff",
                        "bg": "#0d1117",
                        "surface": "#161b22",
                        "text": "#e6edf3",
                    },
                ),
                (
                    "BBEdit",
                    "bbedit",
                    False,
                    {
                        "primary": "#005aff",
                        "secondary": "#aa0000",
                        "bg": "#ffffff",
                        "surface": "#f0f0f0",
                        "text": "#000000",
                    },
                ),
                (
                    "Eclipse",
                    "eclipse",
                    False,
                    {
                        "primary": "#7f0055",
                        "secondary": "#0000c0",
                        "bg": "#ffffff",
                        "surface": "#f5f5f5",
                        "text": "#000000",
                    },
                ),
                # ── Neutral ───────────────────────────────────────────────────
                (
                    "Basic Light",
                    "basicLight",
                    False,
                    {
                        "primary": "#4c8bf5",
                        "secondary": "#9c27b0",
                        "bg": "#ffffff",
                        "surface": "#f5f5f5",
                        "text": "#333333",
                    },
                ),
                (
                    "Basic Dark",
                    "basicDark",
                    True,
                    {
                        "primary": "#4c8bf5",
                        "secondary": "#9c27b0",
                        "bg": "#1a1a1a",
                        "surface": "#2a2a2a",
                        "text": "#e0e0e0",
                    },
                ),
                (
                    "White Light",
                    "whiteLight",
                    False,
                    {
                        "primary": "#1976d2",
                        "secondary": "#7b1fa2",
                        "bg": "#ffffff",
                        "surface": "#f5f5f5",
                        "text": "#212121",
                    },
                ),
                (
                    "White Dark",
                    "whiteDark",
                    True,
                    {
                        "primary": "#90caf9",
                        "secondary": "#ce93d8",
                        "bg": "#121212",
                        "surface": "#1e1e1e",
                        "text": "#e0e0e0",
                    },
                ),
                (
                    "Console Light",
                    "consoleLight",
                    False,
                    {
                        "primary": "#007700",
                        "secondary": "#0000aa",
                        "bg": "#ffffff",
                        "surface": "#f0f0f0",
                        "text": "#111111",
                    },
                ),
                (
                    "Console Dark",
                    "consoleDark",
                    True,
                    {
                        "primary": "#00ff00",
                        "secondary": "#00aaff",
                        "bg": "#000000",
                        "surface": "#0a0a0a",
                        "text": "#00ff00",
                    },
                ),
                (
                    "Material",
                    "material",
                    True,
                    {
                        "primary": "#80cbc4",
                        "secondary": "#c792ea",
                        "bg": "#263238",
                        "surface": "#2e3c43",
                        "text": "#eeffff",
                    },
                ),
            ]

            # Build lookup dicts
            _theme_options = {label: tid for label, tid, *_ in THEMES}
            _theme_is_dark = {label: dark for label, _, dark, *_ in THEMES}
            _theme_palette = {label: pal for label, _, _2, pal in THEMES}

            _DEFAULT_THEME_LABEL = "Dracula"
            _DEFAULT_THEME = _theme_options[_DEFAULT_THEME_LABEL]

            # dark_mode element — lets us toggle Quasar dark mode at runtime
            dark_mode = ui.dark_mode(value=True)

            def _apply_site_theme(label: str) -> None:
                """Drive ui.dark_mode + ui.colors to match the chosen editor theme."""
                pal = _theme_palette[label]
                dark_mode.value = _theme_is_dark[label]
                ui.colors(
                    primary=pal["primary"],
                    secondary=pal["secondary"],
                    dark=pal["bg"],
                    dark_page=pal["bg"],
                )
                # Inject CSS variables so non-Quasar elements (cards, log, header)
                # also recolor — we patch the card backgrounds via a runtime style tag.
                ui.run_javascript(f"""
                    document.documentElement.style.setProperty('--site-bg',      '{pal["bg"]}');
                    document.documentElement.style.setProperty('--site-surface', '{pal["surface"]}');
                    document.documentElement.style.setProperty('--site-text',    '{pal["text"]}');
                """)

            # Apply default palette immediately on page load
            _apply_site_theme(_DEFAULT_THEME_LABEL)

            def _detect_language(path: str) -> str | None:
                """Return the codemirror language string for .toml and .scad files."""
                suffix = Path(path).suffix.lower()
                if suffix == ".toml":
                    return "TOML"
                # OpenSCAD is not in codemirror's language list; use C++ as the
                # closest approximation (shares most syntax: {}, //, /* */, numbers)
                if suffix == ".scad":
                    return "C++"
                return None  # leave language unchanged for other file types

            # 3. Editor card ───────────────────────────────────────────────────
            with (
                ui.card()
                .classes("editor-card")
                .props('id="section-editor" aria-label="Model editor"')
            ):
                with (
                    ui.row()
                    .classes("w-full items-center justify-between")
                    .style("flex-shrink: 0; margin-bottom: 6px;")
                ):
                    with ui.row().classes("items-center gap-3"):
                        ui.label("Model Editor").classes("text-base font-semibold")
                        _editor_path_label_ref[0] = ui.label(
                            "Filepath: No Project Slected"
                        ).classes("text-xs text-gray-400 font-mono")
                    with ui.row().classes("gap-2 items-center"):

                        async def load_into_editor():
                            path = file_input.value.strip()
                            if not path:
                                ui.notify("Set a file path first.", type="warning")
                                return
                            try:
                                content = Path(path).read_text(encoding="utf-8")
                                editor.set_value(content)
                                lang = _detect_language(path)
                                if lang:
                                    editor.set_language(lang)
                                ui.notify(f"Loaded {path}", type="positive")
                            except OSError as exc:
                                ui.notify(f"Could not load: {exc}", type="negative")

                        async def _browse_to_input(target: ui.input) -> None:
                            selected = _pick_directory_native(
                                target.value.strip() or str(Path.home())
                            )
                            if selected:
                                target.set_value(selected)
                            else:
                                ui.notify(
                                    "No folder selected. You can also type a path manually.",
                                    type="warning",
                                )

                        async def _save_to_project(
                            project_root: Path,
                            scad_name: str,
                            notify_prefix: str,
                        ) -> None:
                            _ensure_project_layout(project_root, project_root.name)
                            target = project_root / "src" / _normalize_scad_filename(scad_name)
                            target.write_text(editor.value, encoding="utf-8")
                            file_input.set_value(str(target))
                            _update_editor_filepath(str(target))
                            ui.notify(f"{notify_prefix}: {target}", type="positive")

                        def _open_new_project_dialog(parent_dialog: ui.dialog) -> None:
                            with ui.dialog() as dlg, ui.card().classes("w-[34rem]"):
                                ui.label("Create New Project").classes(
                                    "text-base font-semibold"
                                )
                                ui.label(
                                    "Choose where to create the project. The app will "
                                    "create build/, src/, and 3dmake.toml."
                                ).classes("text-xs text-gray-500")

                                location_input = ui.input(
                                    label="Parent folder",
                                    value=str(Path.home()),
                                    placeholder="/home/user/projects",
                                ).classes("w-full")
                                ui.button(
                                    "Browse…",
                                    on_click=lambda: asyncio.create_task(
                                        _browse_to_input(location_input)
                                    ),
                                ).props("outline size=sm")

                                project_name_input = ui.input(
                                    label="Project name",
                                    placeholder="my-model-project",
                                ).classes("w-full")
                                filename_input = ui.input(
                                    label="SCAD file name",
                                    value="model.scad",
                                    placeholder="model.scad",
                                ).classes("w-full")

                                async def create_and_save() -> None:
                                    parent = location_input.value.strip()
                                    project_name = project_name_input.value.strip()
                                    if not parent or not project_name:
                                        ui.notify(
                                            "Provide both project location and project name.",
                                            type="warning",
                                        )
                                        return
                                    root = Path(parent).expanduser() / project_name
                                    try:
                                        await _save_to_project(
                                            root,
                                            filename_input.value,
                                            "Project created and saved",
                                        )
                                        dlg.close()
                                        parent_dialog.close()
                                    except OSError as exc:
                                        ui.notify(
                                            f"Could not create project: {exc}",
                                            type="negative",
                                        )

                                with ui.row().classes("gap-2 mt-2"):
                                    ui.button("Create & Save", on_click=create_and_save).props(
                                        "color=primary size=sm"
                                    )
                                    ui.button("Cancel", on_click=dlg.close).props(
                                        "flat size=sm"
                                    )
                            dlg.open()

                        def _open_existing_project_dialog(parent_dialog: ui.dialog) -> None:
                            with ui.dialog() as dlg, ui.card().classes("w-[34rem]"):
                                ui.label("Use Existing Project").classes(
                                    "text-base font-semibold"
                                )
                                ui.label(
                                    "Select an existing project folder. Missing build/, "
                                    "src/, or 3dmake.toml will be created automatically."
                                ).classes("text-xs text-gray-500")

                                existing_input = ui.input(
                                    label="Project folder",
                                    placeholder="/home/user/projects/my-model-project",
                                ).classes("w-full")
                                ui.button(
                                    "Select Existing…",
                                    on_click=lambda: asyncio.create_task(
                                        _browse_to_input(existing_input)
                                    ),
                                ).props("outline size=sm")

                                default_name = "model.scad"
                                current_value = file_input.value.strip()
                                if current_value:
                                    current_name = Path(current_value).name
                                    if current_name.lower().endswith(".scad"):
                                        default_name = current_name

                                filename_input = ui.input(
                                    label="SCAD file name",
                                    value=default_name,
                                    placeholder="model.scad",
                                ).classes("w-full")

                                async def use_existing_and_save() -> None:
                                    root_raw = existing_input.value.strip()
                                    if not root_raw:
                                        ui.notify(
                                            "Select an existing project folder first.",
                                            type="warning",
                                        )
                                        return
                                    root = Path(root_raw).expanduser()
                                    if not root.exists():
                                        ui.notify(
                                            "Selected project folder does not exist.",
                                            type="negative",
                                        )
                                        return
                                    if not root.is_dir():
                                        ui.notify(
                                            "Selected path is not a folder.",
                                            type="negative",
                                        )
                                        return
                                    try:
                                        await _save_to_project(
                                            root,
                                            filename_input.value,
                                            "Saved to project",
                                        )
                                        dlg.close()
                                        parent_dialog.close()
                                    except OSError as exc:
                                        ui.notify(
                                            f"Could not save to project: {exc}",
                                            type="negative",
                                        )

                                with ui.row().classes("gap-2 mt-2"):
                                    ui.button(
                                        "Use Existing & Save",
                                        on_click=use_existing_and_save,
                                    ).props("color=primary size=sm")
                                    ui.button("Cancel", on_click=dlg.close).props(
                                        "flat size=sm"
                                    )
                            dlg.open()

                        def _open_first_save_prompt() -> None:
                            with ui.dialog() as dlg, ui.card().classes("w-[28rem]"):
                                ui.label("Save Into a 3dmake Project").classes(
                                    "text-base font-semibold"
                                )
                                ui.label(
                                    "No loaded project was detected. Choose New Project "
                                    "or Select Existing before saving."
                                ).classes("text-xs text-gray-500")

                                with ui.row().classes("gap-2 mt-2"):
                                    ui.button(
                                        "New Project",
                                        on_click=lambda: _open_new_project_dialog(dlg),
                                    ).props("color=primary size=sm")
                                    ui.button(
                                        "Select Existing",
                                        on_click=lambda: _open_existing_project_dialog(
                                            dlg
                                        ),
                                    ).props("outline size=sm")
                                    ui.button("Cancel", on_click=dlg.close).props(
                                        "flat size=sm"
                                    )
                            dlg.open()

                        async def save_editor():
                            path = file_input.value.strip()
                            if path:
                                target_path = Path(path).expanduser()
                                # Config and other already-addressed files should save
                                # directly without forcing project assignment.
                                if target_path.suffix.lower() == ".toml" or (
                                    target_path.exists() and target_path.is_file()
                                ):
                                    try:
                                        if target_path.suffix.lower() == ".toml":
                                            target_path.parent.mkdir(
                                                parents=True,
                                                exist_ok=True,
                                            )
                                        target_path.write_text(
                                            editor.value,
                                            encoding="utf-8",
                                        )
                                        file_input.set_value(str(target_path))
                                        _update_editor_filepath(str(target_path))
                                        ui.notify(
                                            f"Saved to {target_path}",
                                            type="positive",
                                        )
                                    except OSError as exc:
                                        ui.notify(f"Save failed: {exc}", type="negative")
                                    return

                            project_root = _find_project_root(path) if path else None

                            if project_root and path.lower().endswith(".scad"):
                                try:
                                    Path(path).write_text(editor.value, encoding="utf-8")
                                    ui.notify(f"Saved to {path}", type="positive")
                                except OSError as exc:
                                    ui.notify(f"Save failed: {exc}", type="negative")
                                return

                            if project_root:
                                target = project_root / "src" / "model.scad"
                                try:
                                    _ensure_project_layout(project_root, project_root.name)
                                    target.write_text(editor.value, encoding="utf-8")
                                    file_input.set_value(str(target))
                                    _update_editor_filepath(str(target))
                                    ui.notify(f"Saved to {target}", type="positive")
                                except OSError as exc:
                                    ui.notify(f"Save failed: {exc}", type="negative")
                                return

                            _open_first_save_prompt()

                        ui.button("📂 Load", on_click=load_into_editor).props(
                            "flat size=sm"
                        )
                        ui.button("💾 Save", on_click=save_editor).props(
                            "outline size=sm"
                        )

                editor = ui.codemirror(
                    value="// Edit your OpenSCAD model here\n\ncube([10, 10, 10]);\n",
                    language="C++",
                    theme=_DEFAULT_THEME,
                ).classes("w-full font-mono text-sm")

            # ── Wire theme select into the settings drawer ────────────────────
            # Now that THEMES, _theme_options, and editor all exist, we can
            # populate the _theme_mount container inside the drawer.
            with _theme_mount:
                theme_select = (
                    ui.select(
                        options=_theme_options,
                        value=_DEFAULT_THEME_LABEL,
                        label="Theme",
                    )
                    .props("outlined options-dense")
                    .classes("w-full")
                )

                def _on_theme_change(e):
                    editor.set_theme(_theme_options[e.value])
                    _apply_site_theme(e.value)

                theme_select.on_value_change(_on_theme_change)

                # Small colour swatches so users can preview before selecting
                ui.label("Current theme preview:").classes("text-xs text-gray-400 mt-2")
                with ui.row().classes("gap-1 flex-wrap mt-1") as _swatch_row:
                    pass  # swatches injected by JS below

            # Apply default palette + render swatches on load
            _apply_site_theme(_DEFAULT_THEME_LABEL)
            # Build preview swatches via JS after DOM settles
            _swatch_js = ";".join(
                [
                    f"(function(){{var s=document.createElement('span');"
                    f"s.title='{lbl}';"
                    f"s.style.cssText='display:inline-block;width:16px;height:16px;"
                    f"border-radius:3px;background:{pal['primary']};border:1px solid {pal['surface']};cursor:pointer;';"
                    f"s.setAttribute('data-theme-label','{lbl}');"
                    f"document.querySelector('.swatch-row')&&document.querySelector('.swatch-row').appendChild(s)}})()"
                    for lbl, _, _, pal in THEMES
                ]
            )

            # 4. Custom Command card ───────────────────────────────────────────
            with (
                ui.card()
                .classes("cmd-card")
                .props('id="section-cmd" aria-label="Custom command"')
            ):
                ui.label("Custom Command").classes("text-base font-semibold mb-1")
                with ui.row().classes("w-full gap-2 items-end cmd-row"):
                    command_input = ui.input(
                        label="3dm command",
                        placeholder="3dm new  |  3dm setup  |  3dm lib install some-lib",
                    ).classes("flex-1 text-sm cmd-input")

                    async def execute_custom():
                        cmd = command_input.value.strip()
                        if not cmd:
                            ui.notify("Enter a command first.", type="warning")
                            return
                        if _3dm_path and cmd.startswith("3dm "):
                            cmd = cmd.replace("3dm ", f'"{_3dm_path}" ', 1)
                        await _stream_command(cmd, output_log)

                    ui.button("Run", on_click=execute_custom).props(
                        "color=primary size=sm"
                    ).classes("cmd-run-btn")

            # 5. Output Log card ───────────────────────────────────────────────
            with (
                ui.card()
                .classes("log-card")
                .props('id="section-log" aria-label="Output log"')
            ):
                with (
                    ui.row()
                    .classes("w-full items-center justify-between")
                    .style("flex-shrink: 0; margin-bottom: 4px;")
                ):
                    ui.label("Output Log").classes("text-base font-semibold")
                    ui.button("Clear", on_click=lambda: output_log.clear()).props(
                        "flat size=sm"
                    )

                output_log = ui.log(max_lines=500).classes("w-full font-mono text-xs")
                if _3dm_path:
                    output_log.push(f"[info] 3dm binary found at: {_3dm_path}")
                else:
                    output_log.push(
                        "[warn] 3dm not found. Install from https://github.com/tdeck/3dmake "
                        "then set THREE_DM_PATH or add to PATH."
                    )

    # ── Accessibility: keyboard shortcuts + help dialog ───────────────────────
    # All shortcut logic lives in a single JS block so screen readers and
    # keyboard-only users can operate every section without a mouse.
    # The help dialog is a plain <dialog> element so assistive technology
    # announces it correctly as a modal dialog with a proper heading.
    ui.add_body_html("""
<dialog id="a11y-help-dialog"
        aria-modal="true"
        aria-labelledby="a11y-help-title"
        style="
          max-width: 640px; width: 95vw;
          padding: 2rem; border-radius: 8px; border: none;
          background: var(--site-surface, #44475a);
          color: var(--site-text, #f8f8f2);
          box-shadow: 0 8px 32px rgba(0,0,0,.6);
        ">
  <h2 id="a11y-help-title" style="margin: 0 0 1rem; font-size: 1.25rem;">
    Keyboard Shortcuts &amp; Accessibility Help
  </h2>
  <table role="grid" style="width:100%; border-collapse:collapse; font-size:.95rem;">
    <thead>
      <tr>
        <th scope="col" style="text-align:left; padding:.4rem .6rem; border-bottom:1px solid #888;">Key</th>
        <th scope="col" style="text-align:left; padding:.4rem .6rem; border-bottom:1px solid #888;">Action</th>
      </tr>
    </thead>
    <tbody>
      <tr><td style="padding:.35rem .6rem;"><kbd>F6</kbd></td>
          <td style="padding:.35rem .6rem;">Move focus to the next named section (cycles: File → Quick Actions → Settings → Editor → Command → Log → header → repeat)</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Shift+F6</kbd></td>
          <td style="padding:.35rem .6rem;">Move focus to the previous named section</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Escape</kbd></td>
          <td style="padding:.35rem .6rem;"><strong>Exit the code editor tab trap</strong> — returns focus to the Load button in the editor toolbar</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+,</kbd></td>
          <td style="padding:.35rem .6rem;">Open / close this help dialog</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+Shift+E</kbd></td>
          <td style="padding:.35rem .6rem;">Jump to the Model Editor and enter it</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+Shift+F</kbd></td>
          <td style="padding:.35rem .6rem;">Jump to the File path input</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+Shift+C</kbd></td>
          <td style="padding:.35rem .6rem;">Jump to the Custom Command input</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+Shift+L</kbd></td>
          <td style="padding:.35rem .6rem;">Move focus to the Output Log</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+Shift+S</kbd></td>
          <td style="padding:.35rem .6rem;">Open / close the Appearance settings drawer</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+S</kbd></td>
          <td style="padding:.35rem .6rem;">Save the current editor content to disk</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Ctrl+O</kbd></td>
          <td style="padding:.35rem .6rem;">Load the file at the current path into the editor</td></tr>
      <tr><td style="padding:.35rem .6rem;"><kbd>Enter</kbd> (in Command input)</td>
          <td style="padding:.35rem .6rem;">Run the 3dm command</td></tr>
    </tbody>
  </table>
  <p style="margin: 1rem 0 0; font-size:.85rem; color:#aaa;">
    <strong>Tab trap note:</strong> While the code editor is focused, the
    <kbd>Tab</kbd> key inserts indentation rather than moving focus.
    Press <kbd>Escape</kbd> to leave the editor and return to normal tab order.
  </p>
  <button id="a11y-help-close"
          style="
            margin-top:1.25rem; padding:.5rem 1.25rem;
            background: var(--site-bg, #282a36);
            color: var(--site-text, #f8f8f2);
            border: 1px solid #888; border-radius:4px;
            font-size:1rem; cursor:pointer;
          "
          autofocus>
    Close (Escape or Enter)
  </button>
</dialog>
""")

    ui.add_body_html("""
<script>
(function () {
  'use strict';

  // ── Section landmark order for F6 cycling ──────────────────────────────
  // IDs match the aria-label props stamped on each card above.
  // The header is included so F6 can reach the settings button.
  const SECTION_IDS = [
    'section-file',
    'section-quick',
    'section-settings',
    'section-editor',
    'section-cmd',
    'section-log',
  ];

  function firstFocusable(container) {
    // Returns the first keyboard-focusable element inside container,
    // falling back to the container itself if nothing is found.
    const sel = 'button:not([disabled]), [href], input:not([disabled]), ' +
                'select:not([disabled]), textarea:not([disabled]), ' +
                '[tabindex]:not([tabindex="-1"]), .cm-content';
    return container.querySelector(sel) || container;
  }

  function focusSection(id) {
    const el = document.getElementById(id);
    if (!el) return;
    // Scroll into view for low-vision users who may be zoomed in
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const target = firstFocusable(el);
    target.focus();
    // Announce section name to screen readers via aria-live region
    const liveRegion = document.getElementById('a11y-live');
    if (liveRegion) {
      liveRegion.textContent = '';
      requestAnimationFrame(() => {
        liveRegion.textContent = el.getAttribute('aria-label') || id;
      });
    }
  }

  // ── aria-live region for screen reader announcements ───────────────────
  const live = document.createElement('div');
  live.id = 'a11y-live';
  live.setAttribute('role', 'status');
  live.setAttribute('aria-live', 'polite');
  live.setAttribute('aria-atomic', 'true');
  live.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;';
  document.body.appendChild(live);

  // ── Help dialog logic ──────────────────────────────────────────────────
  const dlg = document.getElementById('a11y-help-dialog');
  const closeBtn = document.getElementById('a11y-help-close');
  let _dialogOpener = null;

  function openHelp() {
    _dialogOpener = document.activeElement;
    dlg.showModal();
    closeBtn.focus();
  }
  function closeHelp() {
    dlg.close();
    if (_dialogOpener) _dialogOpener.focus();
  }
  closeBtn.addEventListener('click', closeHelp);
  dlg.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeHelp(); }
    if (e.key === 'Enter' && document.activeElement === closeBtn) { e.preventDefault(); closeHelp(); }
    // Trap focus inside the dialog
    if (e.key === 'Tab') {
      const focusable = Array.from(dlg.querySelectorAll(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      ));
      if (!focusable.length) { e.preventDefault(); return; }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
  });

  // ── Code editor tab-trap escape via Escape key ─────────────────────────
  // CodeMirror captures Tab for indentation.  We intercept Escape while
  // focus is inside .cm-editor and move focus to the Load button, which
  // is the first focusable element in the editor card toolbar.
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !dlg.open) {
      const active = document.activeElement;
      const inEditor = active && active.closest('.cm-editor');
      if (inEditor) {
        e.preventDefault();
        const editorCard = document.getElementById('section-editor');
        if (editorCard) {
          // Focus the first toolbar button (Load), not the editor itself
          const btn = editorCard.querySelector('button');
          if (btn) btn.focus();
        }
      }
    }
  }, true);  // capture phase so we beat CodeMirror's own listener

  // ── Global shortcut dispatcher ─────────────────────────────────────────
  document.addEventListener('keydown', function(e) {
    // Never fire shortcuts from inside the help dialog (except Escape handled above)
    if (dlg.open) return;

    const ctrl  = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;
    const key   = e.key;

    // ── Ctrl+,  → open help dialog ──────────────────────────────────────
    if (ctrl && !shift && key === ',') {
      e.preventDefault();
      openHelp();
      return;
    }

    // ── F6 / Shift+F6  → cycle sections ─────────────────────────────────
    if (key === 'F6') {
      e.preventDefault();
      const active = document.activeElement;
      let currentIdx = -1;
      SECTION_IDS.forEach(function(id, i) {
        const el = document.getElementById(id);
        if (el && el.contains(active)) currentIdx = i;
      });
      const total = SECTION_IDS.length;
      const nextIdx = shift
        ? (currentIdx - 1 + total) % total
        : (currentIdx + 1) % total;
      focusSection(SECTION_IDS[nextIdx]);
      return;
    }

    // ── Ctrl+Shift+E  → jump to editor ──────────────────────────────────
    if (ctrl && shift && key === 'E') {
      e.preventDefault();
      const ed = document.querySelector('#section-editor .cm-content');
      if (ed) ed.focus();
      else focusSection('section-editor');
      const live2 = document.getElementById('a11y-live');
      if (live2) { live2.textContent=''; requestAnimationFrame(()=>{ live2.textContent='Model Editor'; }); }
      return;
    }

    // ── Ctrl+Shift+F  → jump to file input ──────────────────────────────
    if (ctrl && shift && key === 'F') {
      e.preventDefault();
      const inp = document.querySelector('#section-file input');
      if (inp) inp.focus();
      return;
    }

    // ── Ctrl+Shift+C  → jump to command input ───────────────────────────
    if (ctrl && shift && key === 'C') {
      e.preventDefault();
      const inp = document.querySelector('#section-cmd input');
      if (inp) inp.focus();
      return;
    }

    // ── Ctrl+Shift+L  → jump to output log ──────────────────────────────
    if (ctrl && shift && key === 'L') {
      e.preventDefault();
      focusSection('section-log');
      return;
    }

    // ── Ctrl+Shift+S  → toggle settings drawer ──────────────────────────
    if (ctrl && shift && key === 'S') {
      e.preventDefault();
      // Trigger the NiceGUI settings button's click handler
      const settingsBtn = document.querySelector('.q-header button[aria-label*="settings"], .q-header button[title*="settings"], .q-header .q-btn:last-child');
      if (settingsBtn) settingsBtn.click();
      return;
    }

    // ── Ctrl+S  → save editor ────────────────────────────────────────────
    if (ctrl && !shift && key === 's') {
      // Only intercept when focus is inside the editor card or editor itself
      const inEditorCard = document.activeElement &&
        document.activeElement.closest('#section-editor');
      if (inEditorCard) {
        e.preventDefault();
        // Click the Save button in the editor toolbar
        const saveBtn = document.querySelector('#section-editor button[title*="Save"], #section-editor button:last-of-type');
        if (saveBtn) saveBtn.click();
      }
      return;
    }

    // ── Ctrl+O  → load file into editor ─────────────────────────────────
    if (ctrl && !shift && key === 'o') {
      e.preventDefault();
      const loadBtn = document.querySelector('#section-editor button');
      if (loadBtn) loadBtn.click();
      return;
    }

    // ── Enter in command input  → run command ────────────────────────────
    if (key === 'Enter' && !ctrl && !shift) {
      const active2 = document.activeElement;
      if (active2 && active2.closest('#section-cmd') && active2.tagName === 'INPUT') {
        e.preventDefault();
        const runBtn = document.querySelector('#section-cmd button');
        if (runBtn) runBtn.click();
      }
      return;
    }

  }, false);

  // ── Announce page ready to screen readers ─────────────────────────────
  window.addEventListener('load', function() {
    setTimeout(function() {
      const live3 = document.getElementById('a11y-live');
      if (live3) {
        live3.textContent = '3DMake GUI loaded. Press Control comma for keyboard shortcuts.';
      }
    }, 800);
  });

})();
</script>
""")

    # ── Footer ────────────────────────────────────────────────────────────────
    with ui.footer().classes("bg-gray-900 text-center text-xs text-gray-500 py-2"):
        ui.link(
            "tdeck/3dmake on GitHub",
            "https://github.com/tdeck/3dmake",
            new_tab=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Launch the GUI.  Called by the ``3dmake-gui`` console script."""
    ui.run(
        title="3DMake GUI Wrapper",
        port=8080,
        reload=False,
        show=True,
        # native=True,  # ← uncomment to open in a standalone desktop window
        #               #   (requires pywebview; good for PyInstaller builds)
    )


if __name__ == "__main__":
    main()

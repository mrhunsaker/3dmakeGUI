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

import argparse
import base64
import html
import json
import sys
from pathlib import Path
from time import perf_counter

from nicegui import ui

from . import __version__
from .core import (
    find_3dm_binary,
    get_3dmake_config_dir,
    get_3dmake_defaults_toml_path,
    get_packaged_executable_dir,
    install_directory_to_user_path,
    is_directory_on_path,
    launch_in_terminal,
    resolve_3dm_binary_path,
    run_command_async,
)

# ──────────────────────────────────────────────────────────────────────────────
# App-wide state
# ──────────────────────────────────────────────────────────────────────────────

_3dm_path: str | None = None
_current_file: Path | None = None
_output_dialog_counter = 0


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _log(output_log: ui.log, message: str) -> None:
    """Append a line of text to the UI log widget.

    Parameters
    ----------
    output_log : nicegui.ui.log
        Target log widget instance.
    message : str
        Message to append.
    """
    output_log.push(message)


def _open_text_output_dialog(
    title: str,
    content: str,
    status_line: str | None = None,
    trigger_button: ui.button | None = None,
    ui_container=None,
) -> None:
    """Render command output in an accessible modal dialog.

    Parameters
    ----------
    title : str
        Dialog title shown to the user.
    content : str
        Raw command output text to display.
    status_line : str or None, optional
        Supplemental summary line (for example exit code and elapsed time).
    trigger_button : nicegui.ui.button or None, optional
        Button to refocus when the dialog is closed.
    ui_container : Any, optional
        Optional NiceGUI container to host the dialog when it must be rendered
        in a specific slot context.
    """
    global _output_dialog_counter
    _output_dialog_counter += 1

    dialog_id = f"cmd-output-{_output_dialog_counter}"
    title_id = f"{dialog_id}-title"
    text_id = f"{dialog_id}-text"
    raw_text = content or "(No output captured)"
    numbered_lines = [f"{idx:04d} | {line}" for idx, line in enumerate(raw_text.splitlines(), start=1)]
    numbered_text = "\n".join(numbered_lines) if numbered_lines else "0001 |"

    def _build_dialog():
        with (
            ui.dialog().props(f'aria-modal="true" aria-labelledby="{title_id}"') as dlg,
            ui.card().classes("w-[760px] max-w-[96vw]"),
        ):
            ui.label(title).props(f'id="{title_id}"').classes("text-base font-semibold")
            if status_line:
                ui.label(status_line).classes("text-xs font-mono text-gray-500")
            ui.label("Use arrow keys to review output by line number. Press Escape or activate OK to close.").classes(
                "text-xs text-gray-500"
            )

            output_box = (
                ui.textarea(value=numbered_text, label="Command output (line numbered)")
                .props(f'readonly id="{text_id}" aria-label="Command output text with line numbers"')
                .classes("w-full font-mono text-sm")
                .style("min-height: 20rem;")
            )

            def _close_output_dialog() -> None:
                dlg.close()
                if trigger_button is not None:
                    trigger_button.run_method("focus")

            output_box.on("keydown.escape", lambda _e: _close_output_dialog())

            with ui.row().classes("w-full justify-end mt-2"):
                ui.button("OK", on_click=_close_output_dialog).props(
                    'color=primary size=sm aria-label="Close command output dialog"'
                )
        return dlg, output_box

    if ui_container is not None:
        with ui_container:
            dlg, output_box = _build_dialog()
    else:
        dlg, output_box = _build_dialog()

    dlg.open()
    output_box.run_method("focus")


async def _stream_command(
    cmd: str,
    output_log: ui.log,
    cwd: str | None = None,
    post_run=None,
    show_popup: bool = False,
    popup_title: str | None = None,
    trigger_button: ui.button | None = None,
    ui_container=None,
) -> None:
    """Execute a command and stream output into the GUI log.

    Parameters
    ----------
    cmd : str
        Shell command string to execute.
    output_log : nicegui.ui.log
        Log widget used for streamed output.
    cwd : str or None, optional
        Working directory for command execution.
    post_run : callable or None, optional
        Awaitable callback executed when the command exits successfully.
    show_popup : bool, optional
        Whether to display a line-numbered output dialog after completion.
    popup_title : str or None, optional
        Custom title for the output dialog.
    trigger_button : nicegui.ui.button or None, optional
        Button to focus after closing the output dialog.
    ui_container : Any, optional
        Optional dialog host container for slot-context safe rendering.
    """
    started_at = perf_counter()
    _log(output_log, f"[RUN] {cmd}")
    saw_error = False
    final_rc = "?"
    popup_lines: list[str] = []
    if show_popup:
        popup_lines.append(f"[RUN] {cmd}")

    async for line in run_command_async(cmd, cwd=cwd):
        if line.startswith("[done]"):
            rc_part = line[len("[done] ") :].strip()
            rc = rc_part if rc_part else "?"
            final_rc = rc
            status = "[DONE] Done" if rc == "0" else f"[ERROR] Exited with code {rc}"
            _log(output_log, status)
            if show_popup:
                popup_lines.append(status)
            if rc == "0" and post_run is not None:
                await post_run()
        elif line.startswith("[stderr]"):
            saw_error = True
            message = line[9:]
            _log(output_log, message)  # strip tag
            if show_popup:
                popup_lines.append(f"[stderr] {message}")
        else:
            message = line[9:]
            _log(output_log, message)  # strip [stdout]
            if show_popup:
                popup_lines.append(message)

    if show_popup:
        elapsed = perf_counter() - started_at
        _open_text_output_dialog(
            popup_title or "3dm Command Output",
            "\n".join(popup_lines).strip(),
            status_line=f"Command: {cmd} | Exit: {final_rc} | Duration: {elapsed:.2f}s",
            trigger_button=trigger_button,
            ui_container=ui_container,
        )

    if saw_error:
        ui.run_javascript("""
            const logEl = document.querySelector('#section-log .nicegui-log');
            if (logEl) {
              logEl.setAttribute('aria-live', 'assertive');
              setTimeout(() => logEl.setAttribute('aria-live', 'polite'), 1200);
            }
            """)


def _sanitize_svg(svg_content: str) -> str:
    """Normalize SVG text for inline HTML embedding.

    Parameters
    ----------
    svg_content : str
        SVG file content.

    Returns
    -------
    str
        SVG markup with XML declaration and doctype wrappers removed.
    """
    cleaned = svg_content
    if cleaned.lstrip().startswith("<?xml"):
        cleaned = cleaned[cleaned.find("?>") + 2 :]
    stripped = cleaned.lstrip()
    if stripped.startswith("<!DOCTYPE"):
        end = stripped.find(">")
        cleaned = stripped[end + 1 :] if end != -1 else stripped
    return cleaned.strip()


async def _open_svg_viewer(
    project_root: Path | None,
    model_name: str,
    view: str,
    log_widget: ui.log | None,
    trigger_button: ui.button | None = None,
) -> None:
    """Open a generated SVG preview in an accessible dialog.

    Parameters
    ----------
    project_root : pathlib.Path or None
        Root directory of the active 3dmake project.
    model_name : str
        Model name used to compute the output file path.
    view : str
        View identifier used in the output file naming convention.
    log_widget : nicegui.ui.log or None
        Optional log widget for informational status messages.
    trigger_button : nicegui.ui.button or None, optional
        Button to refocus after closing the dialog.
    """
    if project_root is None:
        if log_widget is not None:
            _log(log_widget, "[info] Preview complete. SVG location is unknown.")
        return

    svg_path = project_root / "build" / f"{model_name}-{view}.svg"
    if not svg_path.exists():
        if log_widget is not None:
            _log(
                log_widget,
                "[info] Preview complete. SVG not found at expected path; check build directory.",
            )
        return

    svg_content = _sanitize_svg(svg_path.read_text(encoding="utf-8"))

    with (
        ui.dialog().props('aria-modal="true" aria-labelledby="svg-dlg-title"') as dlg,
        ui.card().classes("w-[600px] max-w-[95vw]"),
    ):
        ui.label(f"Preview: {model_name} ({view})").props('id="svg-dlg-title"').classes("text-base font-semibold")
        ui.html(
            f'<div role="img" aria-label="Tactile preview silhouette of {html.escape(model_name)} from view {html.escape(view)}" '
            f'style="width:100%;overflow:auto;">{svg_content}</div>'
        )
        with ui.row().classes("gap-2 mt-2 items-center"):
            ui.link("Download SVG", target=str(svg_path), new_tab=True).props(
                'aria-label="Download the SVG file for embossing or swell paper printing"'
            )

            def _close_svg() -> None:
                dlg.close()
                if trigger_button is not None:
                    trigger_button.run_method("focus")

            ui.button("Close", on_click=_close_svg).props('flat size=sm aria-label="Close SVG preview"')
    dlg.open()
    if log_widget is not None:
        _log(log_widget, f"[info] Preview SVG opened: {svg_path.name}")


async def _open_stl_viewer(
    stl_path: Path,
    log_widget: ui.log | None,
    trigger_button: ui.button | None = None,
) -> None:
    """Open an STL file in the interactive Three.js viewer dialog.

    Parameters
    ----------
    stl_path : pathlib.Path
        Path to the STL file to render.
    log_widget : nicegui.ui.log or None
        Optional log widget for status updates.
    trigger_button : nicegui.ui.button or None, optional
        Button to refocus after closing the dialog.

    Notes
    -----
    The viewer is initialized client-side with Three.js, STLLoader, and
    OrbitControls loaded from CDN assets.
    """
    if not stl_path.exists() or stl_path.suffix.lower() != ".stl":
        ui.notify("STL file not found.", type="warning")
        return

    stl_b64 = base64.b64encode(stl_path.read_bytes()).decode("ascii")
    dims_text = "Install trimesh for bounding box dimensions."
    try:
        import trimesh

        mesh = trimesh.load(str(stl_path), force="mesh")
        bb = mesh.bounding_box.extents
        dims_text = f"Width: {bb[0]:.1f} mm  Depth: {bb[1]:.1f} mm  Height: {bb[2]:.1f} mm"
    except (ImportError, OSError, ValueError):
        pass

    safe_stem = "".join(ch if ch.isalnum() else "-" for ch in stl_path.stem).strip("-")
    if not safe_stem:
        safe_stem = "model"
    dialog_id = f"stl-dlg-{safe_stem}"
    canvas_id = f"stl-canvas-{safe_stem}"
    live_id = f"stl-live-{safe_stem}"

    with (
        ui.dialog().props(f'id="{dialog_id}" aria-modal="true" aria-labelledby="{dialog_id}-title"') as dlg,
        ui.card().classes("w-[700px] max-w-[95vw]"),
    ):
        ui.label(f"3D View: {stl_path.name}").props(f'id="{dialog_id}-title"').classes("text-base font-semibold")
        ui.label(dims_text).classes("text-sm font-mono").props('aria-label="Bounding box dimensions" tabindex="0"')
        ui.label("Controls: drag to rotate, scroll to zoom, R to reset, arrow keys to rotate by 15 degrees").classes(
            "text-xs text-gray-400"
        )
        ui.html(
            f'<canvas id="{canvas_id}" width="660" height="440" tabindex="0" role="img" '
            f'aria-label="Interactive 3D view of {html.escape(stl_path.name)}. Use arrow keys to rotate, plus and minus to zoom."></canvas>'
            f'<div id="{live_id}" role="status" aria-live="polite" '
            'style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);"></div>'
        )

        def _close_stl() -> None:
            dlg.close()
            if trigger_button is not None:
                trigger_button.run_method("focus")

        with ui.row().classes("gap-2 mt-2"):
            ui.button("Close", on_click=_close_stl).props('flat size=sm aria-label="Close 3D viewer"')

    dlg.open()
    ui.run_javascript(f"""
        (function() {{
          const ensureScript = (src) => new Promise((resolve, reject) => {{
            if ([...document.scripts].some(s => s.src.includes(src))) return resolve();
            const sc = document.createElement('script');
            sc.src = src;
            sc.onload = resolve;
            sc.onerror = reject;
            document.head.appendChild(sc);
          }});

          const init = async () => {{
            await ensureScript('cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js');
            await ensureScript('cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js');
            await ensureScript('cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js');

            const canvas = document.getElementById('{canvas_id}');
            if (!canvas) return;

            const renderer = new THREE.WebGLRenderer({{ canvas: canvas, antialias: true }});
            renderer.setPixelRatio(window.devicePixelRatio || 1);
            renderer.setSize(canvas.width, canvas.height, false);

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x111827);
            const camera = new THREE.PerspectiveCamera(50, canvas.width / canvas.height, 0.1, 5000);
            camera.position.set(120, 90, 140);

            scene.add(new THREE.AmbientLight(0xffffff, 0.6));
            const dl = new THREE.DirectionalLight(0xffffff, 0.7);
            dl.position.set(1, 1, 2);
            scene.add(dl);

            const bytes = atob('{stl_b64}');
            const arr = new Uint8Array(bytes.length);
            for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
            const loader = new THREE.STLLoader();
            const geom = loader.parse(arr.buffer);
            geom.computeBoundingBox();
            geom.computeVertexNormals();
            const mat = new THREE.MeshPhongMaterial({{ color: 0x93c5fd, specular: 0x111111, shininess: 25 }});
            const mesh = new THREE.Mesh(geom, mat);
            const box = geom.boundingBox;
            const center = new THREE.Vector3();
            box.getCenter(center);
            mesh.position.sub(center);
            scene.add(mesh);

            const controls = new THREE.OrbitControls(camera, canvas);
            controls.enableDamping = true;
            controls.dampingFactor = 0.08;

            const size = new THREE.Vector3();
            box.getSize(size);
            const maxDim = Math.max(size.x, size.y, size.z) || 1;
            camera.position.set(maxDim * 1.5, maxDim * 1.2, maxDim * 1.8);
            controls.update();

            const live = document.getElementById('{live_id}');
            const announce = () => {{
              if (!live) return;
              const az = THREE.MathUtils.radToDeg(controls.getAzimuthalAngle()).toFixed(0);
              const el = THREE.MathUtils.radToDeg(controls.getPolarAngle()).toFixed(0);
              live.textContent = '';
              requestAnimationFrame(() => {{
                live.textContent = `Rotated to ${{az}} degrees azimuth, ${{el}} degrees elevation`;
              }});
            }};

            canvas.addEventListener('keydown', (e) => {{
              let acted = false;
              const step = Math.PI / 12;
              if (e.key === 'ArrowLeft') {{ controls.rotateLeft(step); acted = true; }}
              if (e.key === 'ArrowRight') {{ controls.rotateLeft(-step); acted = true; }}
              if (e.key === 'ArrowUp') {{ controls.rotateUp(step); acted = true; }}
              if (e.key === 'ArrowDown') {{ controls.rotateUp(-step); acted = true; }}
              if (e.key === '+' || e.key === '=') {{ camera.position.multiplyScalar(0.9); acted = true; }}
              if (e.key === '-' || e.key === '_') {{ camera.position.multiplyScalar(1.1); acted = true; }}
              if (e.key.toLowerCase() === 'r') {{
                camera.position.set(maxDim * 1.5, maxDim * 1.2, maxDim * 1.8);
                controls.target.set(0, 0, 0);
                acted = true;
              }}
              if (acted) {{
                e.preventDefault();
                controls.update();
                announce();
              }}
            }});

            controls.addEventListener('change', announce);

            const animate = () => {{
              controls.update();
              renderer.render(scene, camera);
              requestAnimationFrame(animate);
            }};
            animate();
          }};

          init().catch((err) => console.error('STL viewer failed', err));
        }})();
        """)
    if log_widget is not None:
        _log(log_widget, f"[info] Opened STL viewer for: {stl_path.name}")


def _find_project_root(path_value: str) -> Path | None:
    """Resolve a file or directory path to its containing 3dmake project root.

    Parameters
    ----------
    path_value : str
        User-selected file or directory path.

    Returns
    -------
    pathlib.Path or None
        Nearest ancestor containing ``3dmake.toml``, or ``None`` if no project
        root can be determined.
    """
    if not path_value:
        return None

    raw = Path(path_value).expanduser()
    search = raw if raw.is_dir() else raw.parent
    for candidate in [search, *search.parents]:
        if (candidate / "3dmake.toml").exists():
            return candidate
    return None


def _ensure_project_layout(project_root: Path, project_name: str) -> None:
    """Create required project folders and baseline configuration files.

    Parameters
    ----------
    project_root : pathlib.Path
        Directory where project layout should exist.
    project_name : str
        Name written into a newly created ``3dmake.toml`` file.
    """
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
    """Normalize a SCAD filename for project file creation.

    Parameters
    ----------
    name : str
        Raw filename entered by the user.

    Returns
    -------
    str
        Filename guaranteed to be non-empty and to end with ``.scad``.
    """
    cleaned = (name or "").strip() or "model.scad"
    if not cleaned.lower().endswith(".scad"):
        cleaned = f"{cleaned}.scad"
    return cleaned


def _pick_directory_native(initial_dir: str | None = None) -> str | None:
    """Open a directory picker and return the selected directory.

    Parameters
    ----------
    initial_dir : str or None, optional
        Initial directory displayed by the native picker.

    Returns
    -------
    str or None
        Selected directory path, or ``None`` when selection is canceled or no
        native picker is available.
    """
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
    """Build and render the main application page.

    Notes
    -----
    This page wires together all primary UI regions: project/file selection,
    quick command actions, command options, source editor, output log, and
    application settings. It also initializes persisted GUI preferences.
    """
    global _3dm_path

    _3dm_path = find_3dm_binary()
    settings_path = get_3dmake_config_dir() / "gui_settings.json"
    packaged_dir = get_packaged_executable_dir()

    def _load_gui_settings() -> dict:
        if not settings_path.exists():
            return {}
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

    def _save_gui_settings(settings: dict) -> None:
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    _gui_settings = _load_gui_settings()

    def _should_offer_path_install() -> bool:
        if packaged_dir is None:
            return False
        if is_directory_on_path(packaged_dir):
            _gui_settings["path_install_prompted_for"] = str(packaged_dir)
            _save_gui_settings(_gui_settings)
            return False
        return _gui_settings.get("path_install_prompted_for") != str(packaged_dir)

    def _mark_path_prompt_seen() -> None:
        if packaged_dir is None:
            return
        _gui_settings["path_install_prompted_for"] = str(packaged_dir)
        _save_gui_settings(_gui_settings)

    # ── Header ────────────────────────────────────────────────────────────────
    # ── Appearance state (font size + theme) ─────────────────────────────────
    _font_state = {"size": "medium"}  # "medium" | "large" | "xlarge"
    _wrap_state = {"enabled": bool(_gui_settings.get("editor_word_wrap", False))}
    EDITOR_PX = {"medium": 14, "large": 17, "xlarge": 20}
    FONT_SIZES = [
        ("Medium", "medium"),
        ("Large", "large"),
        ("X-Large", "xlarge"),
    ]
    _log_ref: list = [None]
    _popup_host_ref: list = [None]
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

    def _apply_word_wrap(enabled: bool) -> None:
        """Toggle visual line wrapping in CodeMirror content."""
        _wrap_state["enabled"] = enabled
        _gui_settings["editor_word_wrap"] = enabled
        _save_gui_settings(_gui_settings)
        wrap = "true" if enabled else "false"
        ui.run_javascript(f"""
            const useWrap = {wrap};
            document.querySelectorAll('#section-editor .cm-content').forEach((el) => {{
              el.style.whiteSpace = useWrap ? 'pre-wrap' : 'pre';
              el.style.wordBreak = useWrap ? 'break-word' : 'normal';
            }});
            document.querySelectorAll('#section-editor .cm-line').forEach((el) => {{
              el.style.whiteSpace = useWrap ? 'pre-wrap' : 'pre';
            }});
            const scroller = document.querySelector('#section-editor .cm-scroller');
            if (scroller) scroller.style.overflowX = useWrap ? 'hidden' : 'auto';
            """)

    # ── Header ────────────────────────────────────────────────────────────────
    with ui.header().classes("items-center justify-between bg-gray-900 text-white px-4 py-2"):
        ui.label("3DMake GUI").classes("text-xl font-bold tracking-wide")

        if _3dm_path:
            ui.label(f"3dm: {_3dm_path}").classes("text-xs text-green-400 font-mono")
        else:
            ui.label("⚠ 3dm not found").classes("text-xs text-yellow-400")

        # ⚙ Settings button — opens the right drawer
        ui.button(icon="settings", on_click=lambda: settings_drawer.toggle()).props(
            "flat round color=white aria-label='Open appearance settings: theme and font size'"
        ).tooltip("Appearance settings (theme & font size)")

    if packaged_dir is not None and _should_offer_path_install():
        with (
            ui.dialog().props('aria-modal="true" aria-labelledby="path-install-title"') as path_dlg,
            ui.card().classes("w-[42rem] max-w-[96vw]"),
        ):
            ui.label("Add 3dmake-gui to PATH?").props('id="path-install-title"').classes("text-base font-semibold")
            ui.label(
                "This packaged build can add its application folder to your user PATH so "
                "you can launch 3dmake-gui from a terminal or command prompt."
            ).classes("text-sm")
            ui.label(str(packaged_dir)).classes("text-xs font-mono text-gray-400")
            ui.label("This affects only your user PATH, not the system-wide PATH.").classes("text-xs text-gray-500")

            def _close_path_dialog() -> None:
                _mark_path_prompt_seen()
                path_dlg.close()

            def _install_gui_path() -> None:
                ok, message = install_directory_to_user_path(packaged_dir)
                _mark_path_prompt_seen()
                ui.notify(message, type="positive" if ok else "negative")
                path_dlg.close()

            with ui.row().classes("gap-2 mt-3 justify-end"):
                ui.button("Add to PATH", on_click=_install_gui_path).props(
                    'color=primary size=sm aria-label="Add packaged application folder to PATH"'
                )
                ui.button("Not Now", on_click=_close_path_dialog).props(
                    'flat size=sm aria-label="Dismiss PATH installation prompt"'
                )

        path_dlg.open()

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
        ).props('color=primary aria-label="Text size selector"')
        _font_radio[0] = font_radio

        ui.separator().classes("my-4")

        ui.switch(
            "Word Wrap (Editor)",
            value=bool(_wrap_state["enabled"]),
            on_change=lambda e: _apply_word_wrap(bool(e.value)),
        ).props('aria-label="Toggle word wrap in code editor"')

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
                height: calc(100dvh - {HDR}px - {FTR}px - var(--cmd-card-h) - {
        LOG_H
    }px - {3 * GAP}px - {2 * PAD}px);
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
        _popup_host_ref[0] = ui.element("div").classes("w-0 h-0 overflow-hidden")
        # ── LEFT PANEL ────────────────────────────────────────────────────────
        with ui.column().classes("left-panel"):
            # 1. Project / File ────────────────────────────────────────────────
            with (
                ui.card()
                .classes("w-full")
                .props('id="section-file" aria-label="Project and file selection" role="region"')
            ):
                ui.label("Project / File").classes("text-base font-semibold mb-1")

                file_input = ui.input(
                    label="File or project directory",
                    placeholder="/home/user/model/src/model.scad",
                ).classes("w-full text-sm")

                _editor_path_label_ref: list[ui.label | None] = [None]

                def _update_editor_filepath(path_value: str | None = None) -> None:
                    value = path_value if path_value is not None else file_input.value
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
                    resolved = getattr(getattr(e, "content", None), "name", None) or e.name
                    file_input.set_value(resolved)
                    _update_editor_filepath(resolved)
                    ui.notify(f"Selected: {e.name}", type="positive")

                (
                    ui.upload(
                        label="Drop a .scad / .stl here",
                        on_upload=handle_upload,
                        max_file_size=50_000_000,
                    )
                    .props(
                        "accept=.scad,.stl,.3mf flat aria-label='Upload a .scad, .stl, or .3mf file - drag and drop or click Browse'"
                    )
                    .classes("w-full mt-2")
                )

                # Browse… programmatically clicks the hidden <input type=file>
                # that Quasar renders inside the upload widget.
                ui.button(
                    "Browse…",
                    on_click=lambda: ui.run_javascript(
                        "document.querySelector('.q-uploader input[type=file]').click()"
                    ),
                ).props("outline size=sm aria-label='Browse for a file to load'").classes("w-full mt-1")

            with (
                ui.expansion("Command Options", icon="tune")
                .classes("w-full")
                .props('id="section-options" aria-label="Command options" role="region"')
            ):
                _opt_model = (
                    ui.input(label="Model name (-m)", value="")
                    .classes("w-full")
                    .props('aria-label="Model name option: -m"')
                    .tooltip("Set model name using -m")
                )
                _opt_view = (
                    ui.select(
                        options=[
                            "3sil",
                            "frontsil",
                            "backsil",
                            "leftsil",
                            "rightsil",
                            "topsil",
                        ],
                        value="3sil",
                        label="View (-v)",
                    )
                    .classes("w-full")
                    .props('aria-label="View option: -v"')
                    .tooltip("Set silhouette view using -v")
                )
                _opt_profile = (
                    ui.input(label="Profile (-p)", value="")
                    .classes("w-full")
                    .props('aria-label="Profile option: -p"')
                    .tooltip("Set slicer profile using -p")
                )
                _opt_overlay = (
                    ui.input(
                        label="Overlays (-o, comma separated)",
                        value="",
                        placeholder="supports,fast",
                    )
                    .classes("w-full")
                    .props('aria-label="Overlay options: repeated -o flags"')
                    .tooltip("Comma-separated overlays map to repeated -o flags")
                )
                _opt_scale = (
                    ui.number(label="Scale (-s)", value=1.0, step=0.05)
                    .classes("w-full")
                    .props('aria-label="Scale option: -s"')
                    .tooltip("Scale model with -s")
                )
                _opt_copies = (
                    ui.number(label="Copies (-c)", value=1, step=1)
                    .classes("w-full")
                    .props('aria-label="Copies option: -c"')
                    .tooltip("Set copies count with -c")
                )
                _opt_debug = (
                    ui.switch("Enable debug (--debug)", value=False)
                    .props('aria-label="Debug flag: --debug"')
                    .tooltip("Enable debug output with --debug")
                )
                _opt_interactive = (
                    ui.switch("Interactive info (-i)", value=False)
                    .props('aria-label="Interactive info flag: -i"')
                    .tooltip("Enable interactive mode for info with -i")
                )

                def _build_flags() -> str:
                    parts: list[str] = []
                    model = (_opt_model.value or "").strip()
                    view = (_opt_view.value or "").strip()
                    profile = (_opt_profile.value or "").strip()
                    overlays_raw = (_opt_overlay.value or "").strip()
                    scale_val = float(_opt_scale.value or 1.0)
                    copies_val = int(_opt_copies.value or 1)

                    if model:
                        parts.extend(["-m", model])
                    if view:
                        parts.extend(["-v", view])
                    if profile:
                        parts.extend(["-p", profile])
                    if overlays_raw:
                        for ov in [o.strip() for o in overlays_raw.split(",") if o.strip()]:
                            parts.extend(["-o", ov])
                    if scale_val != 1.0:
                        parts.extend(["-s", str(scale_val)])
                    if copies_val != 1:
                        parts.extend(["-c", str(copies_val)])
                    if _opt_debug.value:
                        parts.append("--debug")
                    if _opt_interactive.value:
                        parts.append("-i")

                    return " ".join(parts)

            # 2. Quick Actions ─────────────────────────────────────────────────
            with ui.card().classes("w-full").props('id="section-quick" aria-label="Quick actions" role="region"'):
                ui.label("Quick Actions").classes("text-base font-semibold mb-1")
                ui.label("Runs against the file path above.").classes("text-xs text-gray-500 mb-2")

                quick_cmds = [
                    (
                        "Describe (Info)",
                        "3dm info {file}",
                        "Describe shape with AI using 3dm info",
                        "Describe model: runs 3dm info",
                        False,
                    ),
                    (
                        "Build STL",
                        "3dm build {file}",
                        "Compile .scad to .stl using 3dm build",
                        "Build STL: runs 3dm build",
                        False,
                    ),
                    (
                        "Slice",
                        "3dm slice {file}",
                        "Slice .stl for printing",
                        "Slice model: runs 3dm slice",
                        False,
                    ),
                    (
                        "Orient",
                        "3dm orient {file}",
                        "Auto-orient for printing",
                        "Orient model: runs 3dm orient",
                        False,
                    ),
                    (
                        "Preview",
                        "3dm preview {file}",
                        "Generate 2-D tactile preview",
                        "Preview model: runs 3dm preview",
                        False,
                    ),
                    (
                        "New Project",
                        "3dm new",
                        "Scaffold a new 3dmake project",
                        "Create project: runs 3dm new",
                        False,
                    ),
                    (
                        "Build + Slice",
                        "3dm build slice {file}",
                        "Compile .scad then slice to .gcode",
                        "Build and slice: runs 3dm build slice",
                        False,
                    ),
                    (
                        "Full Pipeline",
                        "3dm build orient slice {file}",
                        "Build, auto-orient, then slice",
                        "Full pipeline: runs 3dm build orient slice",
                        False,
                    ),
                    (
                        "Print",
                        "3dm print",
                        "Send sliced file to printer (OctoPrint / Bambu)",
                        "Print: runs 3dm print",
                        True,
                    ),
                    (
                        "View STL",
                        "__view_stl__",
                        "Open STL in 3D viewer",
                        "View STL file in 3D viewer",
                        False,
                    ),
                ]

                preview_btn_ref: list[ui.button | None] = [None]

                with (
                    ui.grid(columns=3)
                    .classes("w-full gap-2")
                    .props('role="toolbar" aria-label="Quick 3dm actions" aria-orientation="horizontal"')
                ):
                    for (
                        btn_label,
                        cmd_tpl,
                        tip,
                        aria_label,
                        needs_project,
                    ) in quick_cmds:

                        def _make_handler(
                            tpl=cmd_tpl,
                            label=btn_label,
                            requires_project=needs_project,
                        ):
                            async def handler():
                                if _log_ref[0] is None:
                                    return

                                path = file_input.value.strip()
                                if not path and "{file}" in tpl:
                                    ui.notify("Enter a file path first.", type="warning")
                                    return

                                if tpl == "__view_stl__":
                                    if not path.lower().endswith(".stl"):
                                        ui.notify(
                                            "Set an .stl file path first.",
                                            type="warning",
                                        )
                                        return
                                    await _open_stl_viewer(Path(path), _log_ref[0])
                                    return

                                project_root = _find_project_root(path)

                                if requires_project and project_root is None:
                                    ui.notify(
                                        "No 3dmake project found at that path. Run 3dm new first.",
                                        type="warning",
                                    )
                                    return

                                cmd = tpl
                                if "{file}" in tpl:
                                    cmd = cmd.replace("{file}", f'"{path}"')

                                flags = _build_flags().strip()
                                if flags and label != "New Project":
                                    cmd = f"{cmd} {flags}".strip()

                                if _3dm_path:
                                    cmd = cmd.replace("3dm ", f'"{_3dm_path}" ', 1)

                                post_run = None
                                if label == "Preview":
                                    model_name = (_opt_model.value or "").strip() or "main"
                                    view = (_opt_view.value or "").strip() or "3sil"

                                    def post_run():
                                        _open_svg_viewer(
                                            project_root,
                                            model_name,
                                            view,
                                            _log_ref[0],
                                            preview_btn_ref[0],
                                        )

                                await _stream_command(
                                    cmd,
                                    _log_ref[0],
                                    cwd=str(project_root) if project_root else None,
                                    post_run=post_run,
                                    show_popup=True,
                                    popup_title=f"{label} Output",
                                    ui_container=_popup_host_ref[0],
                                )

                            return handler

                        btn = (
                            ui.button(btn_label, on_click=_make_handler())
                            .tooltip(tip)
                            .props(f'size=sm aria-label="{aria_label}"')
                            .classes("w-full")
                        )
                        if btn_label == "Preview":
                            preview_btn_ref[0] = btn

                async def _open_last_svg() -> None:
                    await _open_svg_viewer(
                        _find_project_root((file_input.value or "").strip()),
                        (_opt_model.value or "").strip() or "main",
                        (_opt_view.value or "").strip() or "3sil",
                        _log_ref[0],
                        preview_btn_ref[0],
                    )

                ui.button(
                    "View Last SVG",
                    on_click=_open_last_svg,
                ).props(
                    'size=sm aria-label="Open previously generated SVG preview"'
                ).classes("w-full mt-2")

            with (
                ui.expansion("Image Export", icon="photo_camera")
                .classes("w-full")
                .props('id="section-image" aria-label="Image export" role="region"')
            ):
                angle_select = ui.select(
                    options=[
                        "above_front_left",
                        "above_front",
                        "above_front_right",
                        "front",
                        "back",
                        "left",
                        "right",
                        "top",
                        "bottom",
                        "above_back_left",
                        "above_back_right",
                    ],
                    multiple=True,
                    label="Camera angles",
                    value=["above_front_left", "above_front", "above_front_right"],
                ).classes("w-full")
                colorscheme_select = ui.select(
                    options=["slicer_light", "slicer_dark", "light_on_dark"],
                    value="slicer_dark",
                    label="Color scheme",
                ).classes("w-full")
                image_size_input = ui.input(label="Image size", value="1080x720", placeholder="1080x720").classes(
                    "w-full"
                )

                async def _run_image_export() -> None:
                    path = (file_input.value or "").strip()
                    if not path:
                        ui.notify("Enter a file path first.", type="warning")
                        return
                    if _log_ref[0] is None:
                        return

                    project_root = _find_project_root(path)
                    if project_root is None:
                        ui.notify(
                            "No 3dmake project found at that path. Run 3dm new first.",
                            type="warning",
                        )
                        return

                    angles = angle_select.value or []
                    if not angles:
                        ui.notify("Choose at least one camera angle.", type="warning")
                        return

                    angle_flags = " ".join(f"-a {a}" for a in angles)
                    cmd = (
                        f"3dm image {angle_flags} --colorscheme {colorscheme_select.value} "
                        f'--image-size {image_size_input.value} "{path}"'
                    )
                    if _3dm_path:
                        cmd = cmd.replace("3dm ", f'"{_3dm_path}" ', 1)

                    before = set((project_root / "build").glob("*.png"))
                    await _stream_command(
                        cmd,
                        _log_ref[0],
                        cwd=str(project_root),
                        show_popup=True,
                        popup_title="Image Export Output",
                        ui_container=_popup_host_ref[0],
                    )
                    after = set((project_root / "build").glob("*.png"))
                    created = sorted(after - before)

                    if not created:
                        ui.notify("Image export finished. No new PNG files detected.")
                        return

                    with (
                        ui.dialog().props(
                            'role="dialog" aria-label="Image export results" aria-modal="true"'
                        ) as img_dlg,
                        ui.card().classes("w-[760px] max-w-[95vw]"),
                    ):
                        ui.label("Image export results").classes("text-base font-semibold")
                        with ui.column().classes("w-full gap-2"):
                            for png in created:
                                angle_name = png.stem.split("-")[-1]
                                ui.image(str(png)).classes("w-full").props(f'aria-label="Model render: {angle_name}"')
                        ui.button("Close", on_click=img_dlg.close).props(
                            'flat size=sm aria-label="Close image export results"'
                        )
                    img_dlg.open()

                ui.button("Run Image Export", on_click=_run_image_export).props(
                    'size=sm aria-label="Export images: runs 3dm image with selected angles"'
                ).classes("w-full")

            # ── Settings card ─────────────────────────────────────────────────
            with ui.card().classes("w-full").props('id="section-settings" aria-label="Settings" role="region"'):
                ui.label("Settings").classes("text-base font-semibold mb-1")

                def _with_binary(cmd: str) -> str:
                    if _3dm_path and cmd.startswith("3dm "):
                        return cmd.replace("3dm ", f'"{_3dm_path}" ', 1)
                    return cmd

                def _project_root_from_input() -> Path | None:
                    return _find_project_root((file_input.value or "").strip())

                async def _run_settings_command(cmd: str, needs_project: bool = False):
                    if _log_ref[0] is None:
                        return
                    project_root = _project_root_from_input()
                    if needs_project and project_root is None:
                        ui.notify(
                            "No 3dmake project found at that path. Run 3dm new first.",
                            type="warning",
                        )
                        return
                    await _stream_command(
                        _with_binary(cmd),
                        _log_ref[0],
                        cwd=str(project_root) if project_root else None,
                        show_popup=True,
                        popup_title=f"{cmd} Output",
                        ui_container=_popup_host_ref[0],
                    )

                def _launch_in_terminal_ui(cmd: str) -> None:
                    launched = launch_in_terminal(_with_binary(cmd))
                    if launched:
                        ui.notify("Opened command in system terminal.", type="positive")
                    else:
                        ui.notify(
                            "No supported terminal emulator found. Run the command manually.",
                            type="warning",
                        )

                setup_btn_ref: list[ui.button | None] = [None]

                def open_setup_dialog() -> None:
                    with (
                        ui.dialog().props('aria-modal="true" aria-labelledby="setup-dlg-title"') as dlg,
                        ui.card().classes("w-[34rem]"),
                    ):
                        ui.label("Run 3dm setup").props('id="setup-dlg-title"').classes("text-base font-semibold")
                        ui.label(
                            "3dm setup is an interactive command that requires terminal input. "
                            "Click Launch in Terminal to open it in your system terminal, "
                            "or run it manually."
                        ).classes("text-xs text-gray-500")

                        def _close_setup() -> None:
                            dlg.close()
                            if setup_btn_ref[0] is not None:
                                setup_btn_ref[0].run_method("focus")

                        with ui.row().classes("gap-2 mt-2"):
                            ui.button(
                                "Launch in Terminal",
                                on_click=lambda: _launch_in_terminal_ui("3dm setup"),
                            ).props('color=primary size=sm aria-label="Launch 3dm setup in terminal"')
                            ui.button("Close", on_click=_close_setup).props(
                                'flat size=sm aria-label="Close setup dialog"'
                            )
                    dlg.open()

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

                def _load_text_file_in_editor(
                    target: Path,
                    label: str,
                    create_if_missing: bool = False,
                    default_content: str = "",
                ) -> None:
                    if not target.exists():
                        if not create_if_missing:
                            ui.notify(f"{label} not found at: {target}", type="warning")
                            return
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(default_content, encoding="utf-8")
                        except OSError as exc:
                            ui.notify(f"Could not create {target}: {exc}", type="negative")
                            return
                    try:
                        content = target.read_text(encoding="utf-8")
                    except OSError as exc:
                        ui.notify(f"Could not read {target}: {exc}", type="negative")
                        return

                    editor.set_value(content)
                    file_input.set_value(str(target))
                    _update_editor_filepath(str(target))
                    ui.notify(f"Loaded {label}: {target}", type="positive")

                def _resolve_named_file(
                    root: Path,
                    name: str,
                    fallback_suffix: str,
                ) -> Path:
                    raw = (name or "").strip()
                    if not raw:
                        return root / f"default{fallback_suffix}"

                    candidate = Path(raw)
                    if candidate.suffix:
                        return root / candidate.name

                    for suffix in [
                        ".toml",
                        ".ini",
                        ".yaml",
                        ".yml",
                        ".json",
                        ".txt",
                        ".md",
                    ]:
                        path = root / f"{raw}{suffix}"
                        if path.exists():
                            return path

                    return root / f"{raw}{fallback_suffix}"

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
                        ui.label("Set 3dm Binary Path").classes("text-base font-semibold mb-2")
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
                            ui.button("Apply", on_click=apply_path).props("color=primary size=sm")
                            ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
                    dlg.open()

                def open_self_update_confirm() -> None:
                    with ui.dialog() as dlg, ui.card().classes("w-[28rem]"):
                        ui.label("Confirm self update").classes("text-base font-semibold")
                        ui.label("This will overwrite the 3dm binary. Continue?").classes("text-xs text-gray-500")

                        async def _run_self_update() -> None:
                            await _run_settings_command("3dm self-update")
                            dlg.close()

                        with ui.row().classes("gap-2 mt-2"):
                            ui.button(
                                "Continue",
                                on_click=_run_self_update,
                            ).props('color=primary size=sm aria-label="Run 3dm self-update"')
                            ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
                    dlg.open()

                def open_edit_overlay_dialog() -> None:
                    with ui.dialog() as dlg, ui.card().classes("w-[28rem]"):
                        ui.label("Edit Overlay").classes("text-base font-semibold")
                        overlay_name = ui.input(
                            label="Overlay name",
                            placeholder="supports",
                        ).classes("w-full")

                        def _run_overlay() -> None:
                            value = (overlay_name.value or "").strip()
                            if not value:
                                ui.notify("Enter an overlay name first.", type="warning")
                                return
                            config_dir = get_3dmake_config_dir()
                            overlay_dir = config_dir / "overlays"
                            target = _resolve_named_file(overlay_dir, value, ".ini")
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(
                                    "# 3dmake overlay\n# Add slicer override values here.\n",
                                    encoding="utf-8",
                                )
                            _load_text_file_in_editor(target, "overlay")
                            dlg.close()

                        with ui.row().classes("gap-2 mt-2"):
                            ui.button("Open", on_click=_run_overlay).props(
                                'color=primary size=sm aria-label="Edit slicer overlay: runs 3dm edit-overlay"'
                            )
                            ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
                    dlg.open()

                def _settings_click(cmd: str, needs_project: bool = False):
                    async def _handler() -> None:
                        await _run_settings_command(cmd, needs_project=needs_project)

                    return _handler

                with ui.grid(columns=3).classes("w-full gap-2"):
                    setup_btn_ref[0] = (
                        ui.button("Run Setup", on_click=open_setup_dialog)
                        .tooltip("Run 3dm setup to configure 3DMake for the first time")
                        .props('size=sm aria-label="Run 3dm setup: first-time configuration wizard"')
                        .classes("w-full")
                    )
                    ui.button("Global Config", on_click=open_global_config).tooltip(
                        "Load defaults.toml into the editor"
                    ).props("size=sm aria-label='Open global defaults.toml in editor'").classes("w-full")
                    ui.button("Project Config", on_click=open_project_config).tooltip(
                        "Load this project's 3dmake.toml into the editor"
                    ).props("size=sm aria-label='Open project 3dmake.toml in editor'").classes("w-full")
                    ui.button("Set 3dm Path", on_click=open_path_dialog).tooltip(
                        "Override the path to the 3dm binary"
                    ).props("size=sm aria-label='Set 3dm binary path override'").classes("w-full")
                    ui.button("List Libraries", on_click=_settings_click("3dm list-libraries")).tooltip(
                        "Run 3dm list-libraries"
                    ).props("size=sm aria-label='List libraries: runs 3dm list-libraries'").classes("w-full")
                    ui.button(
                        "Install Libraries",
                        on_click=_settings_click("3dm install-libraries", needs_project=True),
                    ).tooltip("Download libraries listed in 3dmake.toml").props(
                        'size=sm aria-label="Install libraries: runs 3dm install-libraries"'
                    ).classes(
                        "w-full"
                    )
                    ui.button(
                        "List Profiles",
                        on_click=_settings_click("3dm list-profiles"),
                    ).tooltip(
                        "List available slicer printer profiles"
                    ).props('size=sm aria-label="List printer profiles: runs 3dm list-profiles"').classes("w-full")
                    ui.button(
                        "List Overlays",
                        on_click=_settings_click("3dm list-overlays"),
                    ).tooltip(
                        "List available slicer overlays"
                    ).props('size=sm aria-label="List slicer overlays: runs 3dm list-overlays"').classes("w-full")
                    ui.button(
                        "Version Info",
                        on_click=_settings_click("3dm version"),
                    ).tooltip(
                        "Show 3dmake version and config directory"
                    ).props('size=sm aria-label="Version info: runs 3dm version"').classes("w-full")
                    ui.button("Self Update", on_click=open_self_update_confirm).tooltip(
                        "Update the 3dm binary to the latest version"
                    ).props('size=sm aria-label="Self update: runs 3dm self-update"').classes("w-full")
                    ui.button(
                        "3dm Help",
                        on_click=_settings_click("3dm help"),
                    ).tooltip(
                        "Show 3dmake CLI help text in the output log"
                    ).props('size=sm aria-label="CLI help: runs 3dm help"').classes("w-full")
                    ui.button("Edit Overlay", on_click=open_edit_overlay_dialog).props(
                        'size=sm aria-label="Edit slicer overlay: runs 3dm edit-overlay"'
                    ).classes("w-full")
                    ui.button(
                        "Edit Profile",
                        on_click=lambda: _load_text_file_in_editor(
                            _resolve_named_file(
                                get_3dmake_config_dir() / "profiles",
                                (_opt_profile.value or "").strip() or "default",
                                ".ini",
                            ),
                            "profile",
                            create_if_missing=True,
                            default_content="# 3dmake printer profile\n",
                        ),
                    ).props('size=sm aria-label="Edit printer profile: runs 3dm edit-profile"').classes("w-full")
                    ui.button(
                        "Edit AI Prompt",
                        on_click=lambda: _load_text_file_in_editor(
                            next(
                                (
                                    p
                                    for p in [
                                        get_3dmake_config_dir() / "prompt.txt",
                                        get_3dmake_config_dir() / "ai_prompt.txt",
                                        get_3dmake_config_dir() / "ai-prompt.txt",
                                        get_3dmake_config_dir() / "prompts" / "describe_prompt.txt",
                                        get_3dmake_config_dir() / "prompts" / "prompt.txt",
                                    ]
                                    if p.exists()
                                ),
                                get_3dmake_config_dir() / "prompt.txt",
                            ),
                            "AI prompt",
                            create_if_missing=True,
                            default_content="# 3dmake AI description prompt\n",
                        ),
                    ).props('size=sm aria-label="Edit AI description prompt: runs 3dm edit-prompt"').classes("w-full")

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
            with ui.card().classes("editor-card").props('id="section-editor" aria-label="Model editor" role="region"'):
                with (
                    ui.row().classes("w-full items-center justify-between").style("flex-shrink: 0; margin-bottom: 6px;")
                ):
                    with ui.row().classes("items-center gap-3"):
                        ui.label("Model Editor").classes("text-base font-semibold")
                        _editor_path_label_ref[0] = ui.label("Filepath: No Project Slected").classes(
                            "text-xs text-gray-400 font-mono"
                        )
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
                            selected = _pick_directory_native(target.value.strip() or str(Path.home()))
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
                                ui.label("Create New Project").classes("text-base font-semibold")
                                ui.label(
                                    "Choose where to create the project. The app will "
                                    "create build/, src/, and 3dmake.toml."
                                ).classes("text-xs text-gray-500")

                                location_input = ui.input(
                                    label="Parent folder",
                                    value=str(Path.home()),
                                    placeholder="/home/user/projects",
                                ).classes("w-full")

                                async def _browse_location() -> None:
                                    await _browse_to_input(location_input)

                                ui.button(
                                    "Browse…",
                                    on_click=_browse_location,
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
                                    ui.button("Create & Save", on_click=create_and_save).props("color=primary size=sm")
                                    ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
                            dlg.open()

                        def _open_existing_project_dialog(
                            parent_dialog: ui.dialog,
                        ) -> None:
                            with ui.dialog() as dlg, ui.card().classes("w-[34rem]"):
                                ui.label("Use Existing Project").classes("text-base font-semibold")
                                ui.label(
                                    "Select an existing project folder. Missing build/, "
                                    "src/, or 3dmake.toml will be created automatically."
                                ).classes("text-xs text-gray-500")

                                existing_input = ui.input(
                                    label="Project folder",
                                    placeholder="/home/user/projects/my-model-project",
                                ).classes("w-full")

                                async def _browse_existing() -> None:
                                    await _browse_to_input(existing_input)

                                ui.button(
                                    "Select Existing…",
                                    on_click=_browse_existing,
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
                                    ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
                            dlg.open()

                        def _open_first_save_prompt() -> None:
                            with ui.dialog() as dlg, ui.card().classes("w-[28rem]"):
                                ui.label("Save Into a 3dmake Project").classes("text-base font-semibold")
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
                                        on_click=lambda: _open_existing_project_dialog(dlg),
                                    ).props("outline size=sm")
                                    ui.button("Cancel", on_click=dlg.close).props("flat size=sm")
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
                            'flat size=sm aria-label="Load file into editor"'
                        )
                        ui.button("💾 Save", on_click=save_editor).props(
                            'outline size=sm aria-label="Save editor contents"'
                        )

                        async def _open_toolbar_stl() -> None:
                            await _open_stl_viewer(
                                Path((file_input.value or "").strip()),
                                _log_ref[0],
                            )

                        view_stl_btn = ui.button(
                            "🔲 View STL",
                            on_click=_open_toolbar_stl,
                        ).props('flat size=sm aria-label="View STL file in 3D viewer"')
                        view_stl_btn.set_visibility(False)

                        def _toggle_view_stl_btn(e) -> None:
                            value = (e.value or "").strip().lower()
                            view_stl_btn.set_visibility(value.endswith(".stl"))

                        file_input.on_value_change(_toggle_view_stl_btn)

                editor = ui.codemirror(
                    value="// Edit your OpenSCAD model here\n\ncube([10, 10, 10]);\n",
                    language="C++",
                    theme=_DEFAULT_THEME,
                ).classes("w-full font-mono text-sm")
                _apply_word_wrap(_wrap_state["enabled"])
                ui.run_javascript("""
                    var cm = document.querySelector('#section-editor .cm-content');
                    if (cm) {
                      cm.setAttribute('aria-label', 'OpenSCAD model source editor');
                      cm.setAttribute('aria-multiline', 'true');
                      cm.setAttribute('aria-roledescription', 'code editor');
                      cm.setAttribute('aria-description', 'Press Escape to exit the editor and return to toolbar. Tab key inserts indentation.');
                    }
                    """)

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
                    .props('outlined options-dense aria-label="Editor and application color theme selector"')
                    .classes("w-full")
                )

                def _on_theme_change(e):
                    editor.set_theme(_theme_options[e.value])
                    _apply_site_theme(e.value)

                theme_select.on_value_change(_on_theme_change)

                # Small colour swatches so users can preview before selecting
                ui.label("Current theme preview:").classes("text-xs text-gray-400 mt-2")
                with (
                    ui.row()
                    .classes("gap-1 flex-wrap mt-1 swatch-row")
                    .props('aria-hidden="true" role="presentation"') as _swatch_row
                ):
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
            ui.run_javascript(_swatch_js)

            # 4. Custom Command card ───────────────────────────────────────────
            with ui.card().classes("cmd-card").props('id="section-cmd" aria-label="Custom command" role="region"'):
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
                        if _log_ref[0] is None:
                            return
                        await _stream_command(
                            cmd,
                            _log_ref[0],
                            show_popup=True,
                            popup_title="Custom Command Output",
                            ui_container=_popup_host_ref[0],
                        )

                    ui.button("Run", on_click=execute_custom).props("color=primary size=sm").classes("cmd-run-btn")

            # 5. Output Log card ───────────────────────────────────────────────
            with ui.card().classes("log-card").props('id="section-log" aria-label="Output log" role="region"'):
                with (
                    ui.row().classes("w-full items-center justify-between").style("flex-shrink: 0; margin-bottom: 4px;")
                ):
                    ui.label("Output Log").classes("text-base font-semibold")
                    ui.button("Clear", on_click=lambda: output_log.clear()).props("flat size=sm")

                output_log = ui.log(max_lines=500).classes("w-full font-mono text-xs")
                _log_ref[0] = output_log
                if _3dm_path:
                    output_log.push(f"[info] 3dm binary found at: {_3dm_path}")
                else:
                    output_log.push(
                        "[warn] 3dm not found. Install from https://github.com/tdeck/3dmake "
                        "then set THREE_DM_PATH or add to PATH."
                    )

                ui.run_javascript("""
                    const logEl = document.querySelector('#section-log .nicegui-log');
                    if (logEl) {
                      logEl.setAttribute('role', 'log');
                      logEl.setAttribute('aria-live', 'polite');
                      logEl.setAttribute('aria-atomic', 'false');
                    }
                    """)

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
          <td style="padding:.35rem .6rem;">Move focus to the next named section (cycles: File → Command Options → Quick Actions → Image Export → Settings → Editor → Command → Log → header → repeat)</td></tr>
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
          <td style="padding:.35rem .6rem;">Save the current editor content to disk from anywhere in the app</td></tr>
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
        'section-options',
    'section-quick',
        'section-image',
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
            e.preventDefault();
            // Always attempt save with Ctrl+S.
            const saveBtn = document.querySelector('#section-editor button[title*="Save"], #section-editor button:nth-of-type(2)');
            if (saveBtn) saveBtn.click();
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

    document.addEventListener('focusin', function(e) {
        if (e.target && e.target.closest('.cm-editor')) {
            var liveRegion = document.getElementById('a11y-live');
            if (liveRegion) {
                liveRegion.textContent = '';
                requestAnimationFrame(function() {
                    liveRegion.textContent = 'Code editor focused. Tab key inserts indentation. Press Escape to exit the editor.';
                });
            }
        }
    });

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


def _build_cli_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the GUI launcher.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser supporting help aliases and ``--version``.
    """
    parser = argparse.ArgumentParser(
        prog="3dmake-gui",
        description="Launch the 3DMake NiceGUI frontend.",
        add_help=False,
    )
    parser.add_argument(
        "-h",
        "--help",
        "--hrlp",
        action="help",
        help="show this help message and exit",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="show the application version and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Launch the NiceGUI application process.

    Parameters
    ----------
    argv : list[str] or None, optional
        Optional command-line arguments. When ``None``, uses
        ``sys.argv[1:]``.
    """
    parser = _build_cli_parser()
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        print(__version__)
        return

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

"""GUI -> CLI contract: clicking each button must run the exact, valid 3dm argv.

Uses NiceGUI's in-process user simulation (no browser). ``run_command_async`` and
``launch_in_terminal`` are replaced by recorders, so this asserts precisely what
the GUI would hand to the operating system.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nicegui import ui
from nicegui.testing.user_interaction import UserInteraction
import pytest

from tdmake_gui_wrapper import app as gui
from tdmake_gui_wrapper import cli

if TYPE_CHECKING:
    from pathlib import Path

    from nicegui.testing import User

FAKE_BIN = "/fake/3dm"
DEFAULT_CAMERA_ANGLES = 3


@pytest.fixture
def rec(user: User, monkeypatch, tmp_path: Path):
    # The NiceGUI test runner resets routes per test; re-register the page.
    ui.page("/")(gui.index)
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "3dmake.toml").write_text('project_name = "p"\n')
    scad = proj / "src" / "main.scad"
    scad.write_text("cube(1);\n")

    streamed: list[list[str]] = []
    terminals: list[tuple[list[str], str | None]] = []

    async def fake_run(cmd, cwd=None, env=None):
        assert not isinstance(cmd, str), "GUI must never hand 3dm a shell string"
        streamed.append(list(cmd))
        yield "[stdout] ok"
        yield "[done] 0"

    def fake_terminal(cmd, cwd=None):
        assert not isinstance(cmd, str)
        terminals.append((list(cmd), cwd))
        return True

    monkeypatch.setattr(gui, "run_command_async", fake_run)
    monkeypatch.setattr(gui, "launch_in_terminal", fake_terminal)
    monkeypatch.setattr(gui, "find_3dm_binary", lambda: FAKE_BIN)
    return {"proj": proj, "scad": scad, "streamed": streamed, "terminals": terminals}


async def _open(user: User, rec) -> None:
    await user.open("/")
    user.find(kind=ui.input, content="File or project directory").type(str(rec["scad"]))


async def _click(user: User, label: str) -> None:
    """Click the one button whose text is exactly ``label`` (substring matches would be ambiguous)."""
    exact = [b for b in user.find(kind=ui.button).elements if getattr(b, "text", None) == label]
    assert len(exact) == 1, f"expected exactly one button labelled {label!r}, found {len(exact)}"
    UserInteraction(user, {exact[0]}, None).click()
    await asyncio.sleep(0.05)  # let async handlers finish


# label -> verbs (streamed, with the selected .scad as input unless None)
STREAMED_WITH_FILE = {
    "Describe (Info)": ["info"],
    "Build STL": ["build"],
    "Slice": ["slice"],
    "Orient": ["orient"],
    "Preview": ["preview"],
    "Preview + Slice": ["preview", "slice"],
    "Preview + Print": ["preview", "print"],
    "Orient + Preview": ["orient", "preview"],
    "Build + Slice": ["build", "slice"],
    "Full Pipeline": ["build", "orient", "slice"],
}


@pytest.mark.parametrize(("label", "verbs"), STREAMED_WITH_FILE.items())
async def test_quick_action_runs_exact_argv(user: User, rec, label, verbs):
    await _open(user, rec)
    await _click(user, label)
    assert rec["streamed"], f"{label}: nothing was executed"
    argv = rec["streamed"][-1]
    assert argv[0] == FAKE_BIN
    assert argv[1:] == cli.build_argv(verbs, cli.Options(view="3sil"), rec["scad"])
    assert not rec["terminals"]


async def test_print_runs_print_verb(user: User, rec):
    await _open(user, rec)
    await _click(user, "Print")
    assert rec["streamed"][-1][1:] == ["-v", "3sil", "print"]


async def test_new_project_uses_terminal_because_3dm_new_prompts(user: User, rec):
    await _open(user, rec)
    await _click(user, "New Project")
    assert not rec["streamed"]
    argv, cwd = rec["terminals"][-1]
    assert argv == [FAKE_BIN, "new"]
    assert cwd == str(rec["proj"])


@pytest.mark.parametrize(
    ("label", "verb"),
    [
        ("List Libraries", "list-libraries"),
        ("Install Libraries", "install-libraries"),
        ("List Profiles", "list-profiles"),
        ("List Overlays", "list-overlays"),
        ("Version Info", "version"),
        ("3dm Help", "help"),
        ("Test Connection", "test-connect"),
    ],
)
async def test_settings_buttons_stream_real_verbs(user: User, rec, label, verb):
    await _open(user, rec)
    await _click(user, label)
    assert rec["streamed"][-1] == [FAKE_BIN, verb]


@pytest.mark.parametrize(
    ("label", "verbs", "extra"),
    [
        ("Edit Profile", ["edit-profile"], []),
        ("Edit AI Prompt", ["edit-prompt"], []),
        ("Edit Model (3dm)", ["edit-model"], []),
        ("Edit Global Config (3dm)", ["edit-global-config"], []),
        ("Clone Profile", ["clone-profile"], []),
        ("Edit Profile GCODE", ["edit-profile-gcode"], []),
    ],
)
async def test_edit_buttons_run_real_edit_verbs_in_terminal(user: User, rec, label, verbs, extra):
    await _open(user, rec)
    await _click(user, label)
    assert not rec["streamed"]
    argv, _cwd = rec["terminals"][-1]
    assert argv[0] == FAKE_BIN
    assert verbs[0] in argv
    assert argv[-1] == verbs[0]  # verb is last (no input file)


async def test_image_export_runs_image_with_selected_options(user: User, rec):
    await _open(user, rec)
    await _click(user, "Run Image Export")
    argv = rec["streamed"][-1]
    assert argv[0] == FAKE_BIN
    assert "image" in argv
    assert argv.count("-a") == DEFAULT_CAMERA_ANGLES  # default three camera angles
    assert argv[argv.index("--colorscheme") + 1] == "slicer_dark"
    assert argv[argv.index("--image-size") + 1] == "1080x720"
    assert argv[-1] == str(rec["scad"])


async def test_info_can_use_image_settings(user: User, rec):
    await _open(user, rec)
    switch = next(e for e in user.find(kind=ui.switch).elements if "Describe (info)" in e.text)
    switch.set_value(True)
    await _click(user, "Describe (Info)")
    argv = rec["streamed"][-1]
    assert argv.count("-a") == DEFAULT_CAMERA_ANGLES
    assert "--colorscheme" in argv
    assert "--image-size" in argv
    assert argv[-2:] == ["info", str(rec["scad"])]


async def test_info_without_switch_does_not_override_config(user: User, rec):
    await _open(user, rec)
    await _click(user, "Describe (Info)")
    argv = rec["streamed"][-1]
    assert "-a" not in argv
    assert "--colorscheme" not in argv
    assert "--image-size" not in argv

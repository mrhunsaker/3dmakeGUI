"""Tests for the spec-driven 3dm command builder (src/tdmake_gui_wrapper/cli.py)."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

import pytest

from tdmake_gui_wrapper import cli
from tdmake_gui_wrapper.cli import CliError, Options, build_argv, needs_terminal, parse_custom_command
from tdmake_gui_wrapper.core import run_command_async


# ── spec sanity ─────────────────────────────────────────────────────────────
def test_spec_covers_every_public_action():
    expected = {
        "setup", "new", "build", "orient", "info", "image", "preview", "slice", "print",
        "list-profiles", "list-overlays", "edit-model", "edit-overlay", "edit-profile",
        "clone-profile", "edit-profile-gcode", "edit-prompt", "edit-global-config",
        "list-libraries", "install-libraries", "test-connect", "install-profile",
        "self-update", "help", "version",
    }  # fmt: skip
    assert set(cli.action_names()) == expected


def test_spec_has_all_global_flags():
    flags = {f for o in cli.load_spec()["options"] for f in o["flags"]}
    for f in ["-s", "--scale-x", "--sy", "--scale-z", "-m", "-v", "-p", "-o", "-a", "-i", "-c",
              "--colorscheme", "--image-size", "--debug"]:  # fmt: skip
        assert f in flags


# ── argv construction: every previously-broken GUI command ──────────────────
@pytest.mark.parametrize(
    ("verbs", "expected"),
    [
        (["build", "slice"], ["build", "slice"]),
        (["build", "orient", "slice"], ["build", "orient", "slice"]),
        (["image"], ["image"]),
        (["list-libraries"], ["list-libraries"]),
        (["install-libraries"], ["install-libraries"]),
        (["list-profiles"], ["list-profiles"]),
        (["list-overlays"], ["list-overlays"]),
        (["test-connect"], ["test-connect"]),
        (["new"], ["new"]),
    ],
)
def test_plain_verbs(verbs, expected):
    assert build_argv(verbs) == expected


def test_all_flags_emitted_canonically_before_verbs():
    opts = Options(
        model="lid", view="topsil", profile="prusa_MK4", overlays=["supports", "PETG"], scale="150%",
        angles=["front", "top"], interactive=True, copies=3, colorscheme="light_on_dark",
        image_size="640x480", debug=True,
    )  # fmt: skip
    assert build_argv(["info"], opts) == [
        "-m", "lid", "-v", "topsil", "-p", "prusa_MK4", "-o", "supports", "-o", "PETG", "-s", "150%",
        "-a", "front", "-a", "top", "--colorscheme", "light_on_dark", "--image-size", "640x480",
        "-c", "3", "-i", "--debug", "info",
    ]  # fmt: skip


def test_per_axis_scale():
    argv = build_argv(["slice"], Options(scale_x="2", scale_z="50%"))
    assert argv == ["--scale-x", "2", "--scale-z", "50%", "slice"]


def test_values_are_single_argv_items_never_shell_split():
    evil = "x; rm -rf ~ && echo"
    assert build_argv(["slice"], Options(profile=evil)) == ["-p", evil, "slice"]
    assert build_argv(["build"], input_file="my model (1).scad")[-1] == "my model (1).scad"


# ── validation mirrors 3dm.py ───────────────────────────────────────────────
@pytest.mark.parametrize(
    ("verbs", "opts", "infile", "fragment"),
    [
        ([], None, None, "Must provide"),
        (["images"], None, None, "Unknown action"),
        (["measure-mesh"], None, None, "Unknown action"),  # internal action
        (["setup", "build"], None, None, "can only be used on its own"),
        (["info", "slice"], None, None, "cannot be followed"),
        (["image", "print"], None, None, "cannot be followed"),
        (["build"], Options(scale="2", scale_x="3"), None, "Cannot use 'scale'"),
        (["build"], Options(model="a"), "b.scad", "Cannot select a model name"),
        (["list-profiles"], None, "b.stl", "does not take an input file"),
        (["build"], None, "b.stl", "does not accept an input file of type .stl"),
        (["list-profiles"], None, "b.scad", "can only be used on its own"),  # 3dm's own known edge case
        (["slice"], None, "b.txt", "does not accept an input file of type .txt"),
        (["image"], Options(angles=["sideways"]), None, "viewpoint angle"),
        (["image"], Options(colorscheme="neon"), None, "color scheme"),
        (["image"], Options(image_size="big"), None, "Image size"),
        (["build"], Options(scale="abc"), None, "Invalid value"),
        (["slice"], Options(copies=0), None, "at least 1"),
    ],
)
def test_rejections_match_3dm(verbs, opts, infile, fragment):
    with pytest.raises(CliError, match=fragment):
        build_argv(verbs, opts, infile)


def test_info_before_slice_is_fine_but_chain_order_is_3dms_not_ours():
    # slice precedes print internally; typed order must not matter
    assert build_argv(["print", "slice"]) == ["print", "slice"]
    with pytest.raises(CliError):
        build_argv(["slice", "info"])  # info is last_in_chain and precedes slice


@pytest.mark.parametrize("verbs", [["slice"], ["info"], ["preview", "print"], ["orient"], ["image"]])
def test_scad_input_is_accepted_because_3dm_adds_build(verbs):
    assert build_argv(verbs, input_file="model.scad")[-1] == "model.scad"


def test_input_file_modes():
    assert build_argv(["slice"], input_file=Path("turtle.stl")) == ["slice", "turtle.stl"]
    assert build_argv(["print"], input_file="job.gcode")[-1] == "job.gcode"
    assert build_argv(["install-profile"], input_file="x.ini") == ["install-profile", "x.ini"]


# ── terminal routing is derived from the source, not guessed ────────────────
@pytest.mark.parametrize(
    "verbs",
    ["setup", "new", "edit-model", "edit-overlay", "edit-profile", "clone-profile",
     "edit-profile-gcode", "edit-prompt", "edit-global-config", "install-profile"],
)  # fmt: skip
def test_interactive_actions_need_terminal(verbs):
    assert needs_terminal([verbs])


@pytest.mark.parametrize(
    "verb",
    ["build", "slice", "print", "orient", "preview", "image", "list-profiles", "list-libraries",
     "test-connect", "version", "help", "self-update"],
)  # fmt: skip
def test_batch_actions_stream(verb):
    assert not needs_terminal([verb])


def test_info_needs_terminal_only_when_interactive():
    assert not needs_terminal(["info"], Options())
    assert needs_terminal(["info"], Options(interactive=True))


# ── custom command ──────────────────────────────────────────────────────────
def test_custom_command_replaces_3dm_with_binary_and_validates():
    assert parse_custom_command("3dm build slice -p 'my profile'", "/opt/3dm") == [
        "/opt/3dm", "build", "slice", "-p", "my profile",
    ]  # fmt: skip
    with pytest.raises(CliError, match="Unknown option"):
        parse_custom_command("3dm build --slice", "/opt/3dm")
    with pytest.raises(CliError, match="Unknown action"):
        parse_custom_command("3dm libraries", "/opt/3dm")
    assert cli.tokens_need_terminal(["-i", "info"])


# ── real subprocess: argv reaches the binary byte-for-byte ──────────────────
@pytest.mark.skipif(sys.platform.startswith("win"), reason="uses a POSIX shim script")
async def test_argv_reaches_binary_unmodified_without_shell(tmp_path: Path):
    log = tmp_path / "argv.txt"
    shim = tmp_path / "3dm"
    shim.write_text(
        f"#!{sys.executable}\nimport sys, pathlib\npathlib.Path({str(log)!r}).write_text(chr(0).join(sys.argv[1:]))\n"
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

    tricky = "name with spaces; $(touch pwned) `id`"
    argv = cli.with_binary(str(shim), build_argv(["slice"], Options(profile=tricky, overlays=["a b"]), "m.stl"))
    lines = [line async for line in run_command_async(argv, cwd=str(tmp_path))]

    assert lines[-1] == "[done] 0"
    assert log.read_text().split("\0") == ["-p", tricky, "-o", "a b", "slice", "m.stl"]
    assert not (tmp_path / "pwned").exists()
    assert os.environ.get("PWNED") is None

"""Guards: the GUI must keep a control for every 3dm action and the spec must match 3dmake."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from tdmake_gui_wrapper import cli

APP_SRC = (Path(cli.__file__).parent / "app.py").read_text(encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]


def _gui_verbs() -> set[str]:
    """Verbs the GUI can emit: ``"3dm <verbs...>"`` literals plus ``build_argv([...])`` lists."""
    found: set[str] = set()
    for m in re.finditer(r'"3dm ([a-z][a-z -]*?)(?: \{file\})?"', APP_SRC):
        found.update(m.group(1).split())
    for m in re.finditer(r"build_argv\(\s*\[([^\]]*)\]", APP_SRC):
        found.update(re.findall(r'"([a-z-]+)"', m.group(1)))
    return found


def test_every_public_3dm_action_has_a_gui_control():
    missing = sorted(set(cli.action_names()) - _gui_verbs())
    assert not missing, f"3dm actions with no GUI control: {missing}"


def test_gui_never_builds_shell_strings_for_3dm():
    assert 'cmd.replace("3dm "' not in APP_SRC
    assert "create_subprocess_shell" not in APP_SRC


def test_every_global_flag_is_emitted_by_the_builder():
    emitted = set()
    opts = cli.Options(
        model="m", view="3sil", profile="p", overlays=["o"], scale="2", angles=["front"],
        interactive=True, copies=2, colorscheme="slicer_dark", image_size="1x1", debug=True,
    )  # fmt: skip
    emitted |= {t for t in cli.build_argv(["info"], opts) if t.startswith("-")}
    emitted |= {t for t in cli.build_argv(["slice"], cli.Options(scale_x="1", scale_y="1", scale_z="1")) if t.startswith("-")}
    spec_flags = {tuple(o["flags"]) for o in cli.load_spec()["options"] if o["dest"] not in {"help", "h", "version"}}
    uncovered = [f for f in spec_flags if not (set(f) & emitted)]
    assert not uncovered, f"flags the GUI cannot emit: {uncovered}"


@pytest.mark.skipif(not os.environ.get("THREEDM_E2E_SRC"), reason="needs a tdeck/3dmake checkout")
def test_committed_spec_matches_3dmake_source():
    res = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "sync_spec.py"), os.environ["THREEDM_E2E_SRC"], "--check"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert res.returncode == 0, "3dm spec drift: run scripts/sync_spec.py\n" + res.stderr

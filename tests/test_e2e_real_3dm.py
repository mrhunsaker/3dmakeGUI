"""End-to-end tests that drive a REAL ``3dm`` through the GUI's argv builder.

Opt-in. Provide a launcher for 3dm and a tdeck/3dmake checkout (for fixtures and
default_config)::

    THREEDM_E2E_BIN=/path/to/3dm THREEDM_E2E_SRC=/path/to/3dmake pytest tests/test_e2e_real_3dm.py

The launcher may be a shell shim, e.g. ``exec python /path/3dmake/3dm.py "$@"``.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tdmake_gui_wrapper import cli
from tdmake_gui_wrapper.cli import CliError, Options, build_argv

BIN = os.environ.get("THREEDM_E2E_BIN")
SRC = Path(os.environ.get("THREEDM_E2E_SRC", ""))

pytestmark = pytest.mark.skipif(
    not (BIN and SRC.is_dir()), reason="set THREEDM_E2E_BIN and THREEDM_E2E_SRC to run against real 3dm"
)


@pytest.fixture
def env(tmp_path: Path):
    cfg = tmp_path / "cfg"
    shutil.copytree(SRC / "default_config", cfg)
    (cfg / "defaults.toml").write_text('printer_profile = "prusa_i3_MK3S"\nview = "3sil"\n')
    work = tmp_path / "work"
    work.mkdir()
    return {**os.environ, "THREEDMAKE_CONFIG_DIR": str(cfg)}, work


def run(env, argv: list[str]) -> subprocess.CompletedProcess:
    full = cli.with_binary(BIN, argv)
    return subprocess.run(full, cwd=env[1], env=env[0], capture_output=True, text=True, timeout=120, check=False)


def test_spec_matches_real_help_output(env):
    out = run(env, ["help"]).stdout
    listed = set(re.findall(r"^    ([a-z][a-z-]*)\s{2,}", out, flags=re.M))
    assert listed == set(cli.action_names())


@pytest.mark.parametrize("verb", ["version", "list-profiles", "list-overlays"])
def test_isolated_actions_succeed(env, verb):
    res = run(env, build_argv([verb]))
    assert res.returncode == 0, res.stdout + res.stderr


def test_info_with_scale_and_input_file(env):
    stl = SRC / "test_fixtures" / "hexagon.stl"
    res = run(env, build_argv(["info"], Options(scale="2"), stl))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Mesh size: x=40.00" in res.stdout


def test_orient_input_file_produces_oriented_stl(env):
    stl = SRC / "test_fixtures" / "upright_T.stl"
    res = run(env, build_argv(["orient"], None, stl))
    assert res.returncode == 0, res.stdout + res.stderr
    assert (env[1] / "upright_T-oriented.stl").exists()


@pytest.mark.parametrize(
    ("verbs", "opts", "infile"),
    [
        (["info"], Options(scale="2", scale_x="3"), "hexagon.stl"),
        (["info", "slice"], None, "hexagon.stl"),
        (["setup", "build"], None, None),
        (["info"], Options(model="a"), "hexagon.stl"),
    ],
)
def test_builder_rejections_match_real_3dm_messages(env, verbs, opts, infile):
    """What the GUI refuses must be exactly what 3dm itself refuses (same message)."""
    path = SRC / "test_fixtures" / infile if infile else None
    with pytest.raises(CliError) as ours:
        build_argv(verbs, opts, path)
    # bypass our validation to learn what 3dm says for the same request
    raw: list[str] = []
    if opts:
        for flag, val in [("-s", opts.scale), ("--scale-x", opts.scale_x), ("-m", opts.model)]:
            if val:
                raw += [flag, val]
    raw += verbs + ([str(path)] if path else [])
    theirs = run(env, raw)
    assert theirs.returncode != 0
    assert str(ours.value) in theirs.stdout + theirs.stderr

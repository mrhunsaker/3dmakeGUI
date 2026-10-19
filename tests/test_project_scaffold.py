"""Projects created or repaired by the GUI must be valid for real 3dm."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tdmake_gui_wrapper import app as gui


def test_manual_fallback_writes_what_3dm_new_writes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gui, "find_3dm_binary", lambda: None)
    root = tmp_path / "p"
    gui._ensure_project_layout(root, "p")
    assert (root / "3dmake.toml").read_text() == "strict_warnings = true\n"
    assert (root / "src").is_dir()
    assert (root / "build").is_dir()


def test_legacy_gui_toml_is_repaired(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gui, "find_3dm_binary", lambda: None)
    cfg = tmp_path / "3dmake.toml"
    cfg.write_text('[project]\nname = "x"\n')
    gui._ensure_project_layout(tmp_path, "x")
    assert cfg.read_text() == "strict_warnings = true\n"


def test_user_edited_toml_is_never_touched(tmp_path: Path):
    cfg = tmp_path / "3dmake.toml"
    cfg.write_text('printer_profile = "mine"\n[project]\nname = "x"\n')
    assert gui._repair_legacy_project_toml(cfg) is False
    assert "mine" in cfg.read_text()


@pytest.mark.skipif(
    not (os.environ.get("THREEDM_E2E_BIN") and os.environ.get("THREEDM_E2E_SRC")),
    reason="needs real 3dm (THREEDM_E2E_BIN / THREEDM_E2E_SRC)",
)
def test_scaffold_with_real_3dm_new_yields_a_project_3dm_accepts(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / "cfg"
    shutil.copytree(Path(os.environ["THREEDM_E2E_SRC"]) / "default_config", cfg_dir)
    (cfg_dir / "defaults.toml").write_text('printer_profile = "prusa_i3_MK3S"\nview = "3sil"\n')
    monkeypatch.setenv("THREEDMAKE_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(gui, "find_3dm_binary", lambda: os.environ["THREEDM_E2E_BIN"])

    root = tmp_path / "made"
    gui._ensure_project_layout(root, "made")
    assert (root / "src" / "main.scad").exists()  # only real `3dm new` creates the template model

    stl = Path(os.environ["THREEDM_E2E_SRC"]) / "test_fixtures" / "hexagon.stl"
    res = subprocess.run(
        [os.environ["THREEDM_E2E_BIN"], "info", str(stl)], cwd=root, capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.skipif(not os.environ.get("THREEDM_E2E_BIN"), reason="needs real 3dm")
def test_legacy_toml_really_breaks_3dm_and_repair_fixes_it(tmp_path: Path):
    """Regression proof for the bug the repair exists for."""
    src = Path(os.environ["THREEDM_E2E_SRC"])
    cfg_dir = tmp_path / "cfg"
    shutil.copytree(src / "default_config", cfg_dir)
    (cfg_dir / "defaults.toml").write_text('printer_profile = "prusa_i3_MK3S"\nview = "3sil"\n')
    env = {**os.environ, "THREEDMAKE_CONFIG_DIR": str(cfg_dir)}
    proj = tmp_path / "legacy"
    (proj / "src").mkdir(parents=True)
    (proj / "3dmake.toml").write_text('[project]\nname = "legacy"\n')
    cmd = [os.environ["THREEDM_E2E_BIN"], "info", str(src / "test_fixtures" / "hexagon.stl")]

    broken = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, check=False)
    assert broken.returncode != 0
    assert "unexpected keyword argument 'project'" in broken.stderr + broken.stdout

    assert gui._repair_legacy_project_toml(proj / "3dmake.toml")
    fixed = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, check=False)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr

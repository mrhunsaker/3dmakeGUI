import os
import sys
from pathlib import Path

import pytest

from tdmake_gui_wrapper.core import (
    _append_path_to_shell_file,
    find_3dm_binary,
    get_3dmake_config_dir,
    get_3dmake_defaults_toml_path,
    get_packaged_executable_dir,
    install_directory_to_user_path,
    is_directory_on_path,
    launch_in_terminal,
    resolve_3dm_binary_path,
    run_command_async,
    run_command_sync,
)


@pytest.mark.asyncio
async def test_run_command_async_interleaves_streams():
    cmd = (
        f'"{sys.executable}" -c "import sys,time; '
        "print('out1'); sys.stdout.flush(); "
        "time.sleep(0.05); "
        "print('err1', file=sys.stderr); sys.stderr.flush(); "
        "time.sleep(0.05); "
        "print('out2'); sys.stdout.flush(); "
        "print('err2', file=sys.stderr); sys.stderr.flush(); "
        '"'
    )

    lines = [line async for line in run_command_async(cmd)]

    done_idx = next(i for i, line in enumerate(lines) if line.startswith("[done]"))
    assert any(line.startswith("[stdout]") for line in lines[:done_idx])
    assert any(line.startswith("[stderr]") for line in lines[:done_idx])
    assert all(not line.startswith("[done]") for line in lines[:done_idx])


@pytest.mark.asyncio
async def test_run_command_async_emits_done_return_code_on_failure():
    cmd = f'"{sys.executable}" -c "import sys; sys.stderr.write(\'boom\\n\'); sys.exit(3)"'

    lines = [line async for line in run_command_async(cmd)]

    assert any(line.startswith("[stderr] boom") for line in lines)
    assert lines[-1] == "[done] 3"


def test_run_command_sync_returns_stdout_stderr_and_code():
    cmd = f'"{sys.executable}" -c "import sys; ' "print('hello'); " "print('oops', file=sys.stderr); " "sys.exit(0)" '"'
    stdout, stderr, code = run_command_sync(cmd)

    assert "hello" in stdout
    assert "oops" in stderr
    assert code == 0


def test_get_packaged_executable_dir_returns_none_when_not_frozen(monkeypatch):
    monkeypatch.delattr("tdmake_gui_wrapper.core.sys.frozen", raising=False)
    assert get_packaged_executable_dir() is None


def test_get_packaged_executable_dir_when_frozen(monkeypatch, tmp_path: Path):
    exe = tmp_path / "dist" / "3dmake-gui"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.frozen", True, raising=False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.executable", str(exe))

    assert get_packaged_executable_dir() == exe.resolve().parent


def test_is_directory_on_path_true(monkeypatch, tmp_path: Path):
    target = (tmp_path / "bin").resolve()
    target.mkdir(parents=True)
    monkeypatch.setenv("PATH", f"{target}{os.pathsep}/usr/bin")

    assert is_directory_on_path(target) is True


def test_is_directory_on_path_false(monkeypatch, tmp_path: Path):
    target = (tmp_path / "missing").resolve()
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    assert is_directory_on_path(target) is False


def test_append_path_to_shell_file_is_idempotent(tmp_path: Path):
    shell_file = tmp_path / ".bashrc"
    target = tmp_path / "app"
    target.mkdir()

    _append_path_to_shell_file(shell_file, target)
    _append_path_to_shell_file(shell_file, target)

    text = shell_file.read_text(encoding="utf-8")
    assert text.count("# Added by 3dmake-gui") == 1
    assert text.count(f'export PATH="{target}:$PATH"') == 1


def test_install_directory_to_user_path_missing_dir(tmp_path: Path):
    missing = tmp_path / "nope"
    ok, message = install_directory_to_user_path(missing)

    assert ok is False
    assert "Directory does not exist" in message


def test_install_directory_to_user_path_short_circuit_when_already_on_path(monkeypatch, tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    monkeypatch.setattr("tdmake_gui_wrapper.core.is_directory_on_path", lambda _p: True)

    ok, message = install_directory_to_user_path(target)

    assert ok is True
    assert "already on PATH" in message


def test_install_directory_to_user_path_delegates_to_posix(monkeypatch, tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    monkeypatch.setattr("tdmake_gui_wrapper.core.is_directory_on_path", lambda _p: False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "linux")
    monkeypatch.setattr(
        "tdmake_gui_wrapper.core._install_directory_to_posix_user_path",
        lambda _p: (True, "ok-posix"),
    )

    assert install_directory_to_user_path(target) == (True, "ok-posix")


def test_install_directory_to_user_path_delegates_to_windows(monkeypatch, tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    monkeypatch.setattr("tdmake_gui_wrapper.core.is_directory_on_path", lambda _p: False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "win32")
    monkeypatch.setattr(
        "tdmake_gui_wrapper.core._install_directory_to_windows_user_path",
        lambda _p: (True, "ok-win"),
    )

    assert install_directory_to_user_path(target) == (True, "ok-win")


def test_resolve_3dm_binary_path_with_folder(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "3dm"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")

    resolved = resolve_3dm_binary_path(str(tmp_path))
    assert resolved == str(exe.resolve())


def test_resolve_3dm_binary_path_with_direct_file(tmp_path: Path):
    exe = tmp_path / "3dm"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")

    resolved = resolve_3dm_binary_path(str(exe))
    assert resolved == str(exe.resolve())


def test_find_3dm_binary_prefers_env_override(monkeypatch, tmp_path: Path):
    env_exe = tmp_path / "env" / "3dm"
    env_exe.parent.mkdir(parents=True)
    env_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("THREE_DM_PATH", str(env_exe))
    monkeypatch.setattr("tdmake_gui_wrapper.core.shutil.which", lambda _x: "/usr/bin/3dm")

    assert find_3dm_binary() == str(env_exe.resolve())


def test_find_3dm_binary_uses_path_when_env_absent(monkeypatch):
    monkeypatch.delenv("THREE_DM_PATH", raising=False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.shutil.which", lambda _x: "/usr/bin/3dm")

    assert find_3dm_binary() == "/usr/bin/3dm"


def test_get_3dmake_config_dir_prefers_env(monkeypatch, tmp_path: Path):
    custom = tmp_path / "cfg"
    custom.mkdir()
    monkeypatch.setenv("THREEDMAKE_CONFIG_DIR", str(custom))

    assert get_3dmake_config_dir() == custom.resolve()


def test_get_3dmake_config_dir_windows_from_localappdata(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("THREEDMAKE_CONFIG_DIR", raising=False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    assert get_3dmake_config_dir() == Path(str(tmp_path / "Local")) / "3dmake" / "3dmake"


def test_get_3dmake_config_dir_macos(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("THREEDMAKE_CONFIG_DIR", raising=False)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "darwin")
    monkeypatch.setattr("tdmake_gui_wrapper.core.Path.home", lambda: tmp_path)

    assert get_3dmake_config_dir() == tmp_path / "Library" / "Application Support" / "3dmake"


def test_get_3dmake_defaults_toml_path(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("THREEDMAKE_CONFIG_DIR", str(cfg))

    assert get_3dmake_defaults_toml_path() == cfg.resolve() / "defaults.toml"


def test_launch_in_terminal_returns_false_no_terminal(monkeypatch):
    monkeypatch.setattr("tdmake_gui_wrapper.core.shutil.which", lambda _x: None)
    called = {"count": 0}

    def _fake_popen(*_args, **_kwargs):
        called["count"] += 1
        raise AssertionError("Popen should not be called when no terminal exists")

    monkeypatch.setattr("tdmake_gui_wrapper.core.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "linux")

    assert launch_in_terminal("echo hello") is False
    assert called["count"] == 0


def test_launch_in_terminal_uses_linux_terminal_when_available(monkeypatch):
    popen_calls: list[list[str]] = []

    def fake_which(binary: str):
        if binary == "gnome-terminal":
            return "/usr/bin/gnome-terminal"
        return None

    def fake_popen(args, *unused_args, **unused_kwargs):
        popen_calls.append(args)

        class DummyProc:
            returncode = 0

        return DummyProc()

    monkeypatch.setattr("tdmake_gui_wrapper.core.sys.platform", "linux")
    monkeypatch.setattr("tdmake_gui_wrapper.core.shutil.which", fake_which)
    monkeypatch.setattr("tdmake_gui_wrapper.core.subprocess.Popen", fake_popen)

    assert launch_in_terminal("echo hello") is True
    assert popen_calls
    assert popen_calls[0][0] == "gnome-terminal"

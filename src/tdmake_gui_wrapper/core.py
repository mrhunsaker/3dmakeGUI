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

"""Core utilities for process execution and 3dm binary discovery.

This module centralizes platform-specific behavior used by the GUI layer:

- locating the ``3dm`` executable
- resolving configuration locations
- running commands with streamed or blocking output collection
- optionally adding packaged install directories to the user PATH
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path


def get_packaged_executable_dir() -> Path | None:
    """Return the directory of the packaged executable, when available.

    Returns
    -------
    pathlib.Path or None
        The resolved parent directory of ``sys.executable`` when running from a
        frozen/packaged build (for example, PyInstaller). Returns ``None`` when
        running from source.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def is_directory_on_path(target_dir: Path) -> bool:
    """Check whether a directory already exists on ``PATH``.

    Parameters
    ----------
    target_dir : pathlib.Path
        Directory to check.

    Returns
    -------
    bool
        ``True`` if the normalized target directory matches an entry in
        ``PATH``; otherwise ``False``.
    """
    try:
        target_resolved = target_dir.resolve()
    except OSError:
        target_resolved = target_dir

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry.strip():
            continue
        try:
            candidate = Path(os.path.expanduser(entry)).resolve()
        except OSError:
            candidate = Path(os.path.expanduser(entry))
        if candidate == target_resolved:
            return True
    return False


def _append_path_to_shell_file(shell_file: Path, target_dir: Path) -> None:
    """Append a PATH export line to a shell startup file.

    Parameters
    ----------
    shell_file : pathlib.Path
        Startup file to update (for example ``~/.bashrc``).
    target_dir : pathlib.Path
        Directory to prepend to ``PATH``.

    Notes
    -----
    A marker comment is written to avoid duplicate insertions.
    """
    marker = "# Added by 3dmake-gui"
    export_line = f'export PATH="{target_dir}:$PATH"'

    existing = ""
    if shell_file.exists():
        existing = shell_file.read_text(encoding="utf-8")
        if marker in existing or export_line in existing:
            return

    prefix = "\n" if existing and not existing.endswith("\n") else ""
    shell_file.parent.mkdir(parents=True, exist_ok=True)
    with shell_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{marker}\n{export_line}\n")


def _install_directory_to_windows_user_path(target_dir: Path) -> tuple[bool, str]:
    """Install a directory into the current user's PATH on Windows.

    Parameters
    ----------
    target_dir : pathlib.Path
        Directory to append to the user-level PATH value.

    Returns
    -------
    tuple[bool, str]
        ``(success, message)`` describing the result.
    """
    try:
        import winreg  # type: ignore
    except ImportError:
        return False, "winreg is unavailable on this Python build."

    path_value = ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        ) as key:
            try:
                path_value, _value_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                path_value = ""

            current_parts = [part for part in path_value.split(os.pathsep) if part.strip()]
            normalized = {str(Path(part).expanduser()) for part in current_parts}
            target_text = str(target_dir)
            if target_text not in normalized:
                current_parts.append(target_text)
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(current_parts))
    except OSError as exc:
        return False, f"Could not update Windows PATH: {exc}"

    return (
        True,
        "Added application folder to the user PATH. Sign out and back in for all processes to see the change.",
    )


def _install_directory_to_posix_user_path(target_dir: Path) -> tuple[bool, str]:
    """Install a directory into shell startup files on POSIX systems.

    Parameters
    ----------
    target_dir : pathlib.Path
        Directory to prepend to ``PATH``.

    Returns
    -------
    tuple[bool, str]
        ``(success, message)`` describing the result.

    Notes
    -----
    Linux updates ``.profile``, ``.bashrc``, ``.zprofile``, and ``.zshrc``.
    macOS updates ``.zprofile``, ``.zshrc``, and ``.bash_profile``.
    """
    home = Path.home()
    if sys.platform == "darwin":
        shell_files = [home / ".zprofile", home / ".zshrc", home / ".bash_profile"]
    else:
        shell_files = [
            home / ".profile",
            home / ".bashrc",
            home / ".zprofile",
            home / ".zshrc",
        ]

    try:
        for shell_file in shell_files:
            _append_path_to_shell_file(shell_file, target_dir)
    except OSError as exc:
        return False, f"Could not update shell startup files: {exc}"

    return (
        True,
        "Added application folder to your shell PATH configuration. Open a new terminal session to use it from the command line.",
    )


def install_directory_to_user_path(target_dir: Path) -> tuple[bool, str]:
    """Add an installation directory to the current user's PATH.

    Parameters
    ----------
    target_dir : pathlib.Path
        Directory to add.

    Returns
    -------
    tuple[bool, str]
        ``(success, message)`` describing whether the operation completed.
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return False, f"Directory does not exist: {target_dir}"

    if is_directory_on_path(target_dir):
        return True, "Application folder is already on PATH."

    if sys.platform.startswith("win"):
        return _install_directory_to_windows_user_path(target_dir)

    return _install_directory_to_posix_user_path(target_dir)


def resolve_3dm_binary_path(path_value: str) -> str | None:
    """Resolve a user-supplied path to a concrete ``3dm`` executable.

    Parameters
    ----------
    path_value : str
        Path-like string that may point directly to a binary or to a directory
        containing one.

    Returns
    -------
    str or None
        Absolute path to a detected ``3dm`` binary, or ``None`` if no suitable
        executable can be found.
    """
    if not path_value:
        return None

    raw = os.path.expandvars(os.path.expanduser(path_value.strip()))
    if not raw:
        return None

    candidate = Path(raw)

    # Direct path to binary
    if candidate.is_file():
        return str(candidate.resolve())

    # Folder path that contains the binary in common locations
    if candidate.is_dir():
        possible_binaries = [
            candidate / "3dm",
            candidate / "3dm.exe",
            candidate / "bin" / "3dm",
            candidate / "bin" / "3dm.exe",
            candidate / "Contents" / "MacOS" / "3dm",  # app bundle-style path
        ]
        for binary in possible_binaries:
            if binary.is_file():
                return str(binary.resolve())

    return None


def find_3dm_binary() -> str | None:
    """Locate the ``3dm`` binary using environment and platform heuristics.

    Search order:

    1. ``THREE_DM_PATH`` environment variable (file or directory).
    2. ``PATH`` lookup via :func:`shutil.which`.
    3. Common installation directories on Linux, macOS, and Windows.

    Returns
    -------
    str or None
        Absolute executable path if found, otherwise ``None``.
    """
    # 1. Explicit env override (file or directory)
    env_path = os.environ.get("THREE_DM_PATH")
    resolved_env_path = resolve_3dm_binary_path(env_path or "")
    if resolved_env_path:
        return resolved_env_path

    # 2. PATH lookup
    found = shutil.which("3dm")
    if found:
        return found

    # 3. Common install locations
    candidates = [
        # User-local installs
        Path.home() / "3dmake" / "3dm",
        Path.home() / "3dmake" / "3dm.exe",
        Path.home() / "Applications" / "3dmake",
        Path.home() / "Applications" / "3dmake" / "3dm",
        Path.home() / "Applications" / "3dmake" / "3dm.exe",
        # System-local installs
        Path("/usr/local/bin/3dm"),
        Path("/opt/3dmake/3dm"),
        Path("/Applications/3dmake"),
        Path("/Applications/3dmake/3dm"),
        Path("/Applications/3dmake/3dm.exe"),
        # Windows: %LOCALAPPDATA%\3dmake\3dm.exe
        Path(os.environ.get("ProgramFiles", "")) / "3dmake" / "3dm.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "3dmake" / "3dm.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "3dmake" / "3dm.exe",
    ]
    for candidate in candidates:
        resolved_candidate = resolve_3dm_binary_path(str(candidate))
        if resolved_candidate:
            return resolved_candidate

    return None


def get_3dmake_config_dir() -> Path:
    """Return the active 3dmake configuration directory.

    Resolution precedence:

    1. ``THREEDMAKE_CONFIG_DIR`` environment variable
    2. Platform default location

    Returns
    -------
    pathlib.Path
        Absolute or user-home-relative configuration path.
    """
    env_dir = os.environ.get("THREEDMAKE_CONFIG_DIR")
    if env_dir:
        return Path(os.path.expandvars(os.path.expanduser(env_dir))).resolve()

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "3dmake" / "3dmake"
        return Path.home() / "AppData" / "Local" / "3dmake" / "3dmake"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "3dmake"

    # Linux / Unix default
    return Path.home() / ".config" / "3dmake"


def get_3dmake_defaults_toml_path() -> Path:
    """Return the expected ``defaults.toml`` path for 3dmake.

    Returns
    -------
    pathlib.Path
        Path formed by ``get_3dmake_config_dir() / 'defaults.toml'``.
    """
    return get_3dmake_config_dir() / "defaults.toml"


async def run_command_async(
    cmd: str,
    cwd: str | None = None,
) -> AsyncIterator[str]:
    """Run a shell command and asynchronously stream process output lines.

    Parameters
    ----------
    cmd : str
        Shell command to execute.
    cwd : str or None, optional
        Working directory used for subprocess execution.

    Yields
    ------
    str
        Output records prefixed with ``[stdout]`` or ``[stderr]``. The final
        record is always ``[done] <returncode>``.

    Notes
    -----
    Output is multiplexed through an ``asyncio.Queue`` so stdout and stderr can
    be consumed without blocking each other.
    """
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _enqueue(stream: asyncio.StreamReader, tag: str) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            await queue.put(f"[{tag}] {line.decode(errors='replace').rstrip()}")
        await queue.put(None)

    stdout_task = asyncio.create_task(_enqueue(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(_enqueue(process.stderr, "stderr"))

    done_readers = 0
    while done_readers < 2:
        item = await queue.get()
        if item is None:
            done_readers += 1
            continue
        yield item

    await asyncio.gather(stdout_task, stderr_task)

    await process.wait()
    yield f"[done] {process.returncode}"


def launch_in_terminal(cmd: str) -> bool:
    """Launch a command in a new terminal window.

    Parameters
    ----------
    cmd : str
        Command string to execute.

    Returns
    -------
    bool
        ``True`` when a compatible terminal launcher is found and started;
        ``False`` when no launcher is available or the command is empty.
    """
    if not cmd.strip():
        return False

    if sys.platform.startswith("win"):
        subprocess.Popen(["cmd.exe", "/c", "start", "cmd.exe", "/k", cmd])
        return True

    if sys.platform == "darwin":
        escaped = cmd.replace('"', '\\"')
        subprocess.Popen(
            [
                "osascript",
                "-e",
                f'tell application "Terminal" to do script "{escaped}"',
            ]
        )
        return True

    # Linux/Unix
    for terminal in [
        "x-terminal-emulator",
        "gnome-terminal",
        "xterm",
        "konsole",
        "xfce4-terminal",
    ]:
        if not shutil.which(terminal):
            continue

        hold_cmd = f"{cmd}; exec bash"
        if terminal == "gnome-terminal":
            subprocess.Popen([terminal, "--", "bash", "-lc", hold_cmd])
        elif terminal == "konsole":
            subprocess.Popen([terminal, "-e", "bash", "-lc", hold_cmd])
        else:
            subprocess.Popen([terminal, "-e", f"bash -lc {shlex.quote(hold_cmd)}"])
        return True

    return False


def run_command_sync(cmd: str, cwd: str | None = None) -> tuple[str, str, int]:
    """Run a shell command synchronously and collect captured output.

    Parameters
    ----------
    cmd : str
        Shell command to execute.
    cwd : str or None, optional
        Working directory used for command execution.

    Returns
    -------
    tuple[str, str, int]
        ``(stdout, stderr, returncode)`` in text mode.
    """
    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        cwd=cwd,
    )
    return result.stdout, result.stderr, result.returncode

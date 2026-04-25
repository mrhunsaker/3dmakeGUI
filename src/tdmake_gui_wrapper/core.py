"""Core utilities: 3dm binary discovery and async command execution."""

from __future__ import annotations

import asyncio
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import AsyncIterator, Optional


def resolve_3dm_binary_path(path_value: str) -> Optional[str]:
    """Resolve a user-provided path (file or folder) to a concrete 3dm binary."""
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


def find_3dm_binary() -> Optional[str]:
    """
    Locate the `3dm` binary.

    Search order:
    1. ``THREE_DM_PATH`` environment variable (absolute path to binary).
    2. ``PATH`` via ``shutil.which``.
    3. Common installation directories on Windows and Linux.

    Returns the resolved path string, or ``None`` if not found.
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
    """Return the 3dmake config directory using the same precedence as 3dm."""
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
    """Return the expected path to defaults.toml for the current platform."""
    return get_3dmake_config_dir() / "defaults.toml"


async def run_command_async(
    cmd: str,
    cwd: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Run *cmd* in a shell and yield output lines as they arrive.

    Yields lines prefixed with ``[stdout] `` or ``[stderr] `` so the caller
    can distinguish streams.  A final sentinel line ``[done] <returncode>``
    is always yielded last.

    Parameters
    ----------
    cmd:
        Shell command string to execute.
    cwd:
        Working directory for the subprocess.  Defaults to the current
        working directory.
    """
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    async def _read_stream(stream: asyncio.StreamReader, tag: str):
        while True:
            line = await stream.readline()
            if not line:
                break
            yield f"[{tag}] {line.decode(errors='replace').rstrip()}"

    # Interleave stdout/stderr
    async for chunk in _read_stream(process.stdout, "stdout"):
        yield chunk
    async for chunk in _read_stream(process.stderr, "stderr"):
        yield chunk

    await process.wait()
    yield f"[done] {process.returncode}"


def run_command_sync(cmd: str, cwd: Optional[str] = None) -> tuple[str, str, int]:
    """
    Blocking wrapper around subprocess for simple use cases.

    Returns ``(stdout, stderr, returncode)``.
    """
    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        cwd=cwd,
    )
    return result.stdout, result.stderr, result.returncode

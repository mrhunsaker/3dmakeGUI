#!/usr/bin/env python3
"""Run the project maintenance/release workflow with uv.

Default order:
1. Sync dependencies
2. Lint / format checks
3. Test suite
4. Build docs (strict)
5. Bump version
6. Build PyInstaller binary

Use flags to skip steps when needed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def run_step(command: list[str], repo_root: Path, env: dict[str, str]) -> None:
    """Run a single workflow command in the repository context.

    Parameters
    ----------
    command : list[str]
        Command and arguments to execute.
    repo_root : pathlib.Path
        Repository root used as the working directory.
    env : dict[str, str]
        Environment variables passed to the subprocess.
    """
    print(f"\n==> {' '.join(command)}")
    subprocess.run(command, check=True, cwd=repo_root, env=env)


def ensure_repo_root(repo_root: Path) -> None:
    """Validate that required project files exist at the repository root.

    Parameters
    ----------
    repo_root : pathlib.Path
        Path expected to contain the project metadata and build files.

    Raises
    ------
    SystemExit
        Raised when one or more required files are missing.
    """
    required = ["pyproject.toml", "3dmake_gui.spec", "scripts/bump_version.py"]
    missing = [entry for entry in required if not (repo_root / entry).exists()]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Run this script from the repository root. Missing: {joined}"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the update workflow.

    Returns
    -------
    argparse.Namespace
        Parsed CLI flags controlling which workflow stages are skipped.
    """
    parser = argparse.ArgumentParser(
        description="Run 3dmakeGUI update/build workflow via uv."
    )
    parser.add_argument(
        "--no-checks",
        action="store_true",
        help="Skip lint/format/tests.",
    )
    parser.add_argument(
        "--no-docs",
        action="store_true",
        help="Skip strict docs build.",
    )
    parser.add_argument(
        "--no-bump",
        action="store_true",
        help="Skip scripts/bump_version.py.",
    )
    parser.add_argument(
        "--no-pyinstaller",
        action="store_true",
        help="Skip PyInstaller build.",
    )
    return parser.parse_args()


def main() -> int:
    """Execute the full update workflow based on CLI flags.

    Returns
    -------
    int
        Process exit code, where ``0`` indicates success.
    """
    if shutil.which("uv") is None:
        print("Error: 'uv' was not found in PATH.")
        return 1

    repo_root = Path(__file__).resolve().parent
    ensure_repo_root(repo_root)
    repo_env = os.environ.copy()

    # Avoid uv warning spam when an unrelated venv is active in the shell.
    expected_venv = (repo_root / ".venv").resolve()
    active_venv = repo_env.get("VIRTUAL_ENV")
    if active_venv:
        try:
            active_venv_path = Path(active_venv).resolve()
        except OSError:
            active_venv_path = Path(active_venv)
        if active_venv_path != expected_venv:
            repo_env.pop("VIRTUAL_ENV", None)
            print(
                "Note: active VIRTUAL_ENV does not match this repository; "
                "running uv commands against the project environment."
            )

    args = parse_args()

    steps: list[list[str]] = [
        ["uv", "sync", "--all-extras"],
    ]

    if not args.no_checks:
        steps.extend(
            [
                ["uv", "run", "ruff", "check", "--fix", "src/"],
                ["uv", "run", "black", "src/", "tests/", "scripts/"],
                ["uv", "run", "ruff", "check", "src/"],
                ["uv", "run", "black", "--check", "src/", "tests/", "scripts/"],
                ["uv", "run", "pytest", "-q"],
                ["uv", "run", "pytest", "tests/test_core.py", "-q"],
                ["uv", "run", "pytest", "tests/test_bump_version.py", "-q"],
            ]
        )

    if not args.no_docs:
        steps.extend(
            [
                ["uv", "sync", "--group", "docs"],
                ["uv", "run", "--group", "docs", "mkdocs", "build", "--strict"],
            ]
        )

    if not args.no_bump:
        steps.append(["uv", "run", "python", "scripts/bump_version.py"])

    if not args.no_pyinstaller:
        steps.append(["uv", "run", "pyinstaller", "3dmake_gui.spec"])

    print("Running update workflow from:", repo_root)
    for command in steps:
        run_step(command, repo_root=repo_root, env=repo_env)

    print("\nWorkflow completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}.")
        raise SystemExit(exc.returncode) from exc

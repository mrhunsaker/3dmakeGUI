#!/usr/bin/env python3
"""Run the project maintenance/release workflow with uv.

Default order:
1. Sync dependencies
2. Lint / format checks
3. Test suite
4. Build docs (strict)
5. Update version to today's date-based SemVer-like value
6. Build PyInstaller binary
7. Commit, tag, push, and trigger release workflow

Use flags to skip steps when needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from pathlib import Path

PYPROJECT_PATH = Path("pyproject.toml")
INIT_PATH = Path("src") / "tdmake_gui_wrapper" / "__init__.py"


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


def run_capture(command: list[str], repo_root: Path, env: dict[str, str]) -> str:
    """Run a command and return stripped stdout text."""
    result = subprocess.run(
        command,
        check=True,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_repo_from_remote(remote_url: str) -> tuple[str, str] | None:
    """Parse ``owner/repo`` from a GitHub origin URL."""
    text = remote_url.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", text)
    if not match:
        return None
    return match.group(1), match.group(2)


def _find_matching_run(runs: list[dict], head_sha: str) -> dict | None:
    """Pick the most relevant release workflow run for the pushed tag SHA."""
    for run in runs:
        if run.get("head_sha") == head_sha and run.get("event") in {"push", "workflow_dispatch"}:
            return run
    for run in runs:
        if run.get("event") in {"push", "workflow_dispatch"}:
            return run
    return None


def fetch_release_run_via_gh(repo_root: Path, env: dict[str, str], head_sha: str) -> dict | None:
    """Try to retrieve workflow run metadata using the GitHub CLI."""
    if shutil.which("gh") is None:
        return None

    output = run_capture(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "release.yml",
            "--json",
            "url,status,conclusion,headSha,event,displayTitle,createdAt",
            "--limit",
            "25",
        ],
        repo_root,
        env,
    )
    rows = json.loads(output) if output else []
    normalized = [
        {
            "html_url": row.get("url"),
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "head_sha": row.get("headSha"),
            "event": row.get("event"),
            "display_title": row.get("displayTitle"),
            "created_at": row.get("createdAt"),
        }
        for row in rows
    ]
    return _find_matching_run(normalized, head_sha)


def fetch_release_run_via_api(
    repo_root: Path,
    env: dict[str, str],
    owner: str,
    repo: str,
    head_sha: str,
) -> dict | None:
    """Try to retrieve workflow run metadata using the public GitHub API."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/release.yml/runs"
        "?per_page=25"
    )
    req = Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "3dmakeGUI-update-system")
    token = env.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urlopen(req, timeout=20) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    normalized = [
        {
            "html_url": row.get("html_url"),
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "head_sha": row.get("head_sha"),
            "event": row.get("event"),
            "display_title": row.get("display_title"),
            "created_at": row.get("created_at"),
        }
        for row in runs
    ]
    return _find_matching_run(normalized, head_sha)


def report_release_workflow_run(repo_root: Path, env: dict[str, str], tag: str) -> None:
    """Poll and print the release workflow run URL/status after push."""
    head_sha = run_capture(["git", "rev-list", "-n", "1", tag], repo_root, env)
    remote_url = run_capture(["git", "config", "--get", "remote.origin.url"], repo_root, env)
    parsed = parse_repo_from_remote(remote_url)
    owner_repo = f"{parsed[0]}/{parsed[1]}" if parsed else None
    fallback_actions_url = f"https://github.com/{owner_repo}/actions/workflows/release.yml" if owner_repo else None

    print("\nLooking for release workflow run...")
    timeout_sec = 180
    start = time.time()
    last_error = ""

    while time.time() - start < timeout_sec:
        run = None
        try:
            run = fetch_release_run_via_gh(repo_root, env, head_sha)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            last_error = f"gh lookup failed: {exc}"

        if run is None and parsed is not None:
            try:
                run = fetch_release_run_via_api(repo_root, env, parsed[0], parsed[1], head_sha)
            except (OSError, URLError, json.JSONDecodeError) as exc:
                last_error = f"API lookup failed: {exc}"

        if run is not None:
            print("Release workflow run detected:")
            print(f"  URL: {run.get('html_url')}")
            print(f"  Event: {run.get('event')}")
            print(f"  Status: {run.get('status')}")
            print(f"  Conclusion: {run.get('conclusion')}")
            return

        time.sleep(5)

    if fallback_actions_url:
        print("No matching release run found within 180s.")
        print(f"Check manually: {fallback_actions_url}")
    elif last_error:
        print(f"No matching release run found within 180s ({last_error}).")


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
    required = [
        "pyproject.toml",
        "3dmake_gui.spec",
        "scripts/bump_version.py",
        ".github/workflows/release.yml",
    ]
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
        help="Skip version update.",
    )
    parser.add_argument(
        "--no-pyinstaller",
        action="store_true",
        help="Skip PyInstaller build.",
    )
    parser.add_argument(
        "--no-release",
        action="store_true",
        help="Skip git commit/tag/push and workflow dispatch.",
    )
    parser.add_argument(
        "--version",
        dest="release_version",
        type=str,
        default=None,
        help="Override date-based release version (without leading v).",
    )
    return parser.parse_args()


def date_based_version(today: dt.date | None = None) -> str:
    """Return YYYY-date based SemVer-like version in YYY.M.D form.

    Examples
    --------
    2026-05-05 -> ``026.5.5``
    """
    current = today or dt.date.today()
    return f"{current.year % 1000:03d}.{current.month}.{current.day}"


def normalize_version(version: str) -> str:
    """Validate and normalize a release version string (no leading ``v``)."""
    cleaned = version.strip()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    if not re.fullmatch(r"\d{3}\.\d{1,2}\.\d{1,2}", cleaned):
        raise SystemExit(
            "Version must match YYY.M.D format (example: 026.5.5 or v026.5.5)."
        )
    return cleaned


def update_version_files(repo_root: Path, version: str) -> None:
    """Update version in pyproject.toml and src/tdmake_gui_wrapper/__init__.py."""
    pyproject_file = repo_root / PYPROJECT_PATH
    init_file = repo_root / INIT_PATH

    py_text = pyproject_file.read_text(encoding="utf-8")
    py_updated, py_count = re.subn(
        r'^(version\s*=\s*)"[^"]+"\s*$',
        rf'\1"{version}"',
        py_text,
        count=1,
        flags=re.MULTILINE,
    )
    if py_count != 1:
        raise SystemExit("Could not update [project].version in pyproject.toml")
    pyproject_file.write_text(py_updated, encoding="utf-8")

    init_text = init_file.read_text(encoding="utf-8")
    init_updated, init_count = re.subn(
        r'^(__version__\s*=\s*)"[^"]+"\s*$',
        rf'\1"{version}"',
        init_text,
        count=1,
        flags=re.MULTILINE,
    )
    if init_count != 1:
        raise SystemExit("Could not update __version__ in src/tdmake_gui_wrapper/__init__.py")
    init_file.write_text(init_updated, encoding="utf-8")


def git_release(repo_root: Path, env: dict[str, str], tag: str) -> None:
    """Commit, tag, push, and trigger release workflow."""
    if shutil.which("git") is None:
        raise SystemExit("Error: 'git' was not found in PATH.")

    branch = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root, env)
    if branch == "HEAD":
        raise SystemExit("Detached HEAD detected. Checkout a branch before running release.")

    existing = run_capture(["git", "tag", "--list", tag], repo_root, env)
    if existing == tag:
        raise SystemExit(f"Tag {tag} already exists. Choose a new version.")

    run_step(["git", "add", "-A"], repo_root, env)

    status = run_capture(["git", "status", "--porcelain"], repo_root, env)
    if status:
        run_step(["git", "commit", "-m", f"release: {tag}"], repo_root, env)
    else:
        print("\nNo staged changes to commit; continuing with tag/push.")

    run_step(["git", "tag", "-a", tag, "-m", f"Release {tag}"], repo_root, env)
    run_step(["git", "push", "origin", branch], repo_root, env)
    run_step(["git", "push", "origin", tag], repo_root, env)

    if shutil.which("gh") is not None:
        run_step(
            ["gh", "workflow", "run", "release.yml", "-f", f"version={tag}"],
            repo_root,
            env,
        )
    else:
        print(
            "\nNote: GitHub CLI not found; skipped explicit workflow dispatch. "
            "Tag push already triggers .github/workflows/release.yml."
        )

    report_release_workflow_run(repo_root, env, tag)


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

    release_version = normalize_version(args.release_version) if args.release_version else date_based_version()
    release_tag = f"v{release_version}"

    if not args.no_bump:
        print(f"\nUpdating version files to {release_version}")
        update_version_files(repo_root, release_version)

    if not args.no_pyinstaller:
        steps.append(["uv", "run", "pyinstaller", "3dmake_gui.spec"])

    print("Running update workflow from:", repo_root)
    for command in steps:
        run_step(command, repo_root=repo_root, env=repo_env)

    if not args.no_release:
        print(f"\nPreparing release commit and tag: {release_tag}")
        git_release(repo_root, repo_env, release_tag)

    print("\nWorkflow completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}.")
        raise SystemExit(exc.returncode) from exc

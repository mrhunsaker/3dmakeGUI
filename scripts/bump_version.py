#!/usr/bin/env python3
"""Interactive version bumper for YYYY.MM.DD style versions.

This script updates:
- pyproject.toml -> [project].version
- src/tdmake_gui_wrapper/__init__.py -> __version__

Version format:
- YYYY.MM.DD
- YYYY.MM.DD.N (optional revision for same-day releases)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INIT_PY = ROOT / "src" / "tdmake_gui_wrapper" / "__init__.py"


VERSION_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(?:\.(\d+))?$")


@dataclass
class VersionParts:
    """Structured representation of a calendar-version string.

    Parameters
    ----------
    year : int
        Four-digit year component.
    month : int
        Month component in the range 1-12.
    day : int
        Day-of-month component.
    revision : int or None, optional
        Optional same-day revision suffix.
    """

    year: int
    month: int
    day: int
    revision: int | None = None

    @property
    def as_date(self) -> date:
        """Convert the version date components into a :class:`datetime.date`.

        Returns
        -------
        datetime.date
            Date instance built from ``year``, ``month``, and ``day``.
        """
        return date(self.year, self.month, self.day)

    def to_string(self) -> str:
        """Serialize the version to ``YYYY.MM.DD`` (with optional revision).

        Returns
        -------
        str
            Calendar-version string using zero-padded date components.
        """
        base = f"{self.year:04d}.{self.month:02d}.{self.day:02d}"
        if self.revision is None:
            return base
        return f"{base}.{self.revision}"


def parse_version(value: str) -> VersionParts | None:
    """Parse a version string into structured components.

    Parameters
    ----------
    value : str
        Version string expected in ``YYYY.MM.DD`` or ``YYYY.MM.DD.N`` format.

    Returns
    -------
    VersionParts or None
        Parsed version object when valid; otherwise ``None``.
    """
    match = VERSION_RE.fullmatch(value.strip())
    if not match:
        return None
    year, month, day, revision = match.groups()
    parts = VersionParts(int(year), int(month), int(day), None)
    if revision is not None:
        parts.revision = int(revision)
    return parts


def read_current_version() -> str:
    """Read the project version from ``pyproject.toml``.

    Returns
    -------
    str
        Current version string from ``[project].version``.

    Raises
    ------
    RuntimeError
        If no version field can be located.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find [project] version in pyproject.toml")
    return match.group(1)


def prompt_choice() -> str:
    """Prompt the user to choose which version component to increment.

    Returns
    -------
    str
        One of ``"1"``, ``"2"``, ``"3"``, or ``"4"``.
    """
    print("Select which aspect to increase:")
    print("  1) Year   (YYYY+1, reset to Jan 01)")
    print("  2) Month  (next month, day -> 01)")
    print("  3) Day    (next day)")
    print("  4) Revision (same day, +1 suffix)")
    while True:
        choice = input("Enter 1/2/3/4: ").strip()
        if choice in {"1", "2", "3", "4"}:
            return choice
        print("Invalid choice. Please enter 1, 2, 3, or 4.")


def compute_next_version(current: VersionParts, choice: str) -> VersionParts:
    """Compute the next version according to an increment strategy.

    Parameters
    ----------
    current : VersionParts
        Current parsed version components.
    choice : str
        Increment mode as returned by :func:`prompt_choice`.

    Returns
    -------
    VersionParts
        New version components after applying the selected increment rule.
    """
    if choice == "1":
        return VersionParts(current.year + 1, 1, 1, None)

    if choice == "2":
        if current.month == 12:
            return VersionParts(current.year + 1, 1, 1, None)
        return VersionParts(current.year, current.month + 1, 1, None)

    if choice == "3":
        next_day = current.as_date + timedelta(days=1)
        return VersionParts(next_day.year, next_day.month, next_day.day, None)

    # choice == "4"
    revision = 1 if current.revision is None else current.revision + 1
    return VersionParts(current.year, current.month, current.day, revision)


def replace_version_in_file(path: Path, pattern: str, new_version: str) -> None:
    """Replace the first version assignment matching a regex pattern.

    Parameters
    ----------
    path : pathlib.Path
        File to update.
    pattern : str
        Regular-expression pattern containing a first capture group for the
        left side of the assignment.
    new_version : str
        Version string to write.

    Raises
    ------
    RuntimeError
        If exactly one replacement cannot be performed.
    """
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, rf'\1"{new_version}"', text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Could not update version in {path}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    """Run the interactive version bump workflow.

    Notes
    -----
    This function reads the current version, prompts for an increment strategy,
    asks for confirmation, and writes updated values to both ``pyproject.toml``
    and ``src/tdmake_gui_wrapper/__init__.py``.
    """
    current_raw = read_current_version()
    parsed = parse_version(current_raw)
    if parsed is None:
        today = date.today()
        parsed = VersionParts(today.year, today.month, today.day, None)
        print(f"Current version '{current_raw}' is not YYYY.MM.DD; normalizing from today.")

    print(f"Current version: {current_raw}")
    choice = prompt_choice()
    next_version = compute_next_version(parsed, choice).to_string()
    print(f"Next version: {next_version}")

    confirm = input("Write this version to pyproject.toml and __init__.py? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Aborted.")
        return

    replace_version_in_file(PYPROJECT, r'^(version\s*=\s*)"[^"]+"\s*$', next_version)
    replace_version_in_file(INIT_PY, r'^(__version__\s*=\s*)"[^"]+"\s*$', next_version)

    print("Updated:")
    print(f"- {PYPROJECT}")
    print(f"- {INIT_PY}")


if __name__ == "__main__":
    main()

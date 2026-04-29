import importlib.util
import sys
from datetime import date
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bump_version.py"
SPEC = importlib.util.spec_from_file_location("bump_version", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None

bump_version = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bump_version
SPEC.loader.exec_module(bump_version)

VersionParts = bump_version.VersionParts
compute_next_version = bump_version.compute_next_version
parse_version = bump_version.parse_version
read_current_version = bump_version.read_current_version
replace_version_in_file = bump_version.replace_version_in_file


def test_parse_version_accepts_calendar_version():
    parsed = parse_version("2026.04.29")

    assert parsed == VersionParts(2026, 4, 29, None)


def test_parse_version_accepts_revision_suffix():
    parsed = parse_version("2026.04.29.2")

    assert parsed == VersionParts(2026, 4, 29, 2)


def test_parse_version_rejects_invalid_format():
    assert parse_version("v2026.04.29") is None


def test_version_parts_to_string_roundtrip():
    parts = VersionParts(2026, 4, 29, 3)

    assert parts.to_string() == "2026.04.29.3"


def test_version_parts_as_date_property():
    parts = VersionParts(2026, 4, 29)

    assert parts.as_date == date(2026, 4, 29)


def test_compute_next_version_year_rollover():
    current = VersionParts(2026, 12, 31)

    assert compute_next_version(current, "1") == VersionParts(2027, 1, 1)


def test_compute_next_version_month_rollover_december():
    current = VersionParts(2026, 12, 15)

    assert compute_next_version(current, "2") == VersionParts(2027, 1, 1)


def test_compute_next_version_day_increment():
    current = VersionParts(2026, 4, 29)

    assert compute_next_version(current, "3") == VersionParts(2026, 4, 30)


def test_compute_next_version_revision_increment_from_none():
    current = VersionParts(2026, 4, 29, None)

    assert compute_next_version(current, "4") == VersionParts(2026, 4, 29, 1)


def test_compute_next_version_revision_increment_from_existing():
    current = VersionParts(2026, 4, 29, 2)

    assert compute_next_version(current, "4") == VersionParts(2026, 4, 29, 3)


def test_read_current_version_reads_pyproject(monkeypatch, tmp_path: Path):
    fake_pyproject = tmp_path / "pyproject.toml"
    fake_pyproject.write_text(
        "\n".join(["[project]", 'version = "2026.04.29"']),
        encoding="utf-8",
    )
    monkeypatch.setattr(bump_version, "PYPROJECT", fake_pyproject)

    assert read_current_version() == "2026.04.29"


def test_replace_version_in_file_updates_single_match(tmp_path: Path):
    target = tmp_path / "target.toml"
    target.write_text('version = "2026.04.29"\n', encoding="utf-8")

    replace_version_in_file(target, r'^(version\s*=\s*)"[^"]+"\s*$', "2026.04.30")

    assert target.read_text(encoding="utf-8") == 'version = "2026.04.30"'

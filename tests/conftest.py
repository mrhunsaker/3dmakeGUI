"""Shared pytest configuration."""

from pathlib import Path
import sys

# Ensure the src layout is importable during test runs
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

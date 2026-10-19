"""Shared pytest configuration."""
import sys
from pathlib import Path

# Ensure the src layout is importable during test runs
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

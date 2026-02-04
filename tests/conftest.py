"""Shared pytest fixtures for twag tests."""

import sys
from pathlib import Path

import pytest

# Add the package to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

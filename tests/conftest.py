"""Shared pytest fixtures for twag tests."""

import sys
from pathlib import Path

import pytest

# Add the package to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _clear_link_utils_state():
    """Reset link_utils LRU cache and network expansion counter between tests."""
    import twag.link_utils as lu

    lu._expand_short_url.cache_clear()
    lu._network_expansion_attempts = 0
    yield
    lu._expand_short_url.cache_clear()
    lu._network_expansion_attempts = 0

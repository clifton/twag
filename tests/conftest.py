"""Shared pytest fixtures for twag tests."""

import os
import sys
import tempfile
from pathlib import Path

# Add the package to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Redirect twag's data dir to a per-session temp path.

    Without this, tests that exercise the CLI or the metrics flush hook would
    write to the user's real ``~/.local/share/twag`` database. Set it before
    any twag module is imported by individual tests.
    """
    if not os.environ.get("TWAG_DATA_DIR"):
        tmp_root = Path(tempfile.mkdtemp(prefix="twag-tests-"))
        os.environ["TWAG_DATA_DIR"] = str(tmp_root)

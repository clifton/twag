"""CI guard: docs must stay in sync with code.

Wraps ``scripts/check_doc_drift.py``. Each individual check becomes its own
test so CI failures point at the specific drift category.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_drift.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_doc_drift", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_doc_drift"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def results():
    checker = _load_checker()
    return checker.run_all_checks()


def test_no_drift(results):
    failing = [r for r in results if not r.ok]
    if failing:
        details = "\n".join(f"[{r.name}]\n  - " + "\n  - ".join(r.issues) for r in failing)
        pytest.fail(f"Documentation drift detected:\n{details}")

# conftest.py (repo root)
# Fix: garantizar que el repo root esté en sys.path para imports tipo: synapse.*, core.*, vault.*
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture(autouse=True)
def _isolate_vault_state(tmp_path):
    """Ensure every test gets a fresh vault state file (no cross-test contamination)."""
    vault_file = str(tmp_path / "vault_state_test.json")
    old = os.environ.get("SYNAPSE_VAULT_STATE_FILE")
    os.environ["SYNAPSE_VAULT_STATE_FILE"] = vault_file
    yield
    if old is None:
        os.environ.pop("SYNAPSE_VAULT_STATE_FILE", None)
    else:
        os.environ["SYNAPSE_VAULT_STATE_FILE"] = old

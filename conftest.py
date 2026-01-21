# conftest.py (repo root)
# Fix: garantizar que el repo root esté en sys.path para imports tipo: synapse.*, core.*, vault.*
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)

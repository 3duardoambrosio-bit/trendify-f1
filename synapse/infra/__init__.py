# synapse/infra/__init__.py
"""
Infra package.

Regla:
- NO importar módulos con CLI aquí (ej. doctor.py),
  para evitar RuntimeWarning de runpy al ejecutar `python -m ...`.
"""

from __future__ import annotations

from .ledger import Ledger

# Re-export de schemas (esto NO importa doctor)
from .schemas import (
    Schemas,
    schemas,
    validate,
    SchemaVersionError,
    SchemaValidationError,
    UnknownSchemaError,
)

__all__ = [
    "Ledger",
    "Schemas",
    "schemas",
    "validate",
    "SchemaVersionError",
    "SchemaValidationError",
    "UnknownSchemaError",
]

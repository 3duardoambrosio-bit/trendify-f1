# synapse/infra/schemas.py
"""
Schema Registry (F1).

Exports estables:
- validate_schema(data, schema_name) -> bool
- validate(schema_name, data) -> bool  
- get_schema_version(schema_name) -> str
- list_schemas() -> list
- SchemaVersionError, SchemaMissingFieldError, SchemaValidationError
- SCHEMAS dict

Regla: NO importar doctor aquí (init hygiene)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import re


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


# ============================================================
# EXCEPTIONS
# ============================================================

class SchemaVersionError(ValueError):
    """Se lanza cuando schema_version no coincide o falta."""


class SchemaValidationError(ValueError):
    """Se lanza cuando el payload no cumple el contrato mínimo."""


# Alias legacy
SchemaMissingFieldError = SchemaValidationError


class UnknownSchemaError(KeyError):
    """Se lanza cuando se pide un schema no registrado."""


# ============================================================
# SCHEMA SPEC
# ============================================================

@dataclass(frozen=True)
class SchemaSpec:
    name: str
    version: str
    required_fields: List[str]


# ============================================================
# SCHEMA DEFINITIONS
# ============================================================

SCHEMAS: Dict[str, SchemaSpec] = {
    "interrogation_result": SchemaSpec(
        name="interrogation_result",
        version="1.0.0",
        required_fields=["schema_version", "product_id", "product_name"],
    ),
    "ad_kit_manifest": SchemaSpec(
        name="ad_kit_manifest",
        version="1.0.0",
        required_fields=["schema_version", "product_id"],
    ),
    "market_pulse_memo": SchemaSpec(
        name="market_pulse_memo",
        version="1.0.0",
        required_fields=["schema_version"],
    ),
}

# Alias
DEFAULT_SPECS = SCHEMAS


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def _require_dict(data: Any) -> Dict[str, Any]:
    """Convierte data a dict si es posible."""
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
        d = data.to_dict()
        if isinstance(d, dict):
            return d
    raise SchemaValidationError(f"data debe ser dict o tener to_dict(): {type(data).__name__}")


def get_schema_version(schema_name: str) -> str:
    """
    Get version of a registered schema.
    
    Args:
        schema_name: Nombre del schema
        
    Returns:
        Version string (semver)
    """
    if schema_name not in SCHEMAS:
        raise UnknownSchemaError(f"Schema no registrado: {schema_name}")
    return SCHEMAS[schema_name].version


def list_schemas() -> List[str]:
    """
    List all registered schema names.
    
    Returns:
        List of schema names
    """
    return list(SCHEMAS.keys())


def validate_schema(data: Any, schema_name: str) -> bool:
    """
    Validate data against a schema.
    
    Args:
        data: Datos a validar (dict o objeto con to_dict)
        schema_name: Nombre del schema
        
    Returns:
        True si válido
        
    Raises:
        UnknownSchemaError: Schema no existe
        SchemaVersionError: Version incorrecta o faltante
        SchemaMissingFieldError: Campos requeridos faltantes
    """
    if schema_name not in SCHEMAS:
        raise UnknownSchemaError(f"Schema no registrado: {schema_name}")
    
    spec = SCHEMAS[schema_name]
    d = _require_dict(data)
    
    # Check schema_version FIRST - missing version = SchemaVersionError
    if "schema_version" not in d:
        raise SchemaVersionError(f"Falta schema_version en datos para {schema_name}")
    
    # Check version matches expected
    actual_version = d["schema_version"]
    if actual_version != spec.version:
        raise SchemaVersionError(f"{schema_name}: esperaba version {spec.version}, recibió {actual_version}")
    
    # Check other required fields (excluding schema_version which we already checked)
    other_required = [f for f in spec.required_fields if f != "schema_version"]
    missing = [f for f in other_required if f not in d]
    if missing:
        raise SchemaMissingFieldError(f"Campos faltantes para {schema_name}: {missing}")
    
    return True


def validate(schema_name: str, data: Any) -> bool:
    """
    Validate data against a schema (order: schema_name, data).
    
    Args:
        schema_name: Nombre del schema
        data: Datos a validar
        
    Returns:
        True si válido
    """
    return validate_schema(data, schema_name)


def validate_output(data: Any, schema_name: str) -> bool:
    """
    Alias for validate_schema (same order: data, schema_name).
    """
    return validate_schema(data, schema_name)


# ============================================================
# SCHEMAS CLASS (for advanced usage)
# ============================================================

class Schemas:
    """Registry class para uso avanzado."""
    
    def __init__(self, specs: Optional[Dict[str, SchemaSpec]] = None) -> None:
        self._specs: Dict[str, SchemaSpec] = dict(specs or SCHEMAS)
    
    def validate(self, name: str, data: Any) -> bool:
        return validate_schema(data, name)
    
    def expected_version(self, name: str) -> str:
        return get_schema_version(name)


# Singleton instance
schemas = Schemas()


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Exceptions
    "SchemaVersionError",
    "SchemaValidationError", 
    "SchemaMissingFieldError",
    "UnknownSchemaError",
    # Functions
    "validate_schema",
    "validate",
    "validate_output",
    "get_schema_version",
    "list_schemas",
    # Data
    "SCHEMAS",
    "DEFAULT_SPECS",
    "SchemaSpec",
    # Class
    "Schemas",
    "schemas",
]

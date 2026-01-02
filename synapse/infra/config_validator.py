# synapse/infra/config_validator.py
"""
Config Validator — OLEADA 16
============================

Valida dict configs (YAML/JSON/etc) con reglas simples:
- required keys
- optional keys
- type checks básicos
- no "adivinar": reporta faltantes

Uso:
from synapse.infra.config_validator import ConfigSpec, ConfigValidator

spec = ConfigSpec(required={"api_key": str}, optional={"timeout_s": float})
validator = ConfigValidator(spec)
result = validator.validate({"api_key":"x", "timeout_s": 10})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Type


@dataclass(frozen=True)
class ConfigSpec:
    required: Dict[str, Type] = field(default_factory=dict)
    optional: Dict[str, Type] = field(default_factory=dict)


@dataclass
class ConfigValidationResult:
    ok: bool
    missing: Dict[str, str]
    wrong_type: Dict[str, str]
    extras: Dict[str, str]


class ConfigValidator:
    def __init__(self, spec: ConfigSpec):
        self.spec = spec

    def validate(self, cfg: Dict[str, Any], *, allow_extras: bool = True) -> ConfigValidationResult:
        missing: Dict[str, str] = {}
        wrong_type: Dict[str, str] = {}
        extras: Dict[str, str] = {}

        for k, t in self.spec.required.items():
            if k not in cfg:
                missing[k] = f"required {t.__name__}"
            else:
                if not isinstance(cfg[k], t):
                    wrong_type[k] = f"expected {t.__name__}, got {type(cfg[k]).__name__}"

        for k, t in self.spec.optional.items():
            if k in cfg and not isinstance(cfg[k], t):
                wrong_type[k] = f"expected {t.__name__}, got {type(cfg[k]).__name__}"

        if not allow_extras:
            allowed = set(self.spec.required.keys()) | set(self.spec.optional.keys())
            for k in cfg.keys():
                if k not in allowed:
                    extras[k] = "extra key not allowed"

        ok = (len(missing) == 0 and len(wrong_type) == 0 and (allow_extras or len(extras) == 0))
        return ConfigValidationResult(ok=ok, missing=missing, wrong_type=wrong_type, extras=extras)

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from infra.logging_config import get_logger

logger = get_logger(__name__)


# =========================
# MODELOS DE CONFIGURACIÓN
# =========================


class BuyerScoringConfig(BaseModel):
  """
  Config mínima para el bloque de compra (BuyerBlock / ScoringRules).

  Todo lo que afecte decisiones de aprobación/rechazo de productos
  tiene que vivir aquí, NO hardcodeado en el código.
  """

  min_margin: float = 0.3
  min_trust: float = 7.0
  suspicious_price_ratio_low: float = 0.7
  suspicious_price_ratio_high: float = 2.0


class AppConfig(BaseModel):
  """
  Config global de SYNAPSE/Trendify para Fase 1.

  A futuro aquí se cuelgan:
  - quality_gate
  - capital_shield
  - criterios_exit
  etc.
  """

  buyer_scoring: BuyerScoringConfig = Field(
    default_factory=BuyerScoringConfig
  )


# =========================
# LOADER
# =========================

_DEFAULT_CONFIG_PATH = (
  Path(__file__).resolve().parents[1] / "config" / "default.yml"
)

_APP_CONFIG: Optional[AppConfig] = None


def _read_raw_yaml(path: Path) -> Dict[str, Any]:
  """Lee YAML de forma segura. Si truena, regresa dict vacío."""
  try:
    with path.open("r", encoding="utf-8") as f:
      data = yaml.safe_load(f) or {}
      if not isinstance(data, dict):
        logger.error(
          "Config YAML root is not a mapping, falling back to defaults",
          extra={"extra_data": {"config_path": str(path)}},
        )
        return {}
      return data
  except FileNotFoundError:
    logger.warning(
      "Config file not found, using defaults",
      extra={"extra_data": {"config_path": str(path)}},
    )
    return {}
  except Exception as exc:  # noqa: BLE001
    logger.error(
      "Error reading config file, using defaults",
      extra={
        "extra_data": {
          "config_path": str(path),
          "error": str(exc),
        }
      },
    )
    return {}


def load_config(path: Optional[Path] = None) -> AppConfig:
  """
  Carga la configuración desde YAML y la valida con Pydantic.

  - Si no hay archivo → usa defaults.
  - Si está mal formado → usa defaults.
  - Cachea en memoria para no leer disco cada vez.
  """
  global _APP_CONFIG

  # Reusar config si ya se cargó y no se pidió un path específico
  if _APP_CONFIG is not None and path is None:
    return _APP_CONFIG

  config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
  raw = _read_raw_yaml(config_path)

  # Estructura esperada:
  # buyer:
  #   scoring: { ... }
  buyer_section = raw.get("buyer", {}) if isinstance(raw, dict) else {}
  scoring_section = (
    buyer_section.get("scoring", {}) if isinstance(buyer_section, dict) else {}
  )

  try:
    app_config = AppConfig(
      buyer_scoring=BuyerScoringConfig(**scoring_section),
    )
    _APP_CONFIG = app_config

    logger.info(
      "Config loaded successfully",
      extra={"extra_data": {"config_path": str(config_path)}},
    )
    return app_config

  except ValidationError as exc:
    logger.error(
      "Invalid config, using defaults",
      extra={
        "extra_data": {
          "config_path": str(config_path),
          "error": str(exc),
        }
      },
    )
    _APP_CONFIG = AppConfig()
    return _APP_CONFIG


def get_app_config() -> AppConfig:
  """Atajo para obtener la config global."""
  return load_config()

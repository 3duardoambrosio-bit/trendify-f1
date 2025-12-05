from __future__ import annotations

from typing import Any, List, Dict, Optional

from buyer.schemas import ProductSchema
from infra.config_loader import BuyerScoringConfig, get_app_config


class ScoringRules:
  """
  Reglas determinísticas para evaluar un producto.

  Fase 1:
  - Margen mínimo
  - Trust mínimo
  - Precio sospechoso (demasiado barato/caro)
  - Composite score simple (0-1) basado en margen y trust
  """

  def __init__(self, config: Optional[BuyerScoringConfig] = None) -> None:
    # Si no pasan config explícita, leemos del YAML
    if config is None:
      try:
        app_cfg = get_app_config()
        config = app_cfg.buyer_scoring
      except Exception:  # noqa: BLE001
        # Fallback ultra defensivo: defaults hardcodeados
        config = BuyerScoringConfig()

    self._config = config
    self.min_margin = config.min_margin
    self.min_trust = config.min_trust
    self.suspicious_price_ratio_low = config.suspicious_price_ratio_low
    self.suspicious_price_ratio_high = config.suspicious_price_ratio_high

  # =====================
  #  MÉTRICAS BÁSICAS
  # =====================

  def calculate_margin(self, product: ProductSchema) -> float:
    """
    Margen como % de venta: (sale - cost) / sale.

    - Si faltan datos o sale_price <= 0 → 0.0
    """
    if product.sale_price is None or product.sale_price <= 0:
      return 0.0
    if product.cost_price is None:
      return 0.0

    margin = (product.sale_price - product.cost_price) / product.sale_price
    return max(margin, 0.0)

  # alias para tests / backwards-compat
  def calculate_margin_percent(self, product: ProductSchema) -> float:
    return self.calculate_margin(product)

  # Versión que usaban los tests
  def calculate_margin_ratio(self, product: ProductSchema) -> float:
    return self.calculate_margin(product)

  # Nombre original esperado por los tests
  def calculate_margin_(self, product: ProductSchema) -> float:
    return self.calculate_margin(product)

  # Compat con el fixture de tests (usa este)
  def calculate_margin_test(self, product: ProductSchema) -> float:
    return self.calculate_margin(product)

  # El nombre que realmente usan los tests actuales:
  def calculate_margin_for_product(self, product: ProductSchema) -> float:
    return self.calculate_margin(product)

  # =====================
  #  CHECKS UNITARIOS
  # =====================

  def is_margin_acceptable(self, margin: float) -> bool:
    """True si el margen está por encima o en el mínimo configurado."""
    return margin >= self.min_margin

  def is_trust_acceptable(self, trust_score: Optional[float]) -> bool:
    """
    True si la confianza está por encima o en el mínimo.

    None = no sabemos → lo tratamos como NO aceptable para ser conservadores.
    """
    if trust_score is None:
      return False
    return trust_score >= self.min_trust

  def is_price_suspicious(self, product: ProductSchema) -> bool:
    """
    True si el ratio precio/coste es demasiado bajo o demasiado alto.

    - ratio < suspicious_price_ratio_low  → sospechosamente barato
    - ratio > suspicious_price_ratio_high → sospechosamente caro
    """
    if not product.cost_price or product.cost_price <= 0:
      return False
    if not product.sale_price or product.sale_price <= 0:
      return False

    ratio = product.sale_price / product.cost_price

    if ratio < self.suspicious_price_ratio_low:
      return True
    if ratio > self.suspicious_price_ratio_high:
      return True
    return False

  # =====================
  #  EVALUACIÓN COMPLETA
  # =====================

  def evaluate_product(self, product: ProductSchema) -> Dict[str, Any]:
    """
    Devuelve un dict con:
    - margin
    - trust_score
    - composite_score
    - suspicion_flags (lista de strings)
    """
    margin = self.calculate_margin(product)
    trust_score = product.trust_score if product.trust_score is not None else 0.0

    flags: List[str] = []

    # Margen
    if not self.is_margin_acceptable(margin):
      flags.append("margin_below_threshold")

    # Precio sospechoso
    if self.is_price_suspicious(product):
      flags.append("suspicious_price")

    # Trust bajo
    if not self.is_trust_acceptable(product.trust_score):
      flags.append("trust_below_threshold")

    composite_score = self._calculate_composite_score(
      margin=margin,
      trust_score=trust_score,
      flags=flags,
    )

    return {
      "margin": margin,
      "trust_score": trust_score,
      "composite_score": composite_score,
      "suspicion_flags": flags,
    }

  def _calculate_composite_score(
    self,
    margin: float,
    trust_score: float,
    flags: List[str],
  ) -> float:
    """
    Score compuesto 0-1 basado en:
    - margen (0-1)
    - trust_score (0-10 → 0-1)

    Para Fase 1 usamos fórmula simple:
      composite = 0.5 * margin + 0.5 * (trust_score / 10)

    NOTA: Aunque haya flags, NO lo forzamos a 0.
    Los flags se usan en BuyerBlock para decidir aprobar/rechazar.
    """
    margin_component = max(min(margin, 1.0), 0.0)
    trust_component = max(min(trust_score / 10.0, 1.0), 0.0)

    return 0.5 * margin_component + 0.5 * trust_component

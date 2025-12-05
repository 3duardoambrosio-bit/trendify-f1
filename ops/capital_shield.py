from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from infra.settings import settings


# =========================
# CONFIG
# =========================


@dataclass
class CapitalShieldConfig:
    """Config mínima para Capital-Shield LITE (Fase 1)."""

    hard_daily_cap: float = 30.0
    daily_learning_cap: float = 15.0
    daily_testing_cap: float = 15.0
    product_soft_cap_ratio: float = 0.40
    product_hard_cap_ratio: float = 0.70

    @classmethod
    def from_settings(cls) -> "CapitalShieldConfig":
        cfg = settings.config.get("capital_shield", {}) or {}
        return cls(
            hard_daily_cap=float(cfg.get("hard_daily_cap", 30.0)),
            daily_learning_cap=float(cfg.get("daily_learning_cap", 15.0)),
            daily_testing_cap=float(cfg.get("daily_testing_cap", 15.0)),
            product_soft_cap_ratio=float(cfg.get("product_soft_cap_ratio", 0.40)),
            product_hard_cap_ratio=float(cfg.get("product_hard_cap_ratio", 0.70)),
        )


# =========================
# MODELOS INTERNOS
# =========================


@dataclass
class _DayState:
    date: date
    total_spend: float = 0.0
    product_spend: Dict[str, float] = field(default_factory=dict)


@dataclass
class SpendDecision:
    """Respuesta de Capital-Shield para un intento de gasto."""

    allowed: bool
    reason: str
    soft_warnings: List[str] = field(default_factory=list)
    remaining_daily_cap: float = 0.0
    remaining_product_before_hard_cap: float = 0.0


# =========================
# NÚCLEO CAPITAL-SHIELD LITE
# =========================


class CapitalShield:
    """
    Guardaespaldas del presupuesto (versión Fase 1).

    Reglas:
    - No permite pasar el hard_daily_cap.
    - Un producto no puede consumir más que product_hard_cap_ratio del cap diario.
    - Si supera product_soft_cap_ratio pero no el hard, deja pasar con warning.
    """

    def __init__(self, config: CapitalShieldConfig | None = None) -> None:
        self.config = config or CapitalShieldConfig.from_settings()
        self._daily_state: Dict[date, _DayState] = {}

    # ---------- Helpers internos ----------

    def _get_day_state(self, day: date) -> _DayState:
        if day not in self._daily_state:
            self._daily_state[day] = _DayState(date=day)
        return self._daily_state[day]

    # ---------- API pública ----------

    def register_spend(self, product_id: str, amount: float) -> SpendDecision:
        """
        Intenta registrar un gasto para un producto.

        Devuelve:
        - allowed=True  → gasto permitido
        - allowed=False → gasto bloqueado (no se registra en el estado interno)
        """
        if amount < 0:
            raise ValueError("amount must be non-negative")

        today = date.today()
        state = self._get_day_state(today)

        # 1) Checar cap diario duro
        projected_total = state.total_spend + amount
        if projected_total > self.config.hard_daily_cap:
            remaining_cap = max(self.config.hard_daily_cap - state.total_spend, 0.0)
            remaining_for_product = max(
                (self.config.hard_daily_cap * self.config.product_hard_cap_ratio)
                - state.product_spend.get(product_id, 0.0),
                0.0,
            )
            return SpendDecision(
                allowed=False,
                reason="hard_daily_cap_exceeded",
                soft_warnings=[],
                remaining_daily_cap=round(remaining_cap, 2),
                remaining_product_before_hard_cap=round(remaining_for_product, 2),
            )

        # 2) Checar concentración por producto
        current_product_spend = state.product_spend.get(product_id, 0.0)
        projected_product_total = current_product_spend + amount

        ratio = (
            projected_product_total / self.config.hard_daily_cap
            if self.config.hard_daily_cap > 0
            else 0.0
        )

        warnings: List[str] = []
        blocked = False
        reason = "ok"

        if ratio > self.config.product_hard_cap_ratio:
            blocked = True
            reason = "product_hard_cap_ratio_exceeded"
        elif ratio > self.config.product_soft_cap_ratio:
            warnings.append("product_soft_cap_ratio_exceeded")

        if blocked:
            remaining_cap = max(self.config.hard_daily_cap - state.total_spend, 0.0)
            remaining_for_product = max(
                (self.config.hard_daily_cap * self.config.product_hard_cap_ratio)
                - current_product_spend,
                0.0,
            )
            return SpendDecision(
                allowed=False,
                reason=reason,
                soft_warnings=warnings,
                remaining_daily_cap=round(remaining_cap, 2),
                remaining_product_before_hard_cap=round(remaining_for_product, 2),
            )

        # 3) Actualizar estado (gasto permitido)
        state.total_spend = projected_total
        state.product_spend[product_id] = projected_product_total

        remaining_cap = max(self.config.hard_daily_cap - state.total_spend, 0.0)
        remaining_for_product = max(
            (self.config.hard_daily_cap * self.config.product_hard_cap_ratio)
            - projected_product_total,
            0.0,
        )

        return SpendDecision(
            allowed=True,
            reason=reason,
            soft_warnings=warnings,
            remaining_daily_cap=round(remaining_cap, 2),
            remaining_product_before_hard_cap=round(remaining_for_product, 2),
        )

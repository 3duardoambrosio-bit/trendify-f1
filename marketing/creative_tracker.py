from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
import random


@dataclass
class CreativeStats:
    """
    Métricas de un creativo individual.

    Esta estructura es la base para:
    - monitorear desempeño
    - alimentar bandits (Thompson Sampling) en F2

    No toma decisiones, solo mantiene contadores y métricas derivadas.
    """

    creative_id: str
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: Decimal = Decimal("0")
    revenue: Decimal = Decimal("0")

    @property
    def alpha(self) -> int:
        """
        Parámetro alpha para Thompson Sampling:
        - éxitos + 1
        """
        return self.conversions + 1

    @property
    def beta(self) -> int:
        """
        Parámetro beta para Thompson Sampling:
        - fallos + 1
        - fallos = clicks - conversions, truncado en 0
        """
        failures = max(self.clicks - self.conversions, 0)
        return failures + 1

    @property
    def estimated_cvr(self) -> float:
        """
        Conversion rate estimado (0-1).
        """
        if self.clicks <= 0:
            return 0.0
        return self.conversions / float(self.clicks)

    @property
    def estimated_ctr(self) -> float:
        """
        Click-through rate estimado (0-1).
        """
        if self.impressions <= 0:
            return 0.0
        return self.clicks / float(self.impressions)

    @property
    def estimated_roas(self) -> float:
        """
        ROAS aproximado (revenue / spend).

        Si spend es 0, se considera 0 para evitar divisiones explosivas.
        """
        if self.spend <= 0:
            return 0.0
        return float(self.revenue / self.spend)

    def add_spend(self, amount: Decimal) -> None:
        try:
            dec = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid spend amount: {amount}") from exc

        if dec < 0:
            raise ValueError("Spend amount must be non-negative")

        self.spend += dec

    def add_revenue(self, amount: Decimal) -> None:
        try:
            dec = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid revenue amount: {amount}") from exc

        if dec < 0:
            raise ValueError("Revenue amount must be non-negative")

        self.revenue += dec


class CreativeSelector:
    """
    Selector de creativos.

    F1:
    - Estrategia de selección por defecto: round-robin determinista.
    - Infraestructura para Thompson Sampling preparada pero desactivada.

    F2:
    - Se podrá activar use_thompson=True cuando haya suficientes datos reales.
    """

    def __init__(self, use_thompson: bool = False) -> None:
        self.stats: Dict[str, CreativeStats] = {}
        self.use_thompson = use_thompson
        self._rr_index: int = 0  # índice para round-robin

    # --- Gestión interna ---

    def _get_or_create(self, creative_id: str) -> CreativeStats:
        if creative_id not in self.stats:
            self.stats[creative_id] = CreativeStats(creative_id=creative_id)
        return self.stats[creative_id]

    # --- API pública de tracking ---

    def record_impression(self, creative_id: str) -> None:
        stats = self._get_or_create(creative_id)
        stats.impressions += 1

    def record_click(self, creative_id: str) -> None:
        stats = self._get_or_create(creative_id)
        stats.clicks += 1

    def record_conversion(self, creative_id: str, revenue: Decimal = Decimal("0")) -> None:
        stats = self._get_or_create(creative_id)
        stats.conversions += 1
        if revenue:
            stats.add_revenue(revenue)

    def record_spend(self, creative_id: str, amount: Decimal) -> None:
        stats = self._get_or_create(creative_id)
        stats.add_spend(amount)

    # --- Selección de creativos ---

    def select_creative(self, available: List[str]) -> Optional[str]:
        """
        Selecciona un creativo de la lista disponible.

        Reglas:
        - Si la lista está vacía → None.
        - Si use_thompson=False → round-robin determinista.
        - Si use_thompson=True → infraestructura de Thompson Sampling.
        """
        if not available:
            return None

        if self.use_thompson:
            return self._select_thompson(available)

        return self._select_round_robin(available)

    def _select_round_robin(self, available: List[str]) -> str:
        """
        Round-robin determinista sobre la lista recibida.
        """
        idx = self._rr_index % len(available)
        self._rr_index += 1
        return available[idx]

    def _select_thompson(self, available: List[str]) -> str:
        """
        Infraestructura de Thompson Sampling:

        - Para cada creativo disponible se samplea Beta(alpha, beta).
        - Se elige el creativo con el sample más alto.

        En F1 no se depende de este comportamiento para decisiones críticas.
        """
        best_id: Optional[str] = None
        best_sample: float = float("-inf")

        for creative_id in available:
            stats = self._get_or_create(creative_id)
            # Beta(alpha, beta) usando la librería estándar
            sample = random.betavariate(stats.alpha, stats.beta)
            if sample > best_sample:
                best_sample = sample
                best_id = creative_id

        # Por construcción siempre habrá uno (available no está vacío).
        assert best_id is not None
        return best_id

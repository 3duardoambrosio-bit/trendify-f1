from __future__ import annotations
from infra.time_utils import now_utc

from datetime import datetime, timezone


from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from infra.bitacora_auto import BitacoraAuto, EntryType


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"


@dataclass
class Hypothesis:
    """Modelo en memoria para una hipótesis concreta."""

    id: str
    area: str
    statement: str
    metric: str
    baseline_value: Optional[float]
    created_at: datetime
    status: HypothesisStatus
    result_value: Optional[float] = None


class HypothesisTracker:
    """
    Lleva registro de hipótesis sobre el sistema (reglas, umbrales, cambios)
    y las escribe en la Bitácora.

    Filosofía:
    - Toda hipótesis se registra antes de probarla.
    - Toda hipótesis se cierra como VALIDATED o INVALIDATED.
    - El resumen se calcula leyendo la Bitácora (fuente de verdad).
    """

    def __init__(self, bitacora: Optional[BitacoraAuto] = None) -> None:
        self._bitacora = bitacora or BitacoraAuto()

    # -----------------------------
    # Helpers internos
    # -----------------------------

    def _log(self, event_type: str, payload: Dict) -> None:
        """
        Envía un evento a Bitácora con entry_type = HYPOTHESIS_EVENT.
        """
        data = {"event_type": event_type, **payload}
        self._bitacora.log(entry_type=EntryType.HYPOTHESIS_EVENT, data=data, metadata={})

    # -----------------------------
    # API pública
    # -----------------------------

    def register(
        self,
        area: str,
        statement: str,
        metric: str,
        baseline_value: Optional[float] = None,
    ) -> Hypothesis:
        """
        Registra una nueva hipótesis.

        Ejemplo:
        - area: "buyer"
        - statement: "Subir margen mínimo a 0.35 mejora ROAS"
        - metric: "roas"
        - baseline_value: 1.2
        """
        from uuid import uuid4

        hyp_id = f"HYP-{uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc)


        hyp = Hypothesis(
            id=hyp_id,
            area=area,
            statement=statement,
            metric=metric,
            baseline_value=baseline_value,
            created_at=created_at,
            status=HypothesisStatus.PENDING,
        )

        self._log(
            "created",
            {
                "hypothesis_id": hyp_id,
                "area": area,
                "statement": statement,
                "metric": metric,
                "baseline_value": baseline_value,
                "status": hyp.status.value,
                "created_at": created_at.isoformat(),
            },
        )

        return hyp

    def close(
        self,
        hypothesis_id: str,
        result: HypothesisStatus,
        new_value: Optional[float] = None,
    ) -> None:
        """
        Cierra una hipótesis como VALIDATED o INVALIDATED.
        """
        if result not in (HypothesisStatus.VALIDATED, HypothesisStatus.INVALIDATED):
            raise ValueError("result debe ser VALIDATED o INVALIDATED")

        self._log(
            "closed",
            {
                "hypothesis_id": hypothesis_id,
                "result": result.value,
                "result_value": new_value,
                "closed_at": now_utc().isoformat(),
            },
        )

    def summarize(self) -> Dict[str, int]:
        """
        Lee la Bitácora y devuelve un resumen tipo:

        {
            "total": 3,
            "validated": 1,
            "invalidated": 1,
            "pending": 1,
        }
        """
        entries = self._bitacora.load_entries()
        relevant = [e for e in entries if e.entry_type == EntryType.HYPOTHESIS_EVENT]

        if not relevant:
            return {"total": 0, "validated": 0, "invalidated": 0, "pending": 0}

        # status por hypothesis_id
        status_by_id: Dict[str, str] = {}

        for e in relevant:
            data = e.data or {}
            hyp_id = str(data.get("hypothesis_id", "unknown"))

            # evento de creación
            if "status" in data:
                status_by_id[hyp_id] = str(data["status"])

            # evento de cierre manda sobre el de creación
            if "result" in data:
                status_by_id[hyp_id] = str(data["result"])

        total = len(status_by_id)
        validated = sum(
            1 for s in status_by_id.values() if s == HypothesisStatus.VALIDATED.value
        )
        invalidated = sum(
            1 for s in status_by_id.values() if s == HypothesisStatus.INVALIDATED.value
        )
        pending = total - validated - invalidated

        return {
            "total": total,
            "validated": validated,
            "invalidated": invalidated,
            "pending": pending,
        }

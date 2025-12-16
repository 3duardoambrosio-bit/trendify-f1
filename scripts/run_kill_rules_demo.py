from __future__ import annotations

import sys
from pathlib import Path
from decimal import Decimal
from typing import List, Dict, Any

# Bootstrap de path para importar paquetes internos
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ops.exit_criteria_v2 import (
    evaluate_kill_criteria,
    KillDecision,
    MIN_SPEND_FOR_DECISION,
    HARD_KILL_ROAS,
    SOFT_KILL_ROAS,
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _build_scenarios() -> List[Dict[str, Any]]:
    """
    Escenarios típicos de vida real para probar las kill rules:

    - Poco gasto, buen ROAS → no decidimos nada aún.
    - Spend decente, ROAS muy malo → kill.
    - Spend decente, ROAS en zona gris → pause.
    - Spend decente, ROAS bueno → continue.
    - Casos extremos para ver estabilidad.
    """
    base_spend = MIN_SPEND_FOR_DECISION

    return [
        {
            "id": "A1",
            "label": "Nuevo test, poco gasto, ROAS medio",
            "roas": 0.9,
            "spend": base_spend - Decimal("1"),
        },
        {
            "id": "B1",
            "label": "Spend suficiente, ROAS basura",
            "roas": float(HARD_KILL_ROAS) - 0.2,
            "spend": base_spend + Decimal("5"),
        },
        {
            "id": "C1",
            "label": "Zona gris, ROAS entre hard y soft",
            "roas": (float(HARD_KILL_ROAS) + float(SOFT_KILL_ROAS)) / 2.0,
            "spend": base_spend + Decimal("10"),
        },
        {
            "id": "D1",
            "label": "Buen performer, ROAS por encima de soft",
            "roas": float(SOFT_KILL_ROAS) + 0.3,
            "spend": base_spend + Decimal("20"),
        },
        {
            "id": "E1",
            "label": "Spend muy alto, ROAS catastrófico",
            "roas": float(HARD_KILL_ROAS) / 2.0,
            "spend": base_spend * Decimal("10"),
        },
        {
            "id": "F1",
            "label": "Spend muy alto, ROAS excelente",
            "roas": float(SOFT_KILL_ROAS) * 2.0,
            "spend": base_spend * Decimal("12"),
        },
    ]


def main() -> None:
    _print_header("KILL RULES DEMO — EVALUATE_KILL_CRITERIA V2")

    print(
        f"MIN_SPEND_FOR_DECISION = {MIN_SPEND_FOR_DECISION}\n"
        f"HARD_KILL_ROAS        = {HARD_KILL_ROAS}\n"
        f"SOFT_KILL_ROAS        = {SOFT_KILL_ROAS}\n"
    )

    scenarios = _build_scenarios()

    for scen in scenarios:
        sid = scen["id"]
        label = scen["label"]
        roas = scen["roas"]
        spend = scen["spend"]

        decision: KillDecision = evaluate_kill_criteria(roas=roas, spend=spend)

        print(f"- [{sid}] {label}")
        print(
            f"    roas={roas:.2f} | spend={spend:.2f} "
            f"-> action={decision.action.upper()} | reason={decision.reason}"
        )


if __name__ == "__main__":
    main()

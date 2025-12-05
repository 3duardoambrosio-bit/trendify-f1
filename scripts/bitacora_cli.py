import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


BITACORA_PATH = Path("data") / "bitacora" / "bitacora.jsonl"


@dataclass
class BitacoraRecord:
    """Representa una entrada leída de la Bitácora."""
    entry_id: str
    timestamp: datetime
    entry_type: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "BitacoraRecord":
        ts = datetime.fromisoformat(raw["timestamp"])
        return cls(
            entry_id=raw["entry_id"],
            timestamp=ts,
            entry_type=raw.get("entry_type", "unknown"),
            data=raw.get("data", {}),
            metadata=raw.get("metadata", {}),
        )


def _load_bitacora() -> List[BitacoraRecord]:
    """Carga TODAS las entradas de la bitácora desde el JSONL."""
    if not BITACORA_PATH.exists():
        print(f"[BITACORA] No existe archivo en {BITACORA_PATH}")
        return []

    records: List[BitacoraRecord] = []
    with BITACORA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                records.append(BitacoraRecord.from_raw(raw))
            except json.JSONDecodeError:
                # No rompemos todo por una línea corrupta
                continue
    return records


def cmd_last(limit: int) -> None:
    """Muestra las últimas N entradas registradas en la bitácora."""
    records = _load_bitacora()
    if not records:
        print("[BITACORA] No hay registros.")
        return

    # Ordenar por timestamp descendente
    records.sort(key=lambda r: r.timestamp, reverse=True)
    sliced = records[:limit]

    print(f"[BITACORA] Últimas {len(sliced)} entradas (de {len(records)} totales):\n")
    for rec in sliced:
        ts_str = rec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"- {ts_str} | {rec.entry_type} | id={rec.entry_id}")
        # Si es evaluación de producto, mostramos resumen bonito
        if rec.entry_type == "product_evaluation":
            pid = rec.data.get("product_id", "unknown")
            final_decision = rec.data.get("final_decision", "unknown")
            buyer_decision = rec.data.get("buyer_decision", "unknown")
            q_score = rec.data.get("quality_global_score", None)
            print(f"    product_id      : {pid}")
            print(f"    final_decision  : {final_decision}")
            print(f"    buyer_decision  : {buyer_decision}")
            if q_score is not None:
                print(f"    quality_score   : {q_score}")
        print()


def cmd_product(product_id: str, limit: Optional[int]) -> None:
    """Muestra entradas relacionadas a un product_id específico."""
    records = _load_bitacora()
    if not records:
        print("[BITACORA] No hay registros.")
        return

    # Filtrar por product_id dentro de data
    filtered = [
        r for r in records
        if r.data.get("product_id") == product_id
    ]

    if not filtered:
        print(f"[BITACORA] No hay entradas para product_id={product_id}")
        return

    # Ordenar más recientes primero
    filtered.sort(key=lambda r: r.timestamp, reverse=True)
    if limit is not None:
        filtered = filtered[:limit]

    print(
        f"[BITACORA] Entradas para product_id={product_id} "
        f"({len(filtered)} encontradas):\n"
    )
    for rec in filtered:
        ts_str = rec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"- {ts_str} | {rec.entry_type} | id={rec.entry_id}")
        final_decision = rec.data.get("final_decision", "unknown")
        buyer_decision = rec.data.get("buyer_decision", "unknown")
        q_score = rec.data.get("quality_global_score", None)
        print(f"    final_decision  : {final_decision}")
        print(f"    buyer_decision  : {buyer_decision}")
        if q_score is not None:
            print(f"    quality_score   : {q_score}")
        print()


def cmd_summary() -> None:
    """Muestra un resumen agregado de la Bitácora (modo mini-TRIBUNAL)."""
    records = _load_bitacora()
    if not records:
        print("[BITACORA] No hay registros.")
        return

    total = len(records)
    product_evals = [r for r in records if r.entry_type == "product_evaluation"]
    total_prod = len(product_evals)

    approved = 0
    rejected = 0
    quality_scores: List[float] = []

    for rec in product_evals:
        final_decision = rec.data.get("final_decision")
        if final_decision == "approved":
            approved += 1
        elif final_decision == "rejected":
            rejected += 1

        qs = rec.data.get("quality_global_score")
        if isinstance(qs, (int, float)):
            quality_scores.append(float(qs))

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

    print("[BITACORA] RESUMEN GLOBAL\n")
    print(f"  Total de entradas              : {total}")
    print(f"  Evaluaciones de producto       : {total_prod}")
    print(f"  - Aprobados                    : {approved}")
    print(f"  - Rechazados                   : {rejected}")
    if avg_quality is not None:
        print(f"  Quality score promedio         : {avg_quality:.3f}")
    else:
        print(f"  Quality score promedio         : N/A")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.bitacora_cli",
        description="Herramientas para inspeccionar la Bitácora de SYNAPSE.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # bitacora last
    last_parser = subparsers.add_parser(
        "last",
        help="Mostrar las últimas entradas registradas en la bitácora.",
    )
    last_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Número máximo de entradas a mostrar (default=20).",
    )

    # bitacora product
    product_parser = subparsers.add_parser(
        "product",
        help="Mostrar entradas de la bitácora filtradas por product_id.",
    )
    product_parser.add_argument(
        "product_id",
        type=str,
        help="ID del producto a buscar en la bitácora.",
    )
    product_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de entradas (más recientes primero).",
    )

    # bitacora summary
    subparsers.add_parser(
        "summary",
        help="Mostrar resumen global de la Bitácora (aprobados, rechazados, quality promedio).",
    )

    args = parser.parse_args()

    if args.command == "last":
        cmd_last(limit=args.limit)
    elif args.command == "product":
        cmd_product(product_id=args.product_id, limit=args.limit)
    elif args.command == "summary":
        cmd_summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

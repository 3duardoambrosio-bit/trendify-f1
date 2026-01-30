#!/usr/bin/env python3
# canonical_quality_gate.py
# Gate de calidad para canonical report. Soporta prod vs bootstrap (soft-fail).
# Mantiene compatibilidad: --report y --allow-seed.

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class GateThresholds:
    min_price_rate: float = 0.90
    min_desc_rate: float = 0.70
    min_image_rate: float = 0.60


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _rate(filled: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return float(filled) / float(total)


def _extract_counts(report: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """
    Devuelve: total_rows, filled_price, filled_image, filled_desc
    Soporta varias formas de reporte (legacy o v3).
    """
    counts = report.get("counts") or {}
    total = counts.get("total_rows") or report.get("total_rows")
    fp = counts.get("filled_price") or report.get("filled_price")
    fi = counts.get("filled_image") or report.get("filled_image")
    fd = counts.get("filled_desc") or report.get("filled_desc")

    # Fallback: si viene rates pero no counts (raro), intenta deducir:
    if total is None:
        total = report.get("total_ids") or report.get("rows") or 0
    if fp is None:
        fp = report.get("fill_price") or 0
    if fi is None:
        fi = report.get("fill_image") or 0
    if fd is None:
        fd = report.get("fill_desc") or 0

    # Normaliza
    total = int(total or 0)
    fp = int(fp or 0)
    fi = int(fi or 0)
    fd = int(fd or 0)
    return total, fp, fi, fd


def _is_seed_exception(report: Dict[str, Any], allow_seed: bool) -> bool:
    if not allow_seed:
        return False
    ids = report.get("product_ids") or []
    if isinstance(ids, list) and len(ids) == 1 and str(ids[0]) == "seed":
        return True
    # fallback por si no viene product_ids:
    total, _, _, _ = _extract_counts(report)
    top1 = (report.get("top1") or report.get("meta", {}).get("top1") or "").strip()
    if total == 1 and top1 == "seed":
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="Path a canonical_products.report.json")
    ap.add_argument("--allow-seed", action="store_true", help="Permite excepción seed (imagen puede faltar)")
    ap.add_argument("--mode", choices=["prod", "bootstrap"], default="prod")
    ap.add_argument("--soft-fail", action="store_true", help="Nunca regresa exitcode != 0 (solo WARN)")
    ap.add_argument("--min-price-rate", type=float, default=GateThresholds.min_price_rate)
    ap.add_argument("--min-desc-rate", type=float, default=GateThresholds.min_desc_rate)
    ap.add_argument("--min-image-rate", type=float, default=GateThresholds.min_image_rate)
    args = ap.parse_args()

    if not os.path.exists(args.report):
        print(f"canonical_quality_gate: FAIL\n- reason: missing_report\n- report: {args.report}")
        return 2

    report = _load_json(args.report)
    canonical_csv = report.get("canonical_csv") or report.get("paths", {}).get("canonical_csv") or ""
    total, fp, fi, fd = _extract_counts(report)

    price_rate = _rate(fp, total)
    image_rate = _rate(fi, total)
    desc_rate = _rate(fd, total)

    thresholds = GateThresholds(
        min_price_rate=float(args.min_price_rate),
        min_desc_rate=float(args.min_desc_rate),
        min_image_rate=float(args.min_image_rate),
    )

    problems: List[str] = []

    # Seed exception: solo ignora image_rate
    seed_exception = _is_seed_exception(report, args.allow_seed)

    if price_rate < thresholds.min_price_rate:
        problems.append(f"price_rate={price_rate:.3f} < {thresholds.min_price_rate:.3f}")
    if desc_rate < thresholds.min_desc_rate:
        problems.append(f"desc_rate={desc_rate:.3f} < {thresholds.min_desc_rate:.3f}")
    if (not seed_exception) and (image_rate < thresholds.min_image_rate):
        problems.append(f"image_rate={image_rate:.3f} < {thresholds.min_image_rate:.3f}")

    status = "OK" if not problems else "FAIL"
    suffix = " (seed exception)" if (seed_exception and status == "OK") else ""

    print(f"canonical_quality_gate: {status}{suffix}")
    print(f"- source: canonical_csv")
    print(f"- canonical_csv: {canonical_csv}")
    print(f"- total_ids: {total}")
    print(f"- rates: price={price_rate:.3f} image={image_rate:.3f} desc={desc_rate:.3f}")
    print(f"- counts: {{'total_rows': {total}, 'filled_price': {fp}, 'filled_image': {fi}, 'filled_desc': {fd}}}")

    if problems:
        print(f"- problems: {problems}")
        print("")
        print("Meaning:")
        print("Your canonical evidence is missing core catalog fields (price/image/description) at acceptable rates.")
        print("Fix input evidence (API/full export) or run bootstrap mode until evidence is richer.")

    if not problems:
        return 0

    # Bootstrap: por default NO debe tumbarte el pipeline (si usas --soft-fail)
    if args.soft_fail or args.mode == "bootstrap":
        print("WARN: canonical quality gate failed, but continuing (soft-fail/bootstrap).")
        return 0

    return 3


if __name__ == "__main__":
    raise SystemExit(main())

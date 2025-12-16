from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# -----------------------------------------------------------------------------
# Fix imports when running as: python scripts\run_launch_dossier.py
# -----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.scoring import BayesianScore  # noqa: E402


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_composite(price: float, cost: float, shipping: float, rating: float, reviews: int) -> Tuple[float, float]:
    if price <= 0:
        margin = 0.0
    else:
        margin = (price - cost - shipping) / price

    m = clip(margin, 0.0, 1.0) * 0.4
    r = clip(rating / 5.0, 0.0, 1.0) * 0.3
    rv = clip(min(reviews, 500) / 500.0, 0.0, 1.0) * 0.3
    return (m + r + rv) * 100.0, margin


def load_evidence(product_id: str, evidence_dir: Path) -> Dict[str, Any] | None:
    p = evidence_dir / f"{product_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _to_int(x: Any) -> int:
    try:
        if x is None:
            return 0
        if isinstance(x, bool):
            return int(x)
        return int(float(x))
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=r"data\catalog\candidates_real.csv")
    ap.add_argument("--threshold", type=float, default=75.0, help="umbral de score (0..100)")
    ap.add_argument("--evidence-dir", default=r"data\evidence\products")
    ap.add_argument("--min-prob", type=float, default=0.55, help="probabilidad mínima para LAUNCH_CANDIDATE")
    args = ap.parse_args()

    csv_path = Path(args.path)
    evidence_dir = Path(args.evidence_dir)

    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            rows.append(row)

    results = []
    for row in rows:
        pid = str(row.get("product_id", "")).strip()
        title = str(row.get("title", "")).strip()

        price = float(row.get("price", 0) or 0)
        cost = float(row.get("cost", 0) or 0)
        shipping = float(row.get("shipping_cost", 0) or 0)
        rating = float(row.get("rating", 0) or 0)
        reviews = _to_int(row.get("reviews", 0) or 0)

        composite, margin = compute_composite(price, cost, shipping, rating, reviews)

        ev = load_evidence(pid, evidence_dir)
        has_evidence = ev is not None and bool(ev.get("supplier_url"))

        # -------------------------------
        # Confidence proxy (ACERO):
        # - reviews = señal fuerte
        # - sold (si existe en evidence) = señal adicional (pero downweighted)
        # -------------------------------
        sold = _to_int((ev or {}).get("sold", 0))
        effective_n = max(reviews + int(0.10 * sold), reviews)

        confidence = clip(effective_n / 2000.0, 0.0, 1.0)

        # BayesianScore en tu repo: (mean: 0..100, confidence: 0..1, sample_size: int)
        score = BayesianScore(mean=composite, confidence=confidence, sample_size=effective_n)

        prob = score.probability_above(float(args.threshold))

        ok_margin = margin >= 0.30
        ok_rating = rating >= 4.6

        if has_evidence and ok_margin and ok_rating and (composite >= args.threshold) and (prob >= float(args.min_prob)):
            status = "LAUNCH_CANDIDATE"
        elif has_evidence and ok_margin and ok_rating and (composite >= 60.0):
            status = "TEST_ONLY"
        else:
            status = "KILL"

        results.append({
            "product_id": pid,
            "title": title,
            "status": status,
            "composite": round(composite, 2),
            "margin": round(margin, 3),
            "confidence": round(confidence, 3),
            "effective_n": int(effective_n),
            "range": (round(score.range_low, 2), round(score.range_high, 2)),
            "prob_above_threshold": round(prob, 3),
            "threshold": float(args.threshold),
            "min_prob": float(args.min_prob),
            "supplier_url": (ev or {}).get("supplier_url", None),
            "sold": int(sold),
            "reviews": int(reviews),
        })

    results.sort(key=lambda x: x["composite"], reverse=True)

    print("\n" + "="*80)
    print("LAUNCH DOSSIER (F1) — DECISION ENGINE")
    print("="*80)
    print(f"CSV: {csv_path.resolve()}")
    print(f"Evidence dir: {evidence_dir.resolve()}")
    print(f"Threshold(score): {float(args.threshold):.2f} | Rule: prob>={float(args.min_prob):.2f} + evidence + margin>=0.30 + rating>=4.6")
    print("Confidence proxy: effective_n = reviews + 0.10*sold (clipped to 2000)\n")

    print("RANKING:")
    for r in results:
        print(
            f"- {r['product_id']} {r['title']} | {r['status']} "
            f"| score={r['composite']:.2f} conf={r['confidence']:.3f} n={r['effective_n']} "
            f"| range={r['range']} prob>={r['threshold']:.0f}={r['prob_above_threshold']:.3f} "
            f"| margin={r['margin']:.3f} | reviews={r['reviews']} sold={r['sold']}"
        )


if __name__ == "__main__":
    main()
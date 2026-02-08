from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__PL_MARKER__ = "POST_LEARNING_2026-01-12_NEXT_ACTIONS_V1"

WEIGHTS_REL = Path("data/config/weights.json")
OUT_REL = Path("data/run/learning_next_actions.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _safe_int(x: Any) -> int:
    try:
        if x is None:
            return 0
        return int(x)
    except Exception:
        return 0


@dataclass(frozen=True)
class ItemScore:
    key: str
    score: float
    roas_mean: float
    spend: float
    count: int


def _score_bucket(bucket: Dict[str, Any]) -> List[ItemScore]:
    """
    bucket item format expected:
      { "count": int, "spend": float, "roas_mean": float, "hook_rate_3s_mean": float }
    Score: roas_mean * log1p(spend)  (sencillo, determinista, orientado a $$)
    Tie-breakers implícitos: spend, count (por score + contenido)
    """
    out: List[ItemScore] = []
    if not isinstance(bucket, dict):
        return out

    for k, v in bucket.items():
        if not isinstance(v, dict):
            continue
        roas = _safe_float(v.get("roas_mean"))
        spend = _safe_float(v.get("spend"))
        count = _safe_int(v.get("count"))
        score = roas * log1p(max(spend, 0.0))
        out.append(ItemScore(key=str(k), score=float(score), roas_mean=float(roas), spend=float(spend), count=int(count)))

    out.sort(key=lambda it: (it.score, it.roas_mean, it.spend, it.count, it.key), reverse=True)
    return out


def _top_k(items: List[ItemScore], k: int = 3) -> List[Dict[str, Any]]:
    return [
        {
            "key": it.key,
            "score": round(it.score, 6),
            "roas_mean": round(it.roas_mean, 6),
            "spend": round(it.spend, 6),
            "count": it.count,
        }
        for it in items[: max(0, int(k))]
    ]


def _pick_best_key(items: List[ItemScore], fallback: str = "unknown") -> str:
    return items[0].key if items else fallback


def _build_utm(hook_id: str, angle: str, fmt: str, version: int = 1) -> str:
    # Compatible con parse_utm_content: Hh0_Adolor_Fhands_V1
    # hook_id ya suele venir como "h0", "h7", etc.
    hook = hook_id.strip() if hook_id else "unknown"
    ang = angle.strip().lower() if angle else "unknown"
    fm = fmt.strip().lower() if fmt else "unknown"
    return f"H{hook}_A{ang}_F{fm}_V{int(version)}"


def generate_next_actions(repo: Path) -> Dict[str, Any]:
    weights_path = repo / WEIGHTS_REL
    out_path = repo / OUT_REL

    weights = _read_json(weights_path)
    ts = _utc_now_z()

    if not weights:
        return {
            "marker": __PL_MARKER__,
            "ts": ts,
            "status": "NO_WEIGHTS",
            "weights_path": str(weights_path),
            "out_path": str(out_path),
            "reason": "weights.json not found or invalid",
        }

    angles = weights.get("angles") or {}
    formats = weights.get("formats") or {}
    hooks = weights.get("hooks") or {}

    angles_scored = _score_bucket(angles if isinstance(angles, dict) else {})
    formats_scored = _score_bucket(formats if isinstance(formats, dict) else {})
    hooks_scored = _score_bucket(hooks if isinstance(hooks, dict) else {})

    best_angle = _pick_best_key(angles_scored, "unknown")
    best_format = _pick_best_key(formats_scored, "unknown")
    best_hook = _pick_best_key(hooks_scored, "unknown")

    utm_content = _build_utm(best_hook, best_angle, best_format, version=1)

    total_spend = _safe_float(weights.get("total_spend"))
    roas_mean = _safe_float(weights.get("roas_mean"))
    records_used = _safe_int(weights.get("records_used"))

    # Playbook mínimo (sin inventar magia)
    # Reglas simples orientadas a acción:
    # - Si roas_mean >= 1.2: scale el combo top, y duplica variando 1 variable
    # - Si 1.0 <= roas_mean < 1.2: iterar hooks/angles
    # - Si roas_mean < 1.0: test agresivo y no escalar
    if roas_mean >= 1.2:
        mode = "SCALE"
        actions = [
            "Scale: duplica presupuesto al combo ganador (siempre con control de riesgo).",
            "Itera: mismo angle+format, prueba 3 hooks nuevos.",
            "Itera: mismo hook+format, prueba 2 angles nuevos.",
        ]
    elif roas_mean >= 1.0:
        mode = "ITERATE"
        actions = [
            "Itera: conserva el formato top, rota hooks (3-5 variantes).",
            "Itera: conserva el hook top, rota angles (2-3 variantes).",
            "No escales todavía: primero confirma estabilidad con más spend.",
        ]
    else:
        mode = "TEST"
        actions = [
            "Test: baja riesgo, crea más variantes (hooks/angles) sin aumentar spend.",
            "Revisa targeting/landing: ROAS bajo suele ser funnel roto, no solo creativo.",
            "No escales: optimiza señal primero.",
        ]

    out = {
        "marker": __PL_MARKER__,
        "ts": ts,
        "status": "OK",
        "repo": str(repo),
        "weights_path": str(weights_path),
        "out_path": str(out_path),
        "weights_meta": {
            "learning_marker": weights.get("marker"),
            "schema_version": weights.get("schema_version"),
            "records_used": records_used,
            "total_spend": round(total_spend, 6),
            "roas_mean": round(roas_mean, 6),
        },
        "top": {
            "angles": _top_k(angles_scored, 3),
            "formats": _top_k(formats_scored, 3),
            "hooks": _top_k(hooks_scored, 3),
        },
        "recommended_combo": {
            "angle": best_angle,
            "format": best_format,
            "hook_id": best_hook,
            "utm_content": utm_content,
        },
        "mode": mode,
        "actions": actions,
    }
    return out


def main() -> int:
    repo = Path.cwd()

    out = generate_next_actions(repo)

    readonly = os.getenv("SYNAPSE_READONLY", "").strip() in ("1", "true", "TRUE", "yes", "YES")
    if out.get("status") == "OK" and not readonly:
        _write_json(repo / OUT_REL, out)

    cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
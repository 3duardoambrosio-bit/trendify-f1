from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


__CB_MARKER__ = "CREATIVE_BRIEFS_2026-01-12_V2_STALE_GUARD"

QUEUE_REL = Path("data/run/creative_queue.json")
OUT_REL = Path("data/run/creative_briefs.json")
OUT_DIR_REL = Path("data/run/creative_briefs")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_readonly() -> bool:
    return os.getenv("SYNAPSE_READONLY", "").strip() in ("1", "true", "TRUE", "yes", "YES")


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


def _brief_for(item: Dict[str, Any], repo: Path, mode: str, source_queue: Path, ts: str) -> Dict[str, Any]:
    angle = str(item.get("angle") or "unknown")
    fmt = str(item.get("format") or "unknown")
    hook_id = str(item.get("hook_id") or "unknown")
    utm = str(item.get("utm_content") or "unknown")
    cid = str(item.get("id") or "")

    # Script template: simple, compliance-safe
    on_screen = [
        "¿Te pasa esto?",
        "beneficio principal (sin claims médicos)",
        "Rápido. Simple. Sin rollos.",
        "2x1 / envío gratis / -20%",
        "Compra aquí",
    ]

    shotlist = [
        "Close-up manos mostrando el problema (antes)",
        "Producto en mano + unboxing rápido",
        "Demostración clara (cómo se usa)",
        "Reacción/gesto (alivio/satisfacción)",
        "Texto en pantalla: beneficio #1, #2",
        "Pantalla final: oferta + CTA",
    ]

    # Hook line rotates by hook_id just to avoid clones
    hook_line = {
        "h7": "3 señales de que necesitas una solución ya (la #2 es la peor).",
        "h8": "Esto NO es normal: si sientes molestia seguido, te va a servir.",
        "h9": "Si te duele tu producto y ya probaste de todo… ve esto.",
    }.get(hook_id.lower(), "Te voy a enseñar cómo beneficio principal (sin claims médicos) sin complicarte.")

    structure = [
        {"beat": "HOOK", "t": "0-2s", "script": hook_line},
        {"beat": "PROBLEM", "t": "2-6s", "script": "Yo era de los que aguantaban… hasta que se vuelve diario. quién lo sufre entiende."},
        {"beat": "DEMO", "t": "6-12s", "script": "Manos a cuadro: enseña el uso y el antes/después. Enfócate en la sensación: beneficio principal (sin claims médicos)."},
        {"beat": "PROOF", "t": "12-18s", "script": "Menciona 1 beneficio concreto + 1 beneficio emocional. (Sin claims médicos raros)."},
        {"beat": "OFFER", "t": "18-22s", "script": "Hoy hay 2x1 / envío gratis / -20%. Si lo vas a probar, que sea con descuento."},
        {"beat": "CTA", "t": "22-25s", "script": "Compra aquí. Link en bio / botón de comprar."},
    ]

    return {
        "id": cid,
        "priority": int(item.get("priority") or 0),
        "rationale": str(item.get("rationale") or ""),
        "angle": angle,
        "format": fmt,
        "hook_id": hook_id,
        "utm_content": utm,
        "metadata": {
            "marker": __CB_MARKER__,
            "ts": ts,
            "mode": mode,
            "source_queue": str(source_queue),
        },
        "script": {
            "angle": angle,
            "format": fmt,
            "hook_id": hook_id,
            "do_not": [
                "No uses claims médicos (curar, tratar enfermedades, etc.)",
                "No prometas resultados garantizados",
                "No metas 10 ideas: una idea, bien ejecutada",
            ],
            "on_screen_text": on_screen,
            "shotlist": shotlist,
            "structure": structure,
        },
    }


def generate(repo: Path) -> Dict[str, Any]:
    ts = _utc_now_z()
    q_path = repo / QUEUE_REL
    out_path = repo / OUT_REL
    out_dir = repo / OUT_DIR_REL

    q = _read_json(q_path)
    if not q or q.get("status") != "OK":
        return {
            "marker": __CB_MARKER__,
            "ts": ts,
            "status": "NO_QUEUE",
            "repo": str(repo),
            "queue_path": str(q_path),
            "out_path": str(out_path),
            "out_dir": str(out_dir),
            "reason": "creative_queue.json missing or not OK. Run creative_queue cuando toque (con next_actions OK).",
            "count": 0,
            "briefs": [],
        }

    mode = str(q.get("mode") or "UNKNOWN")
    items = q.get("items") if isinstance(q.get("items"), list) else []

    briefs: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        briefs.append(_brief_for(it, repo=repo, mode=mode, source_queue=q_path, ts=ts))

    out = {
        "marker": __CB_MARKER__,
        "ts": ts,
        "status": "OK",
        "repo": str(repo),
        "queue_path": str(q_path),
        "out_path": str(out_path),
        "out_dir": str(out_dir),
        "count": len(briefs),
        "briefs": briefs,
    }
    return out


def main(argv: Optional[List[str]] = None) -> int:
    _ = argparse.ArgumentParser(prog="synapse.creative_briefs", description="Generate creative briefs from creative_queue.json (stale-guarded).").parse_args(argv)

    repo = Path.cwd()
    out = generate(repo)

    if out.get("status") == "OK" and not _is_readonly():
        _write_json(repo / OUT_REL, out)
        (repo / OUT_DIR_REL).mkdir(parents=True, exist_ok=True)
        for b in out.get("briefs", []):
            if isinstance(b, dict) and b.get("id"):
                _write_json(repo / OUT_DIR_REL / f"{b['id']}.json", b)

    cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if out.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
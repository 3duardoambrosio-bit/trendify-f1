from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


__CQ_MARKER__ = "CREATIVE_QUEUE_2026-01-12_V2_STALE_GUARD"

NEXT_ACTIONS_REL = Path("data/run/learning_next_actions.json")
OUT_REL = Path("data/run/creative_queue.json")


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


def _build_utm(hook_id: str, angle: str, fmt: str, version: int = 1) -> str:
    hook = (hook_id or "unknown").strip()
    ang = (angle or "unknown").strip().lower()
    fm = (fmt or "unknown").strip().lower()
    return f"H{hook}_A{ang}_F{fm}_V{int(version)}"


def _id_for_utm(utm_content: str) -> str:
    h = hashlib.sha256(utm_content.encode("utf-8")).hexdigest()
    return h[:16]


def _hook_num(hook_id: str) -> int:
    # "h9" -> 9, "h10" -> 10
    s = (hook_id or "").strip().lower()
    if not s.startswith("h"):
        return -1
    try:
        return int(s[1:])
    except Exception:
        return -1


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    try:
        s = str(x).strip()
        return s if s else default
    except Exception:
        return default


def generate_queue(repo: Path, extra_hooks: int = 0) -> Dict[str, Any]:
    ts = _utc_now_z()
    next_path = repo / NEXT_ACTIONS_REL
    out_path = repo / OUT_REL

    na = _read_json(next_path)
    if not na or na.get("status") != "OK":
        out = {
            "marker": __CQ_MARKER__,
            "ts": ts,
            "status": "NO_NEXT_ACTIONS",
            "repo": str(repo),
            "next_actions_path": str(next_path),
            "out_path": str(out_path),
            "reason": "learning_next_actions.json missing or not OK. Run: runner -> post_learning primero (cuando toque).",
            "count": 0,
            "items": [],
        }
        return out

    mode = _safe_str(na.get("mode"), "UNKNOWN")
    rec = na.get("recommended_combo") or {}
    top = na.get("top") or {}

    angle = _safe_str(rec.get("angle"), "unknown")
    fmt = _safe_str(rec.get("format"), "unknown")
    winner_hook = _safe_str(rec.get("hook_id"), "unknown")

    # top hooks list expected like: [{"key":"h9", ...}, {"key":"h8", ...}, ...]
    top_hooks = top.get("hooks") if isinstance(top, dict) else []
    hook_keys: List[str] = []
    if isinstance(top_hooks, list):
        for it in top_hooks:
            if isinstance(it, dict) and str(it.get("key") or "").strip():
                hook_keys.append(str(it["key"]).strip())

    # Ensure winner first
    ordered_hooks: List[str] = []
    if winner_hook and winner_hook != "unknown":
        ordered_hooks.append(winner_hook)

    # Then best other hooks (rotate)
    for hk in hook_keys:
        if hk not in ordered_hooks:
            ordered_hooks.append(hk)

    # Keep: winner + up to 2 rotates
    base_hooks = ordered_hooks[:3] if ordered_hooks else ["h0", "h1", "h2"]
    winner = base_hooks[0]

    # Extra new hook variants: h{max+1}..h{max+n}
    max_n = max([_hook_num(h) for h in base_hooks] + [-1])
    new_hooks: List[str] = []
    for i in range(max(0, _safe_int(extra_hooks, 0))):
        max_n += 1
        new_hooks.append(f"h{max_n}")

    # Build queue items
    items: List[Dict[str, Any]] = []

    def push(hook_id: str, priority: int, rationale: str) -> None:
        utm = _build_utm(hook_id, angle=angle, fmt=fmt, version=1)
        items.append(
            {
                "id": _id_for_utm(utm),
                "angle": angle,
                "format": fmt,
                "hook_id": hook_id,
                "utm_content": utm,
                "priority": int(priority),
                "rationale": rationale,
            }
        )

    push(winner, 100, "Main winner combo (scale-first)")

    rotates = [h for h in base_hooks[1:] if h != winner]
    if len(rotates) >= 1:
        push(rotates[0], 89, "Same angle+format, rotate top hooks")
    if len(rotates) >= 2:
        push(rotates[1], 88, "Same angle+format, rotate top hooks")

    # New variants
    pr = 80
    for h in new_hooks:
        push(h, pr, "Same angle+format, new hook variants")
        pr -= 1

    out = {
        "marker": __CQ_MARKER__,
        "ts": ts,
        "status": "OK",
        "repo": str(repo),
        "mode": mode,
        "next_actions_path": str(next_path),
        "out_path": str(out_path),
        "count": len(items),
        "items": items,
    }
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.creative_queue", description="Generate creative queue from learning_next_actions.json (stale-guarded).")
    ap.add_argument("--extra-hooks", type=int, default=0, help="How many NEW hook variants to add after top hooks.")
    args = ap.parse_args(argv)

    repo = Path.cwd()
    out = generate_queue(repo, extra_hooks=int(args.extra_hooks))

    if out.get("status") == "OK" and not _is_readonly():
        _write_json(repo / OUT_REL, out)

    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if out.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
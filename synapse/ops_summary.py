from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


__MARKER__ = "OPS_SUMMARY_2026-01-13_V1"

PATH_OPS_TICK = Path("data/run/ops_tick.json")
PATH_ACTIONS = Path("data/run/learning_next_actions.json")
PATH_QUEUE = Path("data/run/creative_queue.json")
PATH_BRIEFS = Path("data/run/creative_briefs.json")

OUT_TXT = Path("data/run/ops_summary.txt")
OUT_JSON = Path("data/run/ops_summary.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        if not p.exists():
            return None
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default
    return cur if cur is not None else default


def _fmt_list(xs: List[str], prefix: str = "- ") -> str:
    if not xs:
        return f"{prefix}(vacío)"
    return "\n".join(prefix + str(x) for x in xs)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.ops_summary", description="Short human summary of latest Phase-1 tick outputs.")
    ap.add_argument("--json", action="store_true", help="Print JSON summary only (no text).")
    args = ap.parse_args(argv)

    ops = _read_json(PATH_OPS_TICK) or {}
    actions = _read_json(PATH_ACTIONS) or {}
    queue = _read_json(PATH_QUEUE) or {}
    briefs = _read_json(PATH_BRIEFS) or {}

    # Extract key facts
    status = _safe_get(ops, "status", "UNKNOWN")
    effective_readonly = _safe_get(ops, "inputs.effective_readonly", None)
    ledger_ok = _safe_get(ops, "checks.readonly_invariant_ok", None)

    mode = _safe_get(actions, "mode", "UNKNOWN")
    combo = _safe_get(actions, "recommended_combo", {}) or {}
    winner_utm = _safe_get(combo, "utm_content", "UNKNOWN")
    winner_hook = _safe_get(combo, "hook_id", "UNKNOWN")
    winner_angle = _safe_get(combo, "angle", "UNKNOWN")
    winner_format = _safe_get(combo, "format", "UNKNOWN")

    top_hooks = _safe_get(actions, "top.hooks", []) or []
    top_hooks_str = []
    for h in top_hooks[:5]:
        if isinstance(h, dict):
            top_hooks_str.append(f"{h.get('key')} | roas_mean={h.get('roas_mean')} | spend={h.get('spend')} | n={h.get('count')}")
    if not top_hooks_str:
        top_hooks_str = ["(sin top hooks)"]

    items = _safe_get(queue, "items", []) or []
    queue_lines = []
    for it in items[:10]:
        if isinstance(it, dict):
            queue_lines.append(f"{it.get('priority', 0)}  {it.get('utm_content')}  ({it.get('rationale')})")
    if not queue_lines:
        queue_lines = ["(queue vacío)"]

    brief_count = _safe_get(briefs, "count", None)
    if brief_count is None:
        # sometimes briefs file is a dict with "briefs": [...]
        bl = _safe_get(briefs, "briefs", []) or []
        brief_count = len(bl) if isinstance(bl, list) else 0

    out = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "ops_tick_path": str(PATH_OPS_TICK.resolve()),
        "status": status,
        "effective_readonly": effective_readonly,
        "readonly_invariant_ok": ledger_ok,
        "mode": mode,
        "winner": {
            "utm_content": winner_utm,
            "hook_id": winner_hook,
            "angle": winner_angle,
            "format": winner_format,
        },
        "top_hooks": top_hooks_str,
        "queue_top": queue_lines,
        "briefs_count": int(brief_count or 0),
        "paths": {
            "learning_next_actions": str(PATH_ACTIONS.resolve()),
            "creative_queue": str(PATH_QUEUE.resolve()),
            "creative_briefs": str(PATH_BRIEFS.resolve()),
        },
    }

    # write outputs
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    text = []
    text.append("=== SYNAPSE OPS SUMMARY (Phase-1) ===")
    text.append(f"ts: {_safe_get(out,'ts')}")
    text.append(f"status: {status}")
    text.append(f"readonly: {effective_readonly} | invariant_ok: {ledger_ok}")
    text.append("")
    text.append(f"MODE: {mode}")
    text.append(f"WINNER: {winner_utm}  (hook={winner_hook} angle={winner_angle} format={winner_format})")
    text.append("")
    text.append("TOP HOOKS:")
    text.append(_fmt_list(top_hooks_str))
    text.append("")
    text.append("CREATIVE QUEUE (top):")
    text.append(_fmt_list(queue_lines))
    text.append("")
    text.append(f"BRIEFS: {brief_count}")
    text.append("")
    text.append("PATHS:")
    text.append(_fmt_list([f"{k}: {v}" for k, v in out["paths"].items()]))

    OUT_TXT.write_text("\n".join(text) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("\n".join(text))
        print(f"\n(wrote) {OUT_TXT.resolve()}")
        print(f"(wrote) {OUT_JSON.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
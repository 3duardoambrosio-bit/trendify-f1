from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__CP_MARKER__ = "CREATIVE_PUBLISHER_2026-01-12_V2_STALE_GUARD"

BRIEFS_REL = Path("data/run/creative_briefs.json")
STATE_REL = Path("data/run/creative_publish_state.json")
LEDGER_REL = Path("data/ledger/events.ndjson")


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
    except (json.JSONDecodeError, TypeError):
        return None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _payload_hash(obj: Dict[str, Any]) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def _load_state(repo: Path) -> Dict[str, Any]:
    st = _read_json(repo / STATE_REL)
    if not st:
        st = {}
    if not isinstance(st, dict):
        st = {}
    st.setdefault("produced", {})
    st.setdefault("launched", {})
    if not isinstance(st["produced"], dict):
        st["produced"] = {}
    if not isinstance(st["launched"], dict):
        st["launched"] = {}
    return st


def _save_state(repo: Path, st: Dict[str, Any]) -> None:
    st["marker"] = __CP_MARKER__
    st["ts"] = _utc_now_z()
    st["produced_count"] = len(st.get("produced") or {})
    st["launched_count"] = len(st.get("launched") or {})
    _write_json(repo / STATE_REL, st)


def _read_briefs(repo: Path) -> Tuple[Optional[Dict[str, Any]], Path]:
    p = repo / BRIEFS_REL
    obj = _read_json(p)
    return obj, p


def _items_from_briefs(briefs_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    briefs = briefs_obj.get("briefs") if isinstance(briefs_obj.get("briefs"), list) else []
    out: List[Dict[str, Any]] = []
    for b in briefs:
        if not isinstance(b, dict):
            continue
        cid = str(b.get("id") or "").strip()
        if not cid:
            continue
        out.append(
            {
                "id": cid,
                "priority": int(b.get("priority") or 0),
                "rationale": str(b.get("rationale") or ""),
                "creative": {
                    "angle": str(b.get("angle") or "unknown"),
                    "format": str(b.get("format") or "unknown"),
                    "hook_id": str(b.get("hook_id") or "unknown"),
                    "utm_content": str(b.get("utm_content") or "unknown"),
                },
                "recommended_ops": [
                    "PRODUCE: crea el video/creativo usando el brief JSON",
                    "LAUNCH: súbelo a la plataforma y pega el external_id aquí",
                    "IMPORT_RESULTS: cuando tengas métricas, importa CSV al ledger",
                ],
            }
        )
    out.sort(key=lambda x: (x.get("priority", 0), x.get("id", "")), reverse=True)
    return out


def cmd_show(repo: Path) -> int:
    briefs_obj, briefs_path = _read_briefs(repo)
    ts = _utc_now_z()

    if not briefs_obj or briefs_obj.get("status") != "OK":
        out = {
            "marker": __CP_MARKER__,
            "ts": ts,
            "status": "NO_BRIEFS",
            "repo": str(repo),
            "briefs_path": str(briefs_path),
            "state_path": str(repo / STATE_REL),
            "ledger_path": str(repo / LEDGER_REL),
            "count": 0,
            "items": [],
            "reason": "creative_briefs.json missing or not OK.",
        }
        cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        st = _load_state(repo)
        snap = {
            "marker": __CP_MARKER__,
            "ts": ts,
            "status": "OK",
            "state_path": str(repo / STATE_REL),
            "produced": st.get("produced", {}),
            "launched": st.get("launched", {}),
            "produced_count": len(st.get("produced", {})),
            "launched_count": len(st.get("launched", {})),
        }
        cli_print(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 2

    items = _items_from_briefs(briefs_obj)
    out = {
        "marker": __CP_MARKER__,
        "ts": ts,
        "status": "OK",
        "repo": str(repo),
        "briefs_path": str(briefs_path),
        "state_path": str(repo / STATE_REL),
        "ledger_path": str(repo / LEDGER_REL),
        "count": len(items),
        "items": items,
    }
    cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))

    st = _load_state(repo)
    snap = {
        "marker": __CP_MARKER__,
        "ts": ts,
        "status": "OK",
        "state_path": str(repo / STATE_REL),
        "produced": st.get("produced", {}),
        "launched": st.get("launched", {}),
        "produced_count": len(st.get("produced", {})),
        "launched_count": len(st.get("launched", {})),
    }
    cli_print(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def cmd_plan(repo: Path) -> int:
    # plan == show (misma data, menos drama)
    return cmd_show(repo)


def cmd_mark(repo: Path, cid: str, status: str, platform: str, external_id: str, notes: str) -> int:
    ts = _utc_now_z()
    st = _load_state(repo)

    cid = (cid or "").strip()
    status_u = (status or "").strip().upper()
    platform = (platform or "meta").strip().lower()
    external_id = (external_id or "").strip()
    notes = (notes or "").strip()

    if not cid:
        out = {"marker": __CP_MARKER__, "ts": ts, "status": "BAD_ARGS", "reason": "missing --id"}
        cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 2

    rec = {
        "ts": ts,
        "notes": notes,
        "ext": {"platform": platform, "id": external_id},
    }
    rec["payload_hash"] = _payload_hash({"id": cid, "status": status_u, "rec": rec})

    if status_u == "PRODUCED":
        st["produced"][cid] = rec
    elif status_u == "LAUNCHED":
        st["launched"][cid] = rec
    else:
        out = {"marker": __CP_MARKER__, "ts": ts, "status": "BAD_STATUS", "reason": "use PRODUCED or LAUNCHED"}
        cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 2

    readonly = _is_readonly()
    if not readonly:
        _save_state(repo, st)

    out = {
        "marker": __CP_MARKER__,
        "ts": ts,
        "status": "OK",
        "id": cid,
        "mark": status_u,
        "readonly": bool(readonly),
        "state_path": str(repo / STATE_REL),
        "ledger_path": str(repo / LEDGER_REL),
        "payload_hash": rec.get("payload_hash"),
    }
    cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.creative_publisher", description="Track production/launch state for creative briefs (stale-guarded).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="Show briefs + state snapshot.")
    sub.add_parser("plan", help="Alias of show.")

    sp = sub.add_parser("mark", help="Mark a creative as PRODUCED or LAUNCHED.")
    sp.add_argument("--id", required=True, help="Creative id (from briefs/queue).")
    sp.add_argument("--status", required=True, help="PRODUCED|LAUNCHED")
    sp.add_argument("--platform", default="meta", help="meta|tiktok|google")
    sp.add_argument("--external-id", default="", help="Platform ad id (cuando toque).")
    sp.add_argument("--notes", default="", help="Free notes.")

    args = ap.parse_args(argv)
    repo = Path.cwd()

    if args.cmd == "show":
        return cmd_show(repo)
    if args.cmd == "plan":
        return cmd_plan(repo)
    if args.cmd == "mark":
        return cmd_mark(repo, cid=str(args.id), status=str(args.status), platform=str(args.platform), external_id=str(args.external_id), notes=str(args.notes))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

from synapse.infra.cli_logging import cli_print


import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "META_PUBLISH_EXECUTE_2026-01-17_V7"
LEGACY_META_LIVE_PERMANENTLY_DISABLED = "LEGACY_META_LIVE_PERMANENTLY_DISABLED"

DEFAULT_PLAN = Path("data/run/meta_publish_plan.json")
DEFAULT_OUT = Path("data/run/meta_publish_run.json")
DEFAULT_OUT_DIR = Path("data/run/meta_publish_runs")

ID_REF_RE = re.compile(r"^<ID:([^>]+)>$")
FILE_REF_RE = re.compile(r"^<FILE:([^>]+)>$")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        raise FileNotFoundError(str(p))
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected dict JSON in {p}")
    return obj


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _offline_contract() -> Dict[str, bool]:
    return {
        "offline_only": True,
        "external_write": False,
        "legacy_live_disabled": True,
    }


def _legacy_live_disabled() -> int:
    cli_print(
        json.dumps(
            {
                "marker": __MARKER__,
                "mode": "live",
                "status": "FAIL",
                "diagnostic": LEGACY_META_LIVE_PERMANENTLY_DISABLED,
                **_offline_contract(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 2


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(raw)


def _load_json_arg(s: str) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    s = s.strip()
    if s.startswith("@"):
        p = Path(s[1:]).expanduser().resolve()
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError(f"JSON in {p} must be an object/dict")
        return obj
    obj = json.loads(s)
    if not isinstance(obj, dict):
        raise ValueError("JSON must be an object/dict")
    return obj


@dataclass
class RuntimeInputs:
    daily_budget_minor_units: Optional[int]
    targeting_json: Optional[Dict[str, Any]]
    promoted_object_json: Optional[Dict[str, Any]]
    meta_page_id: Optional[str]
    meta_ig_actor_id: Optional[str]
    meta_pixel_id: Optional[str]
    status_override: Optional[str]


def _resolve_placeholders(obj: Any, id_map: Dict[str, str], rt: RuntimeInputs) -> Any:
    if isinstance(obj, dict):
        return {k: _resolve_placeholders(v, id_map, rt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_placeholders(v, id_map, rt) for v in obj]
    if isinstance(obj, str):
        m = ID_REF_RE.match(obj)
        if m:
            key = m.group(1)
            return id_map.get(key, obj)

        if obj == "<DAILY_BUDGET_MINOR_UNITS>":
            return rt.daily_budget_minor_units if rt.daily_budget_minor_units is not None else obj

        if obj == "<TARGETING_JSON>":
            if rt.targeting_json is None:
                return obj
            return _resolve_placeholders(rt.targeting_json, id_map, rt)

        if obj == "<PROMOTED_OBJECT_JSON>":
            if rt.promoted_object_json is None:
                return obj
            return _resolve_placeholders(rt.promoted_object_json, id_map, rt)

        if obj == "<META_PAGE_ID>":
            return rt.meta_page_id if rt.meta_page_id else obj

        if obj == "<META_IG_ACTOR_ID>":
            return rt.meta_ig_actor_id if rt.meta_ig_actor_id else obj

        if obj == "<META_PIXEL_ID>":
            return rt.meta_pixel_id if rt.meta_pixel_id else obj

        return obj
    return obj


def _find_unresolved(obj: Any, *, ignore_file_refs: bool = False) -> List[str]:
    unresolved: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            if x.startswith("<") and x.endswith(">"):
                if ignore_file_refs and FILE_REF_RE.match(x):
                    return
                unresolved.append(x)

    walk(obj)

    seen = set()
    out: List[str] = []
    for u in unresolved:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _simulate_id(key: str, plan_hash: str) -> str:
    h = hashlib.sha256((plan_hash + "|" + key).encode("utf-8")).hexdigest()[:12].upper()
    if key.startswith("meta:video:"):
        return f"SIMVID_{h}"
    if key.startswith("meta:campaign:"):
        return f"SIMCAMP_{h}"
    if key.startswith("meta:adset:"):
        return f"SIMADSET_{h}"
    if key.startswith("meta:creative:"):
        return f"SIMCREA_{h}"
    if key.startswith("meta:ad:"):
        return f"SIMAD_{h}"
    return f"SIM_{h}"


def _dry_print_steps(plan: Dict[str, Any]) -> None:
    steps = plan.get("steps", [])
    cli_print("=== META PUBLISH EXECUTE (DRY) ===")
    cli_print("offline_only=true")
    cli_print("external_write=false")
    cli_print("legacy_live_disabled=true")
    cli_print(f"marker: {plan.get('marker')}")
    cli_print(f"plan_hash: {plan.get('plan_hash')}")
    cli_print(f"graph_version: {plan.get('graph_version')}")
    cli_print(f"ad_account: {plan.get('ad_account')}")
    cli_print(f"steps: {len(steps)}")
    cli_print("")
    for s in steps:
        if not isinstance(s, dict):
            continue
        cli_print(f"- {s.get('i')}: {s.get('op')}  key={s.get('key')}  deps={s.get('depends_on', [])}  endpoint={s.get('endpoint')}")


def _repo_root_from_plan(plan_path: Path) -> Path:
    # data/run/meta_publish_plan.json -> repo root is parents[2]
    try:
        return plan_path.parents[2]
    except (KeyError, IndexError, TypeError):
        return Path.cwd().resolve()


def _runtime_snapshot(
    rt: RuntimeInputs,
    *,
    mode: str,
    meta_aid: str,
    graph_version: str,
    file_fps: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    # No secrets. Only SAFE knobs.
    targeting_h = _sha256_obj(rt.targeting_json)[:12] if rt.targeting_json else ""
    promoted_h = _sha256_obj(rt.promoted_object_json)[:12] if rt.promoted_object_json else ""

    snap: Dict[str, Any] = {
        "mode": mode,
        "graph_version": graph_version,
        "meta_ad_account_id": meta_aid or "",
        "daily_budget_minor_units": rt.daily_budget_minor_units,
        "targeting_sha12": targeting_h,
        "promoted_object_sha12": promoted_h,
        "meta_page_id": rt.meta_page_id or "",
        "meta_ig_actor_id": rt.meta_ig_actor_id or "",
        "meta_pixel_id": rt.meta_pixel_id or "",
        "status_override": rt.status_override or "",
    }

    # Add file fingerprints (strong safety)
    if file_fps is not None:
        snap["file_fingerprints"] = {
            "algo": file_fps.get("algo"),
            "count": file_fps.get("count"),
            "missing": file_fps.get("missing"),
            "overall_sha12": file_fps.get("overall_sha12"),
            "overall_sha256": file_fps.get("overall_sha256"),
            "entries": file_fps.get("entries", {}),
        }

    return snap


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="synapse.meta_publish_execute",
        description="Execute a Meta publish plan locally in DRY/SIMULATE mode; legacy LIVE is permanently disabled.",
    )
    ap.add_argument("--plan", default=str(DEFAULT_PLAN), help="Path to meta_publish_plan.json")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output run report JSON")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory to store run history JSON")
    ap.add_argument("--mode", default="dry", choices=["dry", "simulate", "live"], help="dry|simulate|live (live is disabled)")
    ap.add_argument("--continue-on-error", action="store_true", help="Legacy compatibility flag; live remains disabled.")

    # Runtime injects
    ap.add_argument("--daily-budget", default="", help="DAILY_BUDGET_MINOR_UNITS (e.g. 500 = $5.00)")
    ap.add_argument("--targeting-json", default="", help="TARGETING_JSON as raw JSON or @file.json")
    ap.add_argument("--promoted-object-json", default="", help="PROMOTED_OBJECT_JSON as raw JSON or @file.json")
    ap.add_argument("--page-id", default="", help="META_PAGE_ID")
    ap.add_argument("--ig-actor-id", default="", help="META_IG_ACTOR_ID")
    ap.add_argument("--pixel-id", default="", help="META_PIXEL_ID")
    ap.add_argument("--status", default="", help="Override status for created objects (PAUSED/ACTIVE)")

    # Ledger controls
    ap.add_argument("--ledger-dir", default="data/ledger", help="Ledger directory (default data/ledger)")
    ap.add_argument("--ledger-disable", action="store_true", help="Legacy compatibility flag; live remains disabled.")

    args = ap.parse_args(argv)
    mode = _safe_str(args.mode, "dry").lower()
    if mode == "live":
        return _legacy_live_disabled()

    plan_path = Path(args.plan).resolve()
    out_path = Path(args.out).resolve()
    out_dir = Path(args.out_dir).resolve()

    plan = _read_json(plan_path)
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")

    # unique keys
    keys: List[str] = []
    for s in steps:
        if isinstance(s, dict):
            keys.append(_safe_str(s.get("key")))
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate step keys detected in plan")

    plan_hash = _safe_str(plan.get("plan_hash"), "")
    if not plan_hash.startswith("sha256:"):
        plan_hash = "sha256:" + _sha256_obj(plan.get("steps", []))

    daily_budget_int: Optional[int] = None
    if _safe_str(args.daily_budget, ""):
        try:
            daily_budget_int = int(_safe_str(args.daily_budget, ""))
        except (ValueError, TypeError):
            raise ValueError("--daily-budget must be an integer (minor units)")

    rt = RuntimeInputs(
        daily_budget_minor_units=daily_budget_int,
        targeting_json=_load_json_arg(_safe_str(args.targeting_json, "")),
        promoted_object_json=_load_json_arg(_safe_str(args.promoted_object_json, "")),
        meta_page_id=_safe_str(args.page_id, "") or None,
        meta_ig_actor_id=_safe_str(args.ig_actor_id, "") or None,
        meta_pixel_id=_safe_str(args.pixel_id, "") or None,
        status_override=_safe_str(args.status, "").upper() or None,
    )

    # Dry mode: keep it fast and readable
    if mode == "dry":
        _dry_print_steps(plan)
        tmp_id_map: Dict[str, str] = {}
        unresolved_all: Dict[str, List[str]] = {}
        for s in steps:
            if not isinstance(s, dict):
                continue
            payload = s.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            payload2 = _resolve_placeholders(payload, tmp_id_map, rt)
            unresolved = _find_unresolved(payload2)
            if unresolved:
                unresolved_all[_safe_str(s.get("key"))] = unresolved

        cli_print("")
        cli_print("UNRESOLVED PLACEHOLDERS (given current flags):")
        if not unresolved_all:
            cli_print("- none")
        else:
            for k, u in unresolved_all.items():
                cli_print(f"- {k}: {u}")
        return 0

    # env knobs (safe)
    meta_aid = _safe_str(os.getenv("META_AD_ACCOUNT_ID"), "")
    graph_version = _safe_str(plan.get("graph_version"), "v25.0")

    repo_root = _repo_root_from_plan(plan_path)

    # File fingerprints (strong safety; affects run_fingerprint)
    from synapse.infra.file_fingerprint import compute_file_fingerprints_from_steps

    file_fps = compute_file_fingerprints_from_steps([s for s in steps if isinstance(s, dict)], cwd=repo_root)

    # fingerprint (SAFE, no secrets)
    from synapse.infra.run_fingerprint import compute_run_fingerprint

    runtime_snapshot = _runtime_snapshot(rt, mode=mode, meta_aid=meta_aid, graph_version=graph_version, file_fps=file_fps)
    run_fp = compute_run_fingerprint(plan_hash=plan_hash, runtime_snapshot=runtime_snapshot)

    id_map: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for s in steps:
        if not isinstance(s, dict):
            continue

        op = _safe_str(s.get("op"))
        key = _safe_str(s.get("key"))
        endpoint = _safe_str(s.get("endpoint"))
        depends_on = s.get("depends_on", [])
        if not isinstance(depends_on, list):
            depends_on = []

        payload = s.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        payload2 = dict(payload)
        if rt.status_override and "status" in payload2:
            payload2["status"] = rt.status_override

        payload2 = _resolve_placeholders(payload2, id_map, rt)

        ignore_file_refs = (op == "upload_video")
        unresolved = _find_unresolved(payload2, ignore_file_refs=ignore_file_refs)

        endpoint_resolved = endpoint
        if meta_aid:
            endpoint_resolved = endpoint_resolved.replace("<META_AD_ACCOUNT_ID>", meta_aid)

        step_report: Dict[str, Any] = {
            "i": s.get("i"),
            "key": key,
            "op": op,
            "endpoint": endpoint,
            "endpoint_resolved": endpoint_resolved,
            "depends_on": depends_on,
            "unresolved": unresolved,
            "status": "OK",
            **_offline_contract(),
        }

        sid = _simulate_id(key, plan_hash)
        id_map[key] = sid
        step_report["simulated_id"] = sid
        results.append(step_report)

    run = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "mode": mode,
        "plan_path": str(plan_path),
        "plan_hash": plan_hash,
        "run_fingerprint": run_fp.fingerprint,
        "run_fingerprint_12": run_fp.fingerprint_12,
        "runtime_snapshot": runtime_snapshot,
        "graph_version": graph_version,
        "counts": {"steps": len(steps), "results": len(results), "errors": len(errors)},
        "id_map": id_map,
        "results": results,
        "errors": errors,
        "status": "OK" if not errors else "FAIL",
        "ledger": {
            "enabled": False,
            "dir": str(Path(args.ledger_dir).resolve()),
            "scope": "run_fingerprint",
        },
        "files": {"count": file_fps.get("count"), "missing": file_fps.get("missing"), "overall_sha12": file_fps.get("overall_sha12")},
        **_offline_contract(),
    }

    _write_json(out_path, run)
    out_dir.mkdir(parents=True, exist_ok=True)
    hist_name = f"meta_publish_run_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _write_json(out_dir / hist_name, run)

    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": run["ts"],
        "mode": mode,
        "status": run["status"],
        "out": str(out_path),
        "history": str(out_dir / hist_name),
        "counts": run["counts"],
        "ledger": run["ledger"],
        "run_fingerprint_12": run_fp.fingerprint_12,
        "files": run["files"],
        **_offline_contract(),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if run["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())

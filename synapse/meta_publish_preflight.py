from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from synapse.meta_publish_execute import (
    _read_json,
    _safe_str,
    _sha256_obj,
    _load_json_arg,
    _resolve_placeholders,
    _find_unresolved,
    _simulate_id,
    RuntimeInputs,
)

from synapse.infra.run_fingerprint import compute_run_fingerprint
from synapse.infra.file_fingerprint import compute_file_fingerprints_from_steps

__MARKER__ = "META_PUBLISH_PREFLIGHT_2026-01-17_V4"
DEFAULT_OUT = Path("data/run/meta_publish_preflight.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _scan_placeholders(steps: List[Dict[str, Any]]) -> Dict[str, bool]:
    flags = {
        "needs_daily_budget": False,
        "needs_targeting": False,
        "needs_promoted_object": False,
        "needs_page_id": False,
        "needs_ig_actor_id": False,
        "needs_pixel_id": False,
        "has_file_refs": False,
    }

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            if x == "<DAILY_BUDGET_MINOR_UNITS>":
                flags["needs_daily_budget"] = True
            elif x == "<TARGETING_JSON>":
                flags["needs_targeting"] = True
            elif x == "<PROMOTED_OBJECT_JSON>":
                flags["needs_promoted_object"] = True
            elif x == "<META_PAGE_ID>":
                flags["needs_page_id"] = True
            elif x == "<META_IG_ACTOR_ID>":
                flags["needs_ig_actor_id"] = True
            elif x == "<META_PIXEL_ID>":
                flags["needs_pixel_id"] = True
            elif x.startswith("<FILE:") and x.endswith(">"):
                flags["has_file_refs"] = True

    for s in steps:
        payload = s.get("payload", {})
        walk(payload)

    return flags


def _repo_root_from_plan(plan_path: Path) -> Path:
    try:
        return plan_path.parents[2]
    except Exception:
        return Path.cwd().resolve()


def _runtime_snapshot(
    rt: RuntimeInputs,
    *,
    mode: str,
    meta_aid: str,
    graph_version: str,
    file_fps: Dict[str, Any],
) -> Dict[str, Any]:
    targeting_h = _sha256_obj(rt.targeting_json)[:12] if rt.targeting_json else ""
    promoted_h = _sha256_obj(rt.promoted_object_json)[:12] if rt.promoted_object_json else ""

    snap: Dict[str, Any] = {
        "mode": mode,  # IMPORTANT: aligned with meta_publish_execute
        "graph_version": graph_version,
        "meta_ad_account_id": meta_aid or "",
        "daily_budget_minor_units": rt.daily_budget_minor_units,
        "targeting_sha12": targeting_h,
        "promoted_object_sha12": promoted_h,
        "meta_page_id": rt.meta_page_id or "",
        "meta_ig_actor_id": rt.meta_ig_actor_id or "",
        "meta_pixel_id": rt.meta_pixel_id or "",
        "status_override": rt.status_override or "",
        "file_fingerprints": {
            "algo": file_fps.get("algo"),
            "count": file_fps.get("count"),
            "missing": file_fps.get("missing"),
            "overall_sha12": file_fps.get("overall_sha12"),
            "overall_sha256": file_fps.get("overall_sha256"),
            "entries": file_fps.get("entries", {}),
        },
    }
    return snap


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="synapse.meta_publish_preflight",
        description="Strict preflight for meta publish plan (offline).",
    )
    ap.add_argument("--plan", default="data/run/meta_publish_plan.json", help="Path to meta_publish_plan.json")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")

    # Preferred flag name to align with execute:
    ap.add_argument("--mode", dest="mode", default="simulate", choices=["simulate", "live"], help="simulate|live")
    # Backward-compatible alias:
    ap.add_argument("--intent", dest="mode", help=argparse.SUPPRESS)

    # Same runtime injects
    ap.add_argument("--daily-budget", default="", help="DAILY_BUDGET_MINOR_UNITS (e.g. 500 = $5.00)")
    ap.add_argument("--targeting-json", default="", help="TARGETING_JSON as raw JSON or @file.json")
    ap.add_argument("--promoted-object-json", default="", help="PROMOTED_OBJECT_JSON as raw JSON or @file.json")
    ap.add_argument("--page-id", default="", help="META_PAGE_ID")
    ap.add_argument("--ig-actor-id", default="", help="META_IG_ACTOR_ID")
    ap.add_argument("--pixel-id", default="", help="META_PIXEL_ID")
    ap.add_argument("--status", default="", help="Override status (PAUSED/ACTIVE)")

    args = ap.parse_args(argv)

    plan_path = Path(args.plan).resolve()
    out_path = Path(args.out).resolve()

    plan = _read_json(plan_path)
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")

    plan_hash = _safe_str(plan.get("plan_hash"), "")
    if not plan_hash.startswith("sha256:"):
        plan_hash = "sha256:" + _sha256_obj(plan.get("steps", []))

    daily_budget_int: Optional[int] = None
    if _safe_str(args.daily_budget, ""):
        try:
            daily_budget_int = int(_safe_str(args.daily_budget, ""))
        except Exception:
            raise ValueError("--daily-budget must be an integer (minor units)")

    status_override = _safe_str(args.status, "")
    if status_override:
        status_override = status_override.upper()
        if status_override not in ("PAUSED", "ACTIVE"):
            raise ValueError("--status must be PAUSED or ACTIVE")

    rt = RuntimeInputs(
        daily_budget_minor_units=daily_budget_int,
        targeting_json=_load_json_arg(_safe_str(args.targeting_json, "")),
        promoted_object_json=_load_json_arg(_safe_str(args.promoted_object_json, "")),
        meta_page_id=_safe_str(args.page_id, "") or None,
        meta_ig_actor_id=_safe_str(args.ig_actor_id, "") or None,
        meta_pixel_id=_safe_str(args.pixel_id, "") or None,
        status_override=status_override or None,
    )

    ph = _scan_placeholders([s for s in steps if isinstance(s, dict)])

    issues: List[Dict[str, Any]] = []

    def err(code: str, msg: str, meta: Optional[Dict[str, Any]] = None) -> None:
        issues.append({"severity": "ERROR", "code": code, "msg": msg, "meta": meta or {}})

    def warn(code: str, msg: str, meta: Optional[Dict[str, Any]] = None) -> None:
        issues.append({"severity": "WARN", "code": code, "msg": msg, "meta": meta or {}})

    if ph["needs_daily_budget"] and rt.daily_budget_minor_units is None:
        err("missing_daily_budget", "Plan usa <DAILY_BUDGET_MINOR_UNITS> pero no diste --daily-budget.")
    if ph["needs_targeting"] and rt.targeting_json is None:
        err("missing_targeting_json", "Plan usa <TARGETING_JSON> pero no diste --targeting-json.")
    if ph["needs_promoted_object"] and rt.promoted_object_json is None:
        err("missing_promoted_object_json", "Plan usa <PROMOTED_OBJECT_JSON> pero no diste --promoted-object-json.")
    if ph["needs_page_id"] and not rt.meta_page_id:
        err("missing_page_id", "Plan usa <META_PAGE_ID> pero no diste --page-id.")
    if ph["needs_ig_actor_id"] and not rt.meta_ig_actor_id:
        err("missing_ig_actor_id", "Plan usa <META_IG_ACTOR_ID> pero no diste --ig-actor-id.")
    if ph["needs_pixel_id"] and not rt.meta_pixel_id:
        warn("missing_pixel_id", "Plan usa <META_PIXEL_ID> pero no diste --pixel-id (ok si aún no trackeas).")

    meta_aid = _safe_str(os.getenv("META_AD_ACCOUNT_ID"), "")
    graph_version = _safe_str(plan.get("graph_version"), "v22.0")
    if args.mode == "live" and not meta_aid:
        warn("meta_ad_account_missing", "Mode=live pero META_AD_ACCOUNT_ID no está en env (API Day pendiente).")

    repo_root = _repo_root_from_plan(plan_path)

    # File fingerprints: included in runtime_snapshot => affects run_fingerprint
    file_fps = compute_file_fingerprints_from_steps([s for s in steps if isinstance(s, dict)], cwd=repo_root)

    missing_paths: List[str] = []
    if int(file_fps.get("missing") or 0) > 0:
        entries = file_fps.get("entries") or {}
        for pth, meta in entries.items():
            if isinstance(meta, dict) and meta.get("missing"):
                missing_paths.append(str(pth))

    if missing_paths:
        if str(args.mode) == "live":
            err("missing_files", "Mode=live y faltan archivos referenciados por <FILE:...> (no se vale volar a ciegas).", {"missing": missing_paths[:50]})
        else:
            warn("missing_files", "Faltan archivos referenciados por <FILE:...> (en simulate no truena, pero ojo).", {"missing": missing_paths[:50]})

    runtime_snapshot = _runtime_snapshot(rt, mode=str(args.mode), meta_aid=meta_aid, graph_version=graph_version, file_fps=file_fps)
    run_fp = compute_run_fingerprint(plan_hash=plan_hash, runtime_snapshot=runtime_snapshot)

    id_map: Dict[str, str] = {}
    per_step: List[Dict[str, Any]] = []

    for s in steps:
        if not isinstance(s, dict):
            continue
        op = _safe_str(s.get("op"))
        key = _safe_str(s.get("key"))
        endpoint = _safe_str(s.get("endpoint"))
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

        sid = _simulate_id(key, plan_hash)
        id_map[key] = sid

        if unresolved:
            err(
                "unresolved_placeholders",
                f"Step {key} aún tiene placeholders sin resolver: {unresolved}",
                {"step_key": key, "unresolved": unresolved},
            )

        per_step.append(
            {
                "i": s.get("i"),
                "key": key,
                "op": op,
                "endpoint": endpoint,
                "endpoint_resolved": endpoint_resolved,
                "simulated_id": sid,
                "unresolved": unresolved,
            }
        )

    status = "OK" if not any(i["severity"] == "ERROR" for i in issues) else "FAIL"

    report = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": status,
        "mode": str(args.mode),
        "plan_path": str(plan_path),
        "plan_hash": plan_hash,
        "run_fingerprint": run_fp.fingerprint,
        "run_fingerprint_12": run_fp.fingerprint_12,
        "runtime_snapshot": runtime_snapshot,
        "counts": {
            "steps": len([s for s in steps if isinstance(s, dict)]),
            "issues": len(issues),
            "errors": len([i for i in issues if i["severity"] == "ERROR"]),
            "warns": len([i for i in issues if i["severity"] == "WARN"]),
        },
        "placeholder_scan": ph,
        "env_meta": {"META_AD_ACCOUNT_ID_present": bool(meta_aid)},
        "files": {"count": file_fps.get("count"), "missing": file_fps.get("missing"), "overall_sha12": file_fps.get("overall_sha12")},
        "issues": issues,
        "per_step": per_step[:50],
        "notes": {
            "offline_only": True,
            "no_secrets_printed": True,
            "goal": "Detectar pendejadas ANTES de meter tokens/APIs.",
        },
    }

    _write_json(out_path, report)

    cli_print(
        json.dumps(
            {
                "marker": __MARKER__,
                "ts": report["ts"],
                "status": report["status"],
                "mode": report["mode"],
                "out": str(out_path),
                "counts": report["counts"],
                "run_fingerprint_12": report["run_fingerprint_12"],
                "files": report["files"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if issues:
        cli_print("")
        cli_print("ISSUES:")
        for it in issues[:25]:
            cli_print(f"- {it['severity']}: {it['code']}  {it['msg']}")
    return 0 if status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())

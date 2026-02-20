from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
logger = logging.getLogger(__name__)

__MARKER__ = "META_PUBLISH_VALIDATE_2026-01-13_V1"

DEFAULT_PLAN = Path("data/run/meta_publish_plan.json")
DEFAULT_OUT_JSON = Path("data/run/meta_publish_validate.json")
DEFAULT_OUT_TXT = Path("data/run/meta_publish_validate.txt")

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


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _load_json_arg(s: str) -> Optional[Dict[str, Any]]:
    """
    Accept:
      - raw JSON string
      - @file.json
    """
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
    ad_account_id: Optional[str]  # digits only, optional
    access_token_present: bool  # env META_ACCESS_TOKEN exists?


def _resolve_runtime_placeholders(obj: Any, rt: RuntimeInputs) -> Any:
    """
    Resolve ONLY external/runtime placeholders (NOT <ID:...>).

    FIX: if we inject a dict (TARGETING/PROMOTED), recurse into it so nested
    placeholders like <META_PIXEL_ID> also get resolved.
    """
    if isinstance(obj, dict):
        return {k: _resolve_runtime_placeholders(v, rt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_runtime_placeholders(v, rt) for v in obj]
    if isinstance(obj, str):
        if obj == "<DAILY_BUDGET_MINOR_UNITS>":
            return rt.daily_budget_minor_units if rt.daily_budget_minor_units is not None else obj
        if obj == "<TARGETING_JSON>":
            if rt.targeting_json is None:
                return obj
            return _resolve_runtime_placeholders(rt.targeting_json, rt)
        if obj == "<PROMOTED_OBJECT_JSON>":
            if rt.promoted_object_json is None:
                return obj
            return _resolve_runtime_placeholders(rt.promoted_object_json, rt)
        if obj == "<META_PAGE_ID>":
            return rt.meta_page_id if rt.meta_page_id else obj
        if obj == "<META_IG_ACTOR_ID>":
            return rt.meta_ig_actor_id if rt.meta_ig_actor_id else obj
        if obj == "<META_PIXEL_ID>":
            return rt.meta_pixel_id if rt.meta_pixel_id else obj
        return obj
    return obj


def _collect_placeholders(obj: Any) -> List[str]:
    """
    Collect any remaining <...> strings.
    """
    found: List[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            if x.startswith("<") and x.endswith(">"):
                found.append(x)

    walk(obj)

    # dedupe preserving order
    seen = set()
    out = []
    for f in found:
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def _classify_placeholders(ph: List[str]) -> Dict[str, List[str]]:
    """
    Split placeholders into:
      - dynamic_ids: <ID:...>  (expected; resolved during execution)
      - file_refs:  <FILE:...>
      - external:   everything else (budget/targeting/page/pixel/etc.)
    """
    out = {"dynamic_ids": [], "file_refs": [], "external": []}
    for x in ph:
        if ID_REF_RE.match(x):
            out["dynamic_ids"].append(x)
        elif FILE_REF_RE.match(x):
            out["file_refs"].append(x)
        else:
            out["external"].append(x)
    return out


def _extract_files_from_payload(payload: Any) -> List[Path]:
    files: List[Path] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            m = FILE_REF_RE.match(x)
            if m:
                p = Path(m.group(1)).expanduser()
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                files.append(p)

    walk(payload)

    # dedupe
    seen = set()
    out = []
    for f in files:
        s = str(f)
        if s in seen:
            continue
        seen.add(s)
        out.append(f)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_publish_validate", description="Preflight validation for Meta publish plan.")
    ap.add_argument("--plan", default=str(DEFAULT_PLAN), help="Path to meta_publish_plan.json")
    ap.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="Output validation JSON")
    ap.add_argument("--out-txt", default=str(DEFAULT_OUT_TXT), help="Output validation TXT")
    ap.add_argument("--strict", action="store_true", help="Fail (exit 2) if any external placeholders or missing assets.")
    ap.add_argument("--require-assets", action="store_true", help="Treat missing video files as FAIL (even if not strict).")
    ap.add_argument("--require-env", action="store_true", help="Require META_ACCESS_TOKEN + META_AD_ACCOUNT_ID to be set.")

    # Runtime injects (same knobs as execute)
    ap.add_argument("--daily-budget", default="", help="DAILY_BUDGET_MINOR_UNITS (e.g. 500 = $5.00)")
    ap.add_argument("--targeting-json", default="", help="TARGETING_JSON as raw JSON or @file.json")
    ap.add_argument("--promoted-object-json", default="", help="PROMOTED_OBJECT_JSON as raw JSON or @file.json")
    ap.add_argument("--page-id", default="", help="META_PAGE_ID")
    ap.add_argument("--ig-actor-id", default="", help="META_IG_ACTOR_ID")
    ap.add_argument("--pixel-id", default="", help="META_PIXEL_ID")

    args = ap.parse_args(argv)

    plan_path = Path(args.plan).resolve()
    plan = _read_json(plan_path)
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("plan.steps must be a list")

    # Runtime inputs
    daily_budget = _safe_str(args.daily_budget, "")
    daily_budget_int: Optional[int] = None
    if daily_budget:
        daily_budget_int = int(daily_budget)

    targeting_obj = _load_json_arg(_safe_str(args.targeting_json, ""))
    promoted_obj = _load_json_arg(_safe_str(args.promoted_object_json, ""))

    access_token_present = bool(_safe_str(os.getenv("META_ACCESS_TOKEN"), ""))
    ad_account_id_env = _safe_str(os.getenv("META_AD_ACCOUNT_ID"), "")

    rt = RuntimeInputs(
        daily_budget_minor_units=daily_budget_int,
        targeting_json=targeting_obj,
        promoted_object_json=promoted_obj,
        meta_page_id=_safe_str(args.page_id, "") or None,
        meta_ig_actor_id=_safe_str(args.ig_actor_id, "") or None,
        meta_pixel_id=_safe_str(args.pixel_id, "") or None,
        ad_account_id=ad_account_id_env or None,
        access_token_present=access_token_present,
    )

    # Validate plan structure basics
    keys: List[str] = []
    for s in steps:
        if isinstance(s, dict):
            keys.append(_safe_str(s.get("key")))
    dup = [k for k in keys if k and keys.count(k) > 1]
    dup = list(dict.fromkeys(dup))  # unique preserve order

    issues: List[Dict[str, Any]] = []
    missing_assets: List[str] = []
    external_missing: Dict[str, List[str]] = {}  # step_key -> missing external placeholders
    file_missing: Dict[str, List[str]] = {}  # step_key -> missing files

    if dup:
        issues.append({"type": "PLAN_DUP_KEYS", "detail": dup})

    # per-step payload scan
    for s in steps:
        if not isinstance(s, dict):
            continue
        key = _safe_str(s.get("key"))
        op = _safe_str(s.get("op"))
        payload = s.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        # resolve runtime placeholders (NOT dynamic IDs)
        payload_rt = _resolve_runtime_placeholders(payload, rt)
        placeholders = _collect_placeholders(payload_rt)
        classified = _classify_placeholders(placeholders)

        # record external missing placeholders (budget/targeting/page/pixel/etc.)
        if classified["external"]:
            external_missing[key] = classified["external"]

        # assets check
        files = _extract_files_from_payload(payload_rt)
        missing_here: List[str] = []
        for fp in files:
            if not fp.exists():
                missing_here.append(str(fp))
            else:
                # tiny guard: empty file is basically useless for upload
                try:
                    if fp.stat().st_size <= 0:
                        missing_here.append(str(fp) + " (empty)")
                except (AttributeError) as e:
                    logger.debug("suppressed exception", exc_info=True)

        if missing_here:
            file_missing[key] = missing_here
            missing_assets.extend(missing_here)

        # basic op sanity
        if not op:
            issues.append({"type": "STEP_BAD", "step": key, "detail": "missing op"})
        if not _safe_str(s.get("endpoint")):
            issues.append({"type": "STEP_BAD", "step": key, "detail": "missing endpoint"})

    # Env checks (optional)
    if args.require_env:
        if not access_token_present:
            issues.append({"type": "ENV_MISSING", "detail": "META_ACCESS_TOKEN not set"})
        if not ad_account_id_env:
            issues.append({"type": "ENV_MISSING", "detail": "META_AD_ACCOUNT_ID not set"})

    # Determine status
    has_external = bool(external_missing)
    has_assets = bool(missing_assets)

    status = "OK"
    if issues:
        status = "FAIL"
    elif has_external or (has_assets and args.require_assets):
        status = "WARN"

    # Strict escalates WARN -> FAIL
    if args.strict and (has_external or has_assets):
        status = "FAIL"

    out = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": status,
        "plan_path": str(plan_path),
        "plan_marker": _safe_str(plan.get("marker")),
        "plan_hash": _safe_str(plan.get("plan_hash")),
        "counts": {
            "steps": len(steps),
            "issues": len(issues),
            "steps_missing_external": len(external_missing),
            "steps_missing_files": len(file_missing),
        },
        "env": {
            "META_ACCESS_TOKEN_present": access_token_present,
            "META_AD_ACCOUNT_ID_present": bool(ad_account_id_env),
        },
        "runtime_inputs_present": {
            "daily_budget": rt.daily_budget_minor_units is not None,
            "targeting_json": rt.targeting_json is not None,
            "promoted_object_json": rt.promoted_object_json is not None,
            "page_id": bool(rt.meta_page_id),
            "ig_actor_id": bool(rt.meta_ig_actor_id),
            "pixel_id": bool(rt.meta_pixel_id),
        },
        "issues": issues,
        "missing_external_placeholders": external_missing,
        "missing_files": file_missing,
        "notes": {
            "dynamic_id_placeholders_are_expected": True,
            "this_is_preflight_only": True,
        },
    }

    # Human TXT
    lines: List[str] = []
    lines.append("=== META PUBLISH VALIDATE (Preflight) ===")
    lines.append(f"ts: {out['ts']}")
    lines.append(f"status: {status}")
    lines.append(f"plan: {out['plan_path']}")
    lines.append(f"plan_hash: {out['plan_hash']}")
    lines.append("")
    lines.append("ENV:")
    lines.append(f"- META_ACCESS_TOKEN present: {out['env']['META_ACCESS_TOKEN_present']}")
    lines.append(f"- META_AD_ACCOUNT_ID present: {out['env']['META_AD_ACCOUNT_ID_present']}")
    lines.append("")
    lines.append("RUNTIME INPUTS PRESENT:")
    for k, v in out["runtime_inputs_present"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    if issues:
        lines.append("PLAN ISSUES:")
        for it in issues:
            lines.append(f"- {it.get('type')}: {it.get('detail') or it}")
        lines.append("")
    if external_missing:
        lines.append("MISSING EXTERNAL PLACEHOLDERS (fill before LIVE):")
        for k, v in external_missing.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    if file_missing:
        lines.append("MISSING FILES (videos):")
        for k, v in file_missing.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    _write_json(Path(args.out_json).resolve(), out)
    _write_text(Path(args.out_txt).resolve(), "\n".join(lines) + "\n")

    cli_print(
        json.dumps(
            {
                "marker": __MARKER__,
                "ts": out["ts"],
                "status": status,
                "out_json": str(Path(args.out_json).resolve()),
                "out_txt": str(Path(args.out_txt).resolve()),
                "counts": out["counts"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())

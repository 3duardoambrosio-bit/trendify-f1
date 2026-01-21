from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__MARKER__ = "META_PUBLISH_PLAN_2026-01-13_V1"
DEFAULT_TASKS = Path("data/run/publish_tasks_meta.json")
DEFAULT_OUT = Path("data/run/meta_publish_plan.json")
DEFAULT_CHECKLIST = Path("data/run/meta_publish_checklist.txt")


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


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def _normalize_act(ad_account_id: str) -> str:
    s = _safe_str(ad_account_id, "").replace("act_", "").strip()
    return f"act_{s}" if s else "act_<META_AD_ACCOUNT_ID>"


def _with_utm(url: str, utm_content: str) -> str:
    # ultra simple: solo agrega utm_content si no está
    u = _safe_str(url, "")
    if not u:
        u = "https://example.com"
    if "utm_content=" in u:
        return u
    joiner = "&" if "?" in u else "?"
    return f"{u}{joiner}utm_content={utm_content}"


def _dedupe(items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        k = _safe_str(it.get(key))
        if not k:
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def build_plan(
    tasks_obj: Dict[str, Any],
    graph_version: str,
    ad_account_id: str,
    default_status: str,
    objective: str,
    billing_event: str,
    optimization_goal: str,
    promoted_object: str,
) -> Dict[str, Any]:
    tasks = tasks_obj.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []

    # Extract unique campaigns (from tasks naming)
    campaigns: List[Dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        naming = t.get("naming", {}) if isinstance(t.get("naming"), dict) else {}
        campaigns.append({"campaign": _safe_str(naming.get("campaign"), "")})
    campaigns = _dedupe(campaigns, "campaign")

    act = _normalize_act(ad_account_id)
    gv = _safe_str(graph_version, "v22.0").lstrip("v")
    gv = f"v{gv}"

    # Plan steps (dry-run friendly): we only prepare payloads + dependencies
    steps: List[Dict[str, Any]] = []
    step_i = 0

    # Campaign create steps
    for c in campaigns:
        cname = c["campaign"]
        payload = {
            "name": cname,
            "status": default_status,
            "objective": objective,
            "special_ad_categories": [],
        }
        idk = _sha256_obj({"op": "create_campaign", "campaign": cname, "payload": payload})
        steps.append({
            "i": step_i,
            "op": "create_campaign",
            "key": f"meta:campaign:{cname}",
            "depends_on": [],
            "endpoint": f"/{act}/campaigns",
            "graph_version": gv,
            "payload": payload,
            "idempotency_key": idk,
            "placeholders": ["META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"] if "<META_AD_ACCOUNT_ID>" in act else ["META_ACCESS_TOKEN"],
        })
        step_i += 1

    # Adset + creative + ad per task
    for t in tasks:
        if not isinstance(t, dict):
            continue

        utm = _safe_str(t.get("utm_content"), "UNKNOWN")
        landing = _safe_str(t.get("landing_url"), "https://example.com")
        landing = _with_utm(landing, utm)

        naming = t.get("naming", {}) if isinstance(t.get("naming"), dict) else {}
        campaign_name = _safe_str(naming.get("campaign"), "")
        adset_name = _safe_str(naming.get("adset"), utm)
        ad_name = _safe_str(naming.get("ad"), f"{utm}_AD")

        copy = t.get("copy", {}) if isinstance(t.get("copy"), dict) else {}
        primary_text = _safe_str(copy.get("primary_text"), "")
        headline = _safe_str(copy.get("headline"), "")
        description = _safe_str(copy.get("description"), "")

        assets = t.get("assets", {}) if isinstance(t.get("assets"), dict) else {}
        video_path = _safe_str(assets.get("video_path"), f"assets/{utm}.mp4")

        # 1) Adset
        adset_payload = {
            "name": adset_name,
            "status": default_status,
            # budgets/targeting se definen al final; aquí dejamos placeholders
            "daily_budget": "<DAILY_BUDGET_MINOR_UNITS>",
            "billing_event": billing_event,
            "optimization_goal": optimization_goal,
            "campaign_id": f"<ID:meta:campaign:{campaign_name}>",
            "promoted_object": promoted_object if promoted_object else "<PROMOTED_OBJECT_JSON>",
            "targeting": "<TARGETING_JSON>",
        }
        adset_idk = _sha256_obj({"op": "create_adset", "campaign": campaign_name, "adset": adset_name, "utm": utm})
        steps.append({
            "i": step_i,
            "op": "create_adset",
            "key": f"meta:adset:{utm}",
            "depends_on": [f"meta:campaign:{campaign_name}"],
            "endpoint": f"/{act}/adsets",
            "graph_version": gv,
            "payload": adset_payload,
            "idempotency_key": adset_idk,
            "placeholders": ["DAILY_BUDGET_MINOR_UNITS", "TARGETING_JSON", "PROMOTED_OBJECT_JSON"],
        })
        step_i += 1

        # 2) Upload video (optional in automation; depends on your future flow)
        upload_payload = {
            "source": f"<FILE:{video_path}>",
            "name": utm,
        }
        upload_idk = _sha256_obj({"op": "upload_video", "utm": utm, "path": video_path})
        steps.append({
            "i": step_i,
            "op": "upload_video",
            "key": f"meta:video:{utm}",
            "depends_on": [],
            "endpoint": f"/{act}/advideos",
            "graph_version": gv,
            "payload": upload_payload,
            "idempotency_key": upload_idk,
            "placeholders": ["VIDEO_FILE_PRESENT"],
        })
        step_i += 1

        # 3) Create creative (requires page_id / ig_actor_id typically)
        creative_payload = {
            "name": f"{utm}_CREATIVE",
            "object_story_spec": {
                "page_id": "<META_PAGE_ID>",
                "instagram_actor_id": "<META_IG_ACTOR_ID>",
                "video_data": {
                    "video_id": f"<ID:meta:video:{utm}>",
                    "message": primary_text,
                    "title": headline,
                    "link_description": description,
                    "call_to_action": {
                        "type": "SHOP_NOW",
                        "value": {"link": landing}
                    }
                }
            }
        }
        creative_idk = _sha256_obj({"op": "create_creative", "utm": utm, "campaign": campaign_name})
        steps.append({
            "i": step_i,
            "op": "create_creative",
            "key": f"meta:creative:{utm}",
            "depends_on": [f"meta:video:{utm}"],
            "endpoint": f"/{act}/adcreatives",
            "graph_version": gv,
            "payload": creative_payload,
            "idempotency_key": creative_idk,
            "placeholders": ["META_PAGE_ID", "META_IG_ACTOR_ID"],
        })
        step_i += 1

        # 4) Create ad
        ad_payload = {
            "name": ad_name,
            "status": default_status,
            "adset_id": f"<ID:meta:adset:{utm}>",
            "creative": {"creative_id": f"<ID:meta:creative:{utm}>"},
            "tracking_specs": [{"action.type": ["offsite_conversion"], "fb_pixel": ["<META_PIXEL_ID>"]}],
        }
        ad_idk = _sha256_obj({"op": "create_ad", "utm": utm, "ad": ad_name})
        steps.append({
            "i": step_i,
            "op": "create_ad",
            "key": f"meta:ad:{utm}",
            "depends_on": [f"meta:adset:{utm}", f"meta:creative:{utm}"],
            "endpoint": f"/{act}/ads",
            "graph_version": gv,
            "payload": ad_payload,
            "idempotency_key": ad_idk,
            "placeholders": ["META_PIXEL_ID"],
        })
        step_i += 1

    plan = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "source_tasks_marker": _safe_str(tasks_obj.get("marker"), ""),
        "tasks_path": _safe_str(tasks_obj.get("tasks_path"), str(DEFAULT_TASKS)),
        "graph_version": gv,
        "ad_account": act,
        "default_status": default_status,
        "counts": {
            "tasks": len(tasks),
            "steps": len(steps),
        },
        "steps": steps,
        "plan_hash": _sha256_obj({"steps": steps}),
        "notes": {
            "this_is_a_plan_only": True,
            "no_api_calls_done": True,
            "placeholders_must_be_filled_before_execution": True,
        }
    }
    return plan


def _write_checklist(path: Path, plan: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("=== META PUBLISH CHECKLIST (Plan only) ===")
    lines.append(f"ts: {plan.get('ts')}")
    lines.append(f"graph_version: {plan.get('graph_version')}")
    lines.append(f"ad_account: {plan.get('ad_account')}")
    lines.append(f"steps: {plan.get('counts', {}).get('steps')}")
    lines.append("")
    lines.append("ANTES DE EJECUTAR (manual / futuro):")
    lines.append("- [ ] Tener META_ACCESS_TOKEN con permisos Ads")
    lines.append("- [ ] Tener META_AD_ACCOUNT_ID (sin act_)")
    lines.append("- [ ] Tener META_PAGE_ID + META_IG_ACTOR_ID")
    lines.append("- [ ] Tener META_PIXEL_ID (si vas a trackear conversiones)")
    lines.append("- [ ] Definir TARGETING_JSON (país/edad/intereses/etc.)")
    lines.append("- [ ] Definir DAILY_BUDGET_MINOR_UNITS (ej: 500 = $5.00 si moneda usa centavos)")
    lines.append("- [ ] Tener videos reales en assets/ (o adaptar subida)")
    lines.append("")
    lines.append("POLICY (evitar bans):")
    lines.append("- [ ] Sin claims médicos (curar/tratar/etc.)")
    lines.append("- [ ] Sin promesas garantizadas")
    lines.append("- [ ] Creativo 1 idea, bien ejecutada (no licuadora de features)")
    lines.append("")
    lines.append("STEP MAP (high level):")
    for s in plan.get("steps", [])[:50]:
        if isinstance(s, dict):
            lines.append(f"- {s.get('i')}: {s.get('op')}  key={s.get('key')}  depends={s.get('depends_on')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.meta_publish_plan", description="Build a Meta publish PLAN (no API calls).")
    ap.add_argument("--tasks", default=str(DEFAULT_TASKS), help="Path to publish_tasks_meta.json")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output plan JSON")
    ap.add_argument("--checklist", default=str(DEFAULT_CHECKLIST), help="Output checklist TXT")

    # Meta-ish knobs (plan only)
    ap.add_argument("--graph-version", default=os.getenv("META_GRAPH_VERSION", "v22.0"), help="Graph/Marketing API version (plan tag).")
    ap.add_argument("--ad-account-id", default=os.getenv("META_AD_ACCOUNT_ID", ""), help="Ad account id (digits).")
    ap.add_argument("--status", default="PAUSED", help="PAUSED|ACTIVE (keep PAUSED in Phase-1).")
    ap.add_argument("--objective", default="OUTCOME_SALES", help="Campaign objective (plan placeholder).")
    ap.add_argument("--billing-event", default="IMPRESSIONS", help="Adset billing_event.")
    ap.add_argument("--optimization-goal", default="OFFSITE_CONVERSIONS", help="Adset optimization_goal.")
    ap.add_argument("--promoted-object", default="", help="JSON string for promoted_object (optional).")

    args = ap.parse_args(argv)

    tasks_path = Path(args.tasks).resolve()
    out_path = Path(args.out).resolve()
    checklist_path = Path(args.checklist).resolve()

    tasks_obj = _read_json(tasks_path) or {}
    # attach for traceability
    tasks_obj["tasks_path"] = str(tasks_path)

    plan = build_plan(
        tasks_obj=tasks_obj,
        graph_version=str(args.graph_version),
        ad_account_id=str(args.ad_account_id),
        default_status=str(args.status),
        objective=str(args.objective),
        billing_event=str(args.billing_event),
        optimization_goal=str(args.optimization_goal),
        promoted_object=str(args.promoted_object),
    )

    _write_json(out_path, plan)
    _write_checklist(checklist_path, plan)

    print(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": "OK",
        "tasks": str(tasks_path),
        "out_plan": str(out_path),
        "out_checklist": str(checklist_path),
        "counts": plan.get("counts", {}),
        "plan_hash": plan.get("plan_hash"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
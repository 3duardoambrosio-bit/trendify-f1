from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


__MARKER__ = "CREATIVE_BUILDSHEET_2026-01-13_V1"

DEFAULT_BRIEFS = Path("data/run/creative_briefs.json")
DEFAULT_OUT = Path("exports/meta_buildsheet.csv")
DEFAULT_TASKS = Path("data/run/publish_tasks_meta.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        if not p.exists():
            return None
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _join(xs: Any, sep: str = " | ") -> str:
    if not isinstance(xs, list):
        return ""
    return sep.join(_safe_str(x) for x in xs if _safe_str(x))


def _build_primary_text(structure: List[Dict[str, Any]], offer: str) -> str:
    # compacta HOOK + PROBLEM + OFFER
    hook = ""
    prob = ""
    for b in structure or []:
        beat = _safe_str(b.get("beat", "")).upper()
        scr = _safe_str(b.get("script", ""))
        if beat == "HOOK" and not hook:
            hook = scr
        if beat == "PROBLEM" and not prob:
            prob = scr
    chunks = [c for c in [hook, prob, _safe_str(offer)] if c]
    return " ".join(chunks).strip()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.creative_buildsheet", description="Create Meta buildsheet CSV from creative briefs.")
    ap.add_argument("--briefs", default=str(DEFAULT_BRIEFS), help="Path to creative_briefs.json")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output CSV path")
    ap.add_argument("--platform", default="meta", help="meta|tiktok|google (tag only)")
    ap.add_argument("--landing-url", default="", help="Landing page URL (if blank, uses placeholder).")
    ap.add_argument("--offer", default="2x1 / envío gratis / -20%", help="Offer text (used in copy placeholders).")
    args = ap.parse_args(argv)

    briefs_path = Path(args.briefs).resolve()
    out_path = Path(args.out).resolve()

    obj = _read_json(briefs_path) or {}
    briefs = obj.get("briefs", [])
    if not isinstance(briefs, list):
        briefs = []

    landing = _safe_str(args.landing_url, "")
    if not landing:
        landing = "https://example.com"  # placeholder until Shopify/Domain is final

    rows: List[Dict[str, Any]] = []
    tasks: List[Dict[str, Any]] = []

    for b in briefs:
        if not isinstance(b, dict):
            continue

        utm = _safe_str(b.get("utm_content"), "UNKNOWN")
        angle = _safe_str(b.get("angle"), "unknown")
        fmt = _safe_str(b.get("format"), "unknown")
        hook = _safe_str(b.get("hook_id"), "unknown")
        bid = _safe_str(b.get("id"), "")

        script = b.get("script", {}) if isinstance(b.get("script"), dict) else {}
        on_screen = script.get("on_screen_text", [])
        shotlist = script.get("shotlist", [])
        structure = script.get("structure", [])

        primary_text = _build_primary_text(structure, args.offer)
        headline = "Rápido. Simple. Sin rollos."
        description = "Oferta limitada. Stock variable."

        # Naming conventions (simple + deterministic)
        campaign_name = f"P1_{angle}_{fmt}".replace(" ", "_")
        adset_name = f"{utm}"
        ad_name = f"{utm}_AD"

        video_asset_path = f"assets/{utm}.mp4"  # placeholder file path for later automation

        row = {
            "platform": _safe_str(args.platform, "meta"),
            "campaign_name": campaign_name,
            "adset_name": adset_name,
            "ad_name": ad_name,
            "utm_content": utm,
            "hook_id": hook,
            "angle": angle,
            "format": fmt,
            "landing_url": landing,
            "offer": _safe_str(args.offer),
            "primary_text": primary_text,
            "headline": headline,
            "description": description,
            "on_screen_text": _join(on_screen),
            "shotlist": _join(shotlist),
            "video_asset_path": video_asset_path,
            "policy_notes": "Sin claims médicos. Sin promesas garantizadas.",
            "brief_id": bid,
        }
        rows.append(row)

        tasks.append({
            "id": bid,
            "platform": row["platform"],
            "utm_content": utm,
            "naming": {"campaign": campaign_name, "adset": adset_name, "ad": ad_name},
            "landing_url": landing,
            "copy": {"primary_text": primary_text, "headline": headline, "description": description},
            "assets": {"video_path": video_asset_path},
            "notes": {"on_screen_text": on_screen, "shotlist": shotlist, "policy": row["policy_notes"]},
            "marker": __MARKER__,
            "ts": _utc_now_z(),
        })

    # write CSV (Excel-friendly: utf-8-sig)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "platform","campaign_name","adset_name","ad_name",
        "utm_content","hook_id","angle","format",
        "landing_url","offer",
        "primary_text","headline","description",
        "on_screen_text","shotlist","video_asset_path","policy_notes","brief_id"
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    # write tasks JSON for future API publisher
    tasks_path = DEFAULT_TASKS.resolve()
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "briefs_path": str(briefs_path),
        "out_csv": str(out_path),
        "count": len(tasks),
        "tasks": tasks,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": "OK",
        "briefs": str(briefs_path),
        "out_csv": str(out_path),
        "tasks_json": str(tasks_path),
        "count": len(rows),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
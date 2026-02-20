from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__ARI_MARKER__ = "AD_RESULTS_IMPORT_2026-01-13_V2_AUTO"

LEDGER_REL = Path("data/ledger/events.ndjson")
STATE_REL = Path("data/run/ad_results_import_state.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        s = str(x).strip()
        if not s:
            return 0.0
        s = s.replace(",", "")
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(x: Any) -> int:
    try:
        if x is None:
            return 0
        s = str(x).strip()
        if not s:
            return 0
        s = s.replace(",", "")
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    try:
        s = str(x).strip()
        return s if s else default
    except Exception:
        return default


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


def _append_ledger_event(path: Path, payload: Dict[str, Any], ts_utc: Optional[str] = None) -> None:
    """
    Ledger contract: NDJSON lines with { "ts_utc": "...Z", "payload": {...} }.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ev = {"ts_utc": ts_utc or _utc_now_z(), "payload": payload}
    line = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def _row_hash(payload: Dict[str, Any]) -> str:
    s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def _load_state(repo: Path) -> Dict[str, Any]:
    st = _read_json(repo / STATE_REL)
    if not st:
        return {"marker": __ARI_MARKER__, "ts": _utc_now_z(), "seen": {}}
    st.setdefault("seen", {})
    if not isinstance(st["seen"], dict):
        st["seen"] = {}
    return st


def _save_state(repo: Path, st: Dict[str, Any]) -> None:
    st["marker"] = __ARI_MARKER__
    st["ts"] = _utc_now_z()
    _write_json(repo / STATE_REL, st)


def _pick(row: Dict[str, str], keys: List[str]) -> str:
    for k in keys:
        if k in row and str(row[k]).strip():
            return str(row[k]).strip()
    return ""


def _normalize_ts_utc(x: str) -> str:
    s = (x or "").strip()
    if not s:
        return _utc_now_z()
    try:
        # common: 2026-01-12T22:20:00Z
        if s.endswith("Z"):
            # validate parse
            datetime.fromisoformat(s.replace("Z", "+00:00"))
            return s
        # allow "YYYY-MM-DD"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return s + "T00:00:00Z"
        # parse iso with offset or naive
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return _utc_now_z()


def _extract_utm_content(row: Dict[str, str]) -> str:
    # 1) direct columns
    utm = _pick(row, ["utm_content", "utm", "utmContent", "UTM_CONTENT"])
    if utm:
        return utm

    # 2) URL param utm_content=
    url = _pick(row, ["url", "URL", "landing_page", "Landing Page", "website_url", "Website URL"])
    if url:
        m = re.search(r"[?&]utm_content=([^&]+)", url)
        if m:
            return m.group(1).strip()

    # 3) ad name / creative name pattern like Hh9_Adolor_Fhands_V1
    name = _pick(row, ["ad_name", "Ad Name", "creative_name", "Creative Name", "campaign_name", "Campaign Name"])
    if name:
        m2 = re.search(r"(Hh\d+_[A-Za-z0-9]+_[A-Za-z0-9]+_V\d+)", name)
        if m2:
            return m2.group(1).strip()

    return ""


def _list_csvs(exports_dir: Path) -> List[Path]:
    if not exports_dir.exists():
        return []
    return sorted([p for p in exports_dir.rglob("*.csv") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)


def _pick_auto_csv(repo: Path, exports_dir: Path) -> Optional[Path]:
    cands = _list_csvs(exports_dir)
    if not cands:
        # fallback: search repo for csv in exports only
        cands = _list_csvs(repo / "exports")
    return cands[0] if cands else None


def import_csv(repo: Path, csv_path: Path, platform: str, product_id: str, allow_duplicates: bool, dry_run: bool) -> Dict[str, Any]:
    ts = _utc_now_z()
    ledger_path = repo / LEDGER_REL

    if not csv_path.exists():
        return {"marker": __ARI_MARKER__, "ts": ts, "status": "NO_CSV", "csv": str(csv_path)}

    st = _load_state(repo)
    seen = st.get("seen", {})

    parsed = 0
    inserted = 0
    skipped = 0
    written = 0
    errors: List[str] = []

    readonly = os.getenv("SYNAPSE_READONLY", "").strip() in ("1", "true", "TRUE", "yes", "YES")
    if dry_run:
        readonly = True  # force no writes

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not isinstance(row, dict):
                continue
            parsed += 1

            utm_content = _extract_utm_content(row)

            spend = _safe_float(_pick(row, ["spend", "cost", "amount_spent", "Amount Spent"]))
            impressions = _safe_int(_pick(row, ["impressions", "Impressions"]))
            clicks = _safe_int(_pick(row, ["clicks", "Clicks", "link_clicks", "Link Clicks"]))
            conversions = _safe_int(_pick(row, ["conversions", "purchases", "Purchases", "results", "Results"]))
            roas = _safe_float(_pick(row, ["roas", "purchase_roas", "ROAS"]))
            hook_rate_3s = _safe_float(_pick(row, ["hook_rate_3s", "hookRate3s", "3s_view_rate", "3s View Rate"]))
            creative_id = _pick(row, ["creative_id", "ad_id", "Ad ID", "Creative ID", "adset_id", "Adset ID"])

            row_ts = _pick(row, ["ts", "timestamp", "date_start", "date", "Date"])
            ts_utc = _normalize_ts_utc(row_ts)

            payload: Dict[str, Any] = {
                "event_type": "AD_RESULTS",
                "platform": _safe_str(platform, "unknown").lower(),
                "product_id": _safe_str(product_id, "") or "unknown",
                "utm_content": utm_content or "unknown",
                "creative_id": creative_id or "unknown",
                "spend": float(spend),
                "impressions": int(impressions),
                "clicks": int(clicks),
                "conversions": int(conversions),
                "roas": float(roas),
                "hook_rate_3s": float(hook_rate_3s),
                "marker": __ARI_MARKER__,
            }

            h = _row_hash(payload)
            if (not allow_duplicates) and (h in seen):
                skipped += 1
                continue

            inserted += 1
            if not readonly:
                _append_ledger_event(ledger_path, payload=payload, ts_utc=ts_utc)
                seen[h] = {"ts": _utc_now_z(), "csv": str(csv_path.name)}
                written += 1

    st["seen"] = seen
    if not readonly:
        _save_state(repo, st)

    return {
        "marker": __ARI_MARKER__,
        "ts": ts,
        "status": "OK",
        "repo": str(repo),
        "csv": str(csv_path),
        "platform": _safe_str(platform, "unknown").lower(),
        "product_id": _safe_str(product_id, "") or "unknown",
        "ledger_path": str(ledger_path),
        "state_path": str(repo / STATE_REL),
        "parsed_rows": parsed,
        "inserted": inserted,
        "written": written,
        "skipped_duplicates": skipped,
        "readonly": bool(readonly),
        "dry_run": bool(dry_run),
        "errors": errors,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.ad_results_import", description="Import ad results CSV into ledger as evidence events.")
    ap.add_argument("--csv", default="auto", help="Path to CSV export, or 'auto' to pick newest in ./exports.")
    ap.add_argument("--exports-dir", default="exports", help="Directory to scan when --csv auto.")
    ap.add_argument("--list", action="store_true", help="List CSVs found in exports-dir and exit.")
    ap.add_argument("--platform", default="meta", help="meta|tiktok|google (evidence key).")
    ap.add_argument("--product-id", default="34357", help="Product id tag (evidence key).")
    ap.add_argument("--allow-duplicates", action="store_true", help="Do not dedupe by payload hash.")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; do not write ledger/state.")
    args = ap.parse_args(argv)

    repo = Path.cwd()
    exports_dir = (repo / args.exports_dir).resolve()

    if args.list:
        cands = _list_csvs(exports_dir)
        out = {
            "marker": __ARI_MARKER__,
            "ts": _utc_now_z(),
            "status": "OK",
            "exports_dir": str(exports_dir),
            "count": len(cands),
            "items": [str(p) for p in cands[:25]],
        }
        cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0

    if str(args.csv).strip().lower() == "auto":
        picked = _pick_auto_csv(repo, exports_dir)
        if not picked:
            out = {"marker": __ARI_MARKER__, "ts": _utc_now_z(), "status": "NO_CSV_FOUND", "exports_dir": str(exports_dir)}
            cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
            return 2
        csv_path = picked
    else:
        csv_path = Path(args.csv).expanduser().resolve()

    out = import_csv(
        repo=repo,
        csv_path=csv_path,
        platform=str(args.platform),
        product_id=str(args.product_id),
        allow_duplicates=bool(args.allow_duplicates),
        dry_run=bool(args.dry_run),
    )
    cli_print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if out.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
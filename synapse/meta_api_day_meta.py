from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__MARKER__ = "META_API_DAY_2026-01-19_V2"

SECRET_FILES = {
    "META_ACCESS_TOKEN": "meta_access_token.txt",
    "META_AD_ACCOUNT_ID": "meta_ad_account_id.txt",
    "META_PAGE_ID": "meta_page_id.txt",
    "META_IG_ACTOR_ID": "meta_ig_actor_id.txt",
}

def _read_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}

def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default

def _append_kv(argv: List[str], flag: str, value: str) -> None:
    v = _safe_str(value, "")
    if v:
        argv.extend([flag, v])

def _load_secrets_from_dir(secrets_dir: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, fname in SECRET_FILES.items():
        p = (secrets_dir / fname).resolve()
        if p.exists() and p.is_file():
            raw = p.read_text(encoding="utf-8", errors="ignore")
            out[k] = (raw or "").strip()
        else:
            out[k] = ""
    # normaliza ad account: acepta act_123 o 123
    aid = out.get("META_AD_ACCOUNT_ID", "")
    if aid.startswith("act_"):
        aid = aid.replace("act_", "", 1).strip()
    out["META_AD_ACCOUNT_ID"] = aid
    return out

def _token_sanity(token: str) -> Tuple[bool, Dict[str, Any]]:
    t = (token or "").strip()
    meta = {
        "len": len(t),
        "has_whitespace": bool(__import__("re").search(r"\s", t)),
        "prefix": t[:4] if len(t) >= 4 else t,
    }
    if not t:
        return False, {"reason": "empty", **meta}
    if meta["has_whitespace"]:
        return False, {"reason": "whitespace_in_token", **meta}
    # heurística suave (no bloquea): normalmente tokens empiezan con "EA"
    meta["looks_like_meta"] = t.startswith("EA")
    return True, {"reason": "ok", **meta}

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="synapse.meta_api_day_meta",
        description="One-command Meta API Day runner: gate -> preflight -> execute -> fingerprint match.",
    )

    ap.add_argument("--mode", default="live", choices=["simulate", "live"], help="simulate|live")
    ap.add_argument("--plan", default="data/run/meta_publish_plan.json", help="Path to meta_publish_plan.json")

    ap.add_argument("--status", default="", help="Override status for created objects (PAUSED/ACTIVE)")
    ap.add_argument("--daily-budget", default="", help="DAILY_BUDGET_MINOR_UNITS (e.g. 500 = $5.00)")
    ap.add_argument("--targeting-json", default="", help="TARGETING_JSON as raw JSON or @file.json")
    ap.add_argument("--promoted-object-json", default="", help="PROMOTED_OBJECT_JSON as raw JSON or @file.json")
    ap.add_argument("--page-id", default="", help="META_PAGE_ID (optional override)")
    ap.add_argument("--ig-actor-id", default="", help="META_IG_ACTOR_ID (optional override)")
    ap.add_argument("--pixel-id", default="", help="META_PIXEL_ID")

    ap.add_argument("--out-preflight", default="data/run/meta_publish_preflight.json", help="Preflight output JSON")
    ap.add_argument("--out-run", default="data/run/meta_publish_run.json", help="Execute output JSON")

    ap.add_argument("--continue-on-error", action="store_true", help="Continue steps even after an error (live).")
    ap.add_argument("--ledger-dir", default="data/ledger", help="Ledger directory (default data/ledger)")
    ap.add_argument("--ledger-disable", action="store_true", help="DANGEROUS: disable idempotency ledger in LIVE")

    # NEW: secrets loading (future-proof)
    ap.add_argument("--secrets-dir", default="secrets", help="Directory containing secret txt files (default ./secrets)")
    ap.add_argument("--load-secrets", action="store_true", help="Load META_* secrets from secrets-dir into process env (safe, no printing).")
    ap.add_argument("--print-secrets-sanity", action="store_true", help="Print safe sanity (length/prefix only).")

    args = ap.parse_args(argv)
    mode = _safe_str(args.mode, "live").lower()

    # optionally load secrets into this process (so live_gate + execute see them)
    if args.load_secrets:
        sdir = Path(args.secrets_dir).resolve()
        secrets = _load_secrets_from_dir(sdir)
        # allow CLI overrides for page/ig
        if _safe_str(args.page_id):
            secrets["META_PAGE_ID"] = _safe_str(args.page_id)
        if _safe_str(args.ig_actor_id):
            secrets["META_IG_ACTOR_ID"] = _safe_str(args.ig_actor_id)

        for k, v in secrets.items():
            if v:
                os.environ[k] = v

        ok_tok, tok_meta = _token_sanity(secrets.get("META_ACCESS_TOKEN", ""))
        if args.print_secrets_sanity:
            print(json.dumps({
                "marker": __MARKER__,
                "stage": "secrets_sanity",
                "secrets_dir": str(sdir),
                "META_ACCESS_TOKEN": tok_meta,   # len/prefix only
                "META_AD_ACCOUNT_ID_present": bool(secrets.get("META_AD_ACCOUNT_ID")),
                "META_PAGE_ID_present": bool(secrets.get("META_PAGE_ID")),
                "META_IG_ACTOR_ID_present": bool(secrets.get("META_IG_ACTOR_ID")),
                "no_secrets_printed": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))

        if mode == "live" and not ok_tok:
            # no token = no live. this is a feature.
            print(json.dumps({
                "marker": __MARKER__,
                "stage": "secrets_sanity",
                "status": "FAIL",
                "reason": "token_invalid_or_empty",
                "token_meta": tok_meta,
                "no_secrets_printed": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 2

    # Build argv for underlying modules WITHOUT empty flags
    base_rt: List[str] = ["--plan", str(args.plan)]
    _append_kv(base_rt, "--status", _safe_str(args.status))
    _append_kv(base_rt, "--daily-budget", _safe_str(args.daily_budget))
    _append_kv(base_rt, "--targeting-json", _safe_str(args.targeting_json))
    _append_kv(base_rt, "--promoted-object-json", _safe_str(args.promoted_object_json))
    _append_kv(base_rt, "--page-id", _safe_str(args.page_id))
    _append_kv(base_rt, "--ig-actor-id", _safe_str(args.ig_actor_id))
    _append_kv(base_rt, "--pixel-id", _safe_str(args.pixel_id))

    # 1) LIVE gate (only in live)
    if mode == "live":
        from synapse.infra.live_gate import check_meta_live_gate

        gate = check_meta_live_gate()
        print(json.dumps({
            "marker": __MARKER__,
            "stage": "live_gate",
            "status": gate.status,
            "ok": bool(gate.ok),
            "reason": gate.reason,
            "meta": gate.meta,
        }, ensure_ascii=False, indent=2, sort_keys=True))

        if not gate.ok:
            return 0 if gate.status == "SKIP" else 2

    # 2) Preflight
    from synapse.meta_publish_preflight import main as preflight_main
    preflight_argv = ["--mode", mode, "--out", str(args.out_preflight)] + base_rt
    rc_pre = int(preflight_main(preflight_argv))

    if rc_pre != 0:
        print(json.dumps({
            "marker": __MARKER__,
            "stage": "preflight",
            "status": "FAIL",
            "rc": rc_pre,
            "out_preflight": str(Path(args.out_preflight).resolve()),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    # 3) Execute
    from synapse.meta_publish_execute import main as execute_main
    exec_argv = ["--mode", mode, "--out", str(args.out_run), "--ledger-dir", str(args.ledger_dir)] + base_rt
    if args.continue_on_error:
        exec_argv.append("--continue-on-error")
    if args.ledger_disable:
        exec_argv.append("--ledger-disable")

    rc_ex = int(execute_main(exec_argv))

    # 4) Final contract: fingerprint match
    pre = _read_json(Path(args.out_preflight))
    run = _read_json(Path(args.out_run))

    fp_pre = _safe_str(pre.get("run_fingerprint_12"))
    fp_run = _safe_str(run.get("run_fingerprint_12"))

    ok_fp = (fp_pre and fp_run and fp_pre == fp_run)

    print(json.dumps({
        "marker": __MARKER__,
        "stage": "final_check",
        "mode": mode,
        "rc_execute": rc_ex,
        "fingerprint_match": bool(ok_fp),
        "preflight_fp12": fp_pre,
        "execute_fp12": fp_run,
        "out_preflight": str(Path(args.out_preflight).resolve()),
        "out_run": str(Path(args.out_run).resolve()),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    if not ok_fp:
        return 2

    return 0 if rc_ex == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())

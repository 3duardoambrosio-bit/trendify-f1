from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__MARKER__ = "META_API_DAY_2026-01-19_V2"
LEGACY_META_LIVE_PERMANENTLY_DISABLED = "LEGACY_META_LIVE_PERMANENTLY_DISABLED"

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


def _offline_contract() -> Dict[str, bool]:
    return {
        "offline_only": True,
        "external_write": False,
        "legacy_live_disabled": True,
    }


def _legacy_live_disabled() -> int:
    cli_print(json.dumps({
        "marker": __MARKER__,
        "mode": "live",
        "status": "FAIL",
        "diagnostic": LEGACY_META_LIVE_PERMANENTLY_DISABLED,
        **_offline_contract(),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 2


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

def _secret_status(secrets: Dict[str, str]) -> Dict[str, Any]:
    return {
        "secret_loaded": any(bool(value) for value in secrets.values()),
        "secret_source": "local_secret_files",
    }

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="synapse.meta_api_day_meta",
        description="Local-only Meta API Day runner: preflight -> simulate -> fingerprint match.",
    )

    ap.add_argument("--mode", default="simulate", choices=["simulate", "live"], help="simulate|live (live is disabled)")
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

    ap.add_argument("--continue-on-error", action="store_true", help="Legacy compatibility flag; live remains disabled.")
    ap.add_argument("--ledger-dir", default="data/ledger", help="Ledger directory (default data/ledger)")
    ap.add_argument("--ledger-disable", action="store_true", help="Legacy compatibility flag; live remains disabled.")

    # Local compatibility only. The live guard returns before this block.
    ap.add_argument("--secrets-dir", default="secrets", help="Directory containing secret txt files (default ./secrets)")
    ap.add_argument(
        "--load-secrets",
        action="store_true",
        help="Inspect local META_* availability only; values are never exported or delegated.",
    )
    ap.add_argument("--print-secrets-sanity", action="store_true", help="Print presence/source metadata only; never secret-derived values.")

    args = ap.parse_args(argv)
    mode = _safe_str(args.mode, "simulate").lower()
    if mode == "live":
        return _legacy_live_disabled()

    # Optional availability check only; live has already failed closed.
    if args.load_secrets:
        sdir = Path(args.secrets_dir).resolve()
        secrets = _load_secrets_from_dir(sdir)

        if args.print_secrets_sanity:
            cli_print(json.dumps({
                "marker": __MARKER__,
                "stage": "secrets_sanity",
                **_secret_status(secrets),
                "no_secrets_printed": True,
                **_offline_contract(),
            }, ensure_ascii=False, indent=2, sort_keys=True))

    # Build argv for underlying modules WITHOUT empty flags
    base_rt: List[str] = ["--plan", str(args.plan)]
    _append_kv(base_rt, "--status", _safe_str(args.status))
    _append_kv(base_rt, "--daily-budget", _safe_str(args.daily_budget))
    _append_kv(base_rt, "--targeting-json", _safe_str(args.targeting_json))
    _append_kv(base_rt, "--promoted-object-json", _safe_str(args.promoted_object_json))
    _append_kv(base_rt, "--page-id", _safe_str(args.page_id))
    _append_kv(base_rt, "--ig-actor-id", _safe_str(args.ig_actor_id))
    _append_kv(base_rt, "--pixel-id", _safe_str(args.pixel_id))

    # 1) Preflight
    from synapse.meta_publish_preflight import main as preflight_main
    preflight_argv = ["--mode", mode, "--out", str(args.out_preflight)] + base_rt
    rc_pre = int(preflight_main(preflight_argv))

    if rc_pre != 0:
        cli_print(json.dumps({
            "marker": __MARKER__,
            "stage": "preflight",
            "status": "FAIL",
            "rc": rc_pre,
            "out_preflight": str(Path(args.out_preflight).resolve()),
            **_offline_contract(),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    # 2) Execute
    from synapse.meta_publish_execute import main as execute_main
    exec_argv = ["--mode", mode, "--out", str(args.out_run), "--ledger-dir", str(args.ledger_dir)] + base_rt
    if args.continue_on_error:
        exec_argv.append("--continue-on-error")
    if args.ledger_disable:
        exec_argv.append("--ledger-disable")

    rc_ex = int(execute_main(exec_argv))

    # 3) Final contract: fingerprint match
    pre = _read_json(Path(args.out_preflight))
    run = _read_json(Path(args.out_run))

    fp_pre = _safe_str(pre.get("run_fingerprint_12"))
    fp_run = _safe_str(run.get("run_fingerprint_12"))

    ok_fp = (fp_pre and fp_run and fp_pre == fp_run)

    cli_print(json.dumps({
        "marker": __MARKER__,
        "stage": "final_check",
        "mode": mode,
        "rc_execute": rc_ex,
        "fingerprint_match": bool(ok_fp),
        "preflight_fp12": fp_pre,
        "execute_fp12": fp_run,
        "out_preflight": str(Path(args.out_preflight).resolve()),
        "out_run": str(Path(args.out_run).resolve()),
        **_offline_contract(),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    if not ok_fp:
        return 2

    return 0 if rc_ex == 0 else 2

if __name__ == "__main__":
    raise SystemExit(main())

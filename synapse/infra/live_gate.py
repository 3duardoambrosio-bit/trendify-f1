from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict


__MARKER__ = "LIVE_GATE_2026-01-15_V2"


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _try_parse_json(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    if not t:
        return {}
    # secrets_doctor imprime JSON indentado multilinea => json.loads funciona directo
    if t.startswith("{") and t.endswith("}"):
        try:
            obj = json.loads(t)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _run_py(args: list[str]) -> Dict[str, Any]:
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    return {
        "returncode": p.returncode,
        "stdout": out,
        "stderr": err,
        "json": _try_parse_json(out),
    }


@dataclass(frozen=True)
class GateResult:
    ok: bool
    status: str   # OK | SKIP | FAIL
    reason: str
    meta: Dict[str, Any]


def check_meta_live_gate() -> GateResult:
    # 1) Secrets contract
    sd = _run_py(["-m", "synapse.infra.secrets_doctor", "--scope", "meta"])
    sdj = sd.get("json") or {}
    sd_ok = (sdj.get("status") == "OK")

    # 2) Auth check (si no hay token => SKIP)
    ac = _run_py(["-m", "synapse.meta_auth_check"])
    acj = ac.get("json") or {}
    ac_status = (acj.get("status") or "").upper()

    ac_ok = (ac_status == "OK")

    if not sd_ok:
        return GateResult(
            ok=False,
            status="SKIP",
            reason="meta_secrets_missing (expected before API Day)",
            meta={"secrets_doctor": sdj, "auth_check": acj},
        )

    if not ac_ok:
        why = "meta_auth_missing" if ac_status == "SKIP" else "meta_auth_invalid"
        return GateResult(
            ok=False,
            status="FAIL" if ac_status == "FAIL" else "SKIP",
            reason=why,
            meta={"secrets_doctor": sdj, "auth_check": acj},
        )

    return GateResult(
        ok=True,
        status="OK",
        reason="live_gate_passed",
        meta={"secrets_doctor": sdj, "auth_check": acj},
    )


def main() -> int:
    r = check_meta_live_gate()
    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": r.status,
        "ok": r.ok,
        "reason": r.reason,
        "meta": r.meta,
    }, ensure_ascii=False, indent=2))
    return 0 if r.status in {"OK", "SKIP"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
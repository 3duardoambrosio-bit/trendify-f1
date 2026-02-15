"""Healthcheck JSON (parseable). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Dict


def run_checks() -> Dict[str, Any]:
    """Run all health checks and return structured dict."""
    out: Dict[str, Any] = {"ok": True, "checks": {}}
    out["checks"]["cwd"] = str(Path(".").resolve())

    try:
        from synapse.infra.feature_flags import FeatureFlags
        flags = FeatureFlags.load()
        out["checks"]["flags_loaded"] = True
        out["checks"]["flags_count"] = len(flags.values)
    except Exception as e:
        out["ok"] = False
        out["checks"]["flags_loaded"] = False
        out["checks"]["flags_error"] = str(e)

    try:
        import synapse.infra.doctor as _doctor  # noqa: F401
        out["checks"]["doctor_import"] = True
    except Exception as e:
        out["checks"]["doctor_import"] = False
        out["checks"]["doctor_error"] = str(e)

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    out = run_checks()

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print("HEALTHCHECK_OK=" + ("1" if out["ok"] else "0"))
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0 if out["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())

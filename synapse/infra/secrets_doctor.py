from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from synapse.infra.secrets_contract import contract


__MARKER__ = "SECRETS_DOCTOR_2026-01-15_V1"
DEFAULT_OUT_JSON = Path("data/run/secrets_doctor.json")
DEFAULT_OUT_TXT = Path("data/run/secrets_doctor.txt")
DEFAULT_TEMPLATE = Path("exports/secrets_template.env")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _mask_value(v: str) -> Dict[str, Any]:
    """
    Nunca imprime el secreto completo.
    Devuelve metadatos y un "preview" inocuo.
    """
    v = v or ""
    ln = len(v)
    head = v[:4]
    tail = v[-4:] if ln >= 4 else v
    sha = hashlib.sha256(v.encode("utf-8")).hexdigest()[:12]
    return {
        "present": bool(v),
        "len": ln,
        "preview": f"{head}…{tail}" if ln > 8 else ("…" if ln else ""),
        "sha12": sha if ln else "",
    }


def _read_env(key: str) -> str:
    return _safe_str(os.environ.get(key, ""), "")


def build_report(scope: str, include_optional: bool) -> Dict[str, Any]:
    specs = contract()
    if scope == "all":
        scopes = list(specs.keys())
    else:
        if scope not in specs:
            raise ValueError(f"Unknown scope: {scope}. Valid: {list(specs.keys())} or all")
        scopes = [scope]

    missing_required: List[str] = []
    missing_optional: List[str] = []
    present: Dict[str, Dict[str, Any]] = {}

    for sc in scopes:
        c = specs[sc]
        for s in c.required:
            v = _read_env(s.key)
            present[s.key] = _mask_value(v)
            if not v:
                missing_required.append(s.key)
        if include_optional:
            for s in c.optional:
                v = _read_env(s.key)
                present[s.key] = _mask_value(v)
                if not v:
                    missing_optional.append(s.key)

    # Dedup while preserving order
    def dedupe(xs: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    missing_required = dedupe(missing_required)
    missing_optional = dedupe(missing_optional)

    status = "OK" if len(missing_required) == 0 else "FAIL"

    return {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "scope": scope,
        "include_optional": bool(include_optional),
        "status": status,
        "counts": {
            "present_keys": len([k for k, v in present.items() if v.get("present")]),
            "missing_required": len(missing_required),
            "missing_optional": len(missing_optional),
        },
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "present_meta": present,  # masked only
        "notes": {
            "never_print_full_secrets": True,
            "tip": "Usa variables de entorno User/Machine o .env.local (gitignored).",
        },
    }


def write_template(path: Path) -> None:
    specs = contract()
    lines: List[str] = []
    lines.append("# secrets_template.env  (SAFE TO COMMIT)")
    lines.append("# Rellena tus secretos en .env.local (NO se commitea) o en env vars del sistema.")
    lines.append("")
    for sc, c in specs.items():
        lines.append(f"# --- {sc.upper()} ---")
        for s in c.required:
            lines.append(f"{s.key}=")
        for s in c.optional:
            lines.append(f"{s.key}=")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.infra.secrets_doctor", description="Validate secrets contract (masked output).")
    ap.add_argument("--scope", default="all", help="meta|shopify|google|all")
    ap.add_argument("--include-optional", action="store_true", help="Also check optional vars")
    ap.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="Output JSON path")
    ap.add_argument("--out-txt", default=str(DEFAULT_OUT_TXT), help="Output TXT path")
    ap.add_argument("--template", default="", help="Write template env file to path (e.g. exports/secrets_template.env)")
    args = ap.parse_args(argv)

    if args.template:
        write_template(Path(args.template).resolve())
        print(json.dumps({"marker": __MARKER__, "status": "OK", "wrote_template": str(Path(args.template).resolve())}, ensure_ascii=False, indent=2))
        return 0

    report = build_report(scope=str(args.scope), include_optional=bool(args.include_optional))

    out_json = Path(args.out_json).resolve()
    out_txt = Path(args.out_txt).resolve()

    _write_json(out_json, report)

    # Human TXT
    lines: List[str] = []
    lines.append("=== SECRETS DOCTOR ===")
    lines.append(f"ts: {report.get('ts')}")
    lines.append(f"scope: {report.get('scope')}")
    lines.append(f"status: {report.get('status')}")
    lines.append("")
    lines.append(f"missing_required ({len(report.get('missing_required', []))}):")
    for k in report.get("missing_required", []):
        lines.append(f"- {k}")
    lines.append("")
    lines.append(f"missing_optional ({len(report.get('missing_optional', []))}):")
    for k in report.get("missing_optional", []):
        lines.append(f"- {k}")
    lines.append("")
    lines.append("present_meta (masked):")
    pm = report.get("present_meta", {}) or {}
    for k in sorted(pm.keys()):
        meta = pm[k]
        if meta.get("present"):
            lines.append(f"- {k}: len={meta.get('len')} preview={meta.get('preview')} sha12={meta.get('sha12')}")
        else:
            lines.append(f"- {k}: <missing>")
    _write_text(out_txt, "\n".join(lines) + "\n")

    print(json.dumps({
        "marker": __MARKER__,
        "ts": report.get("ts"),
        "status": report.get("status"),
        "scope": report.get("scope"),
        "out_json": str(out_json),
        "out_txt": str(out_txt),
        "counts": report.get("counts", {}),
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if report.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
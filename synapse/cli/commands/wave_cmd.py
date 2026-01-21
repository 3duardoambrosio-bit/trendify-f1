from __future__ import annotations

import argparse
from pathlib import Path

from synapse.cli.commands._invoke import invoke_module
from synapse.infra.dry_run import resolve_dry_run


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("wave", help="Run marketing wave (default DRY-RUN).")
    p.add_argument("--product-id", default=None, help="Target product_id for the wave runner.")
    p.add_argument("--out-root", default=None, help="Override output root (for tests/sandboxes).")
    p.add_argument("--canonical-csv", default=None, help="Override canonical CSV path.")
    mx = p.add_mutually_exclusive_group(required=False)
    mx.add_argument("--apply", action="store_true", help="Execute (turn off dry-run).")
    mx.add_argument("--dry-run", action="store_true", help="Force dry-run (no side effects).")
    p.set_defaults(_fn=_run)


def _print_wave_ok(pid: str, out_root: str | None) -> None:
    root = Path(out_root) if out_root else Path("data/marketing/waves")
    kit = root / pid
    print(f"wave: OK — kit_dir={kit}", flush=True)

    manifest = kit / "manifest.json"
    if manifest.exists():
        try:
            from synapse.marketing_os.wave_kit_manifest import read_manifest  # lazy import

            m = read_manifest(manifest)
            arts = m.get("artifacts") or []
            if arts:
                print("wave: artifacts:", flush=True)
                for a in arts:
                    rp = a.get("relpath")
                    sh = a.get("sha256")
                    print(f"  - {rp}  sha256={sh}", flush=True)
            meta = m.get("meta") or {}
            mode = meta.get("catalog_mode")
            if mode:
                print(f"wave: catalog_mode={mode}", flush=True)
        except Exception:
            # keep DX robust; summary is best-effort
            return


def _run(args: argparse.Namespace) -> int:
    pid = getattr(args, "product_id", None)
    decision = resolve_dry_run(
        apply=bool(getattr(args, "apply", False)),
        dry_run_flag=bool(getattr(args, "dry_run", False)),
        default_dry_run=True,
    )

    if not decision.dry_run and not pid:
        print("wave: ERROR — --product-id is required when using --apply", flush=True)
        return 2

    if decision.dry_run:
        print(f"wave: DRY-RUN — would run wave for product_id={pid or '<none>'}. Use --apply to execute.", flush=True)
        return 0

    kw = {"product_id": str(pid), "dry_run": False}
    if getattr(args, "out_root", None):
        kw["out_root"] = str(args.out_root)
    if getattr(args, "canonical_csv", None):
        kw["canonical_csv"] = str(args.canonical_csv)

    try:
        rc = invoke_module("synapse.marketing_os.wave_kit_runner", argv=[], **kw)
        if rc == 0:
            _print_wave_ok(str(pid), getattr(args, "out_root", None))
        return rc
    except FileNotFoundError as e:
        print(f"wave: ERROR — {e}", flush=True)
        return 2
    except Exception as e:
        # Let CLI crash-guard handle it (crash report)
        raise

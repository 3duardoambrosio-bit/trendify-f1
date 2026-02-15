"""CLI cockpit minimal (health). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import argparse
import json
import subprocess
import sys

def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse-cli-cockpit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_health = sub.add_parser("health")
    p_health.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "health":
        res = _run([sys.executable, "-m", "synapse.infra.healthcheck", "--json"])
        out = {"ok": res["returncode"] == 0, "healthcheck": res}
        print(json.dumps(out, ensure_ascii=False) if args.json else json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] else 2

    return 2

if __name__ == "__main__":
    raise SystemExit(main())

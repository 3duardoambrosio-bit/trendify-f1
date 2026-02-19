from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as tools/*.py from any CWD
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synapse.forecast.model import (
    load_report,
    extend_plateau,
    first_profitable_month,
    first_cum_net_ge_0_month,
)


def _abs_from_root(p: Path) -> Path:
    return p if p.is_absolute() else (ROOT / p).resolve()


def _die(code: int, msg: str) -> int:
    print("PLAN_OK=0")
    print(f"ERROR={msg}")
    return code


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Emit month-by-month plan from v13.2 forecast JSON using synapse.forecast core."
    )
    ap.add_argument("--injson", default="./out/forecast/synapse_report_v13_2.json")
    ap.add_argument("--label", required=True)
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    injson = _abs_from_root(Path(args.injson))
    if not injson.exists():
        return _die(2, f"INJSON_NOT_FOUND path={injson}")

    if args.months < 1:
        return _die(2, f"MONTHS_LT_1 months={args.months}")

    rep = load_report(injson)
    try:
        sc = rep.get(args.label)
    except KeyError as e:
        return _die(2, str(e))

    if not sc.path:
        return _die(2, f"SCENARIO_PATH_EMPTY label={args.label}")

    ext = extend_plateau(sc.path, args.months)

    fp = first_profitable_month(ext)
    fc = first_cum_net_ge_0_month(ext)

    print("=== FORECAST PLAN (v13.2) ===")
    print(f"injson={injson.as_posix()}")
    print(f"label={args.label}")
    print(f"months={args.months}")
    print(f"rows_out={len(ext)}")
    print(f"first_profitable_month={fp}")
    print(f"first_cum_net_ge_0_month={fc}")

    if not args.quiet:
        print("--- months ---")
        for r in ext:
            print(
                f"m={r.m} net_mxn={r.net_mxn:.2f} cum_mxn={r.cum_mxn:.2f} "
                f"roas={r.roas:.4f} collect={r.collect:.4f} unit={r.unit:.2f} thr={r.thr:.2f}"
            )

    ok = int(len(ext) == args.months and ext[0].m == 1 and ext[-1].m == args.months)
    print(f"PLAN_OK={ok}")
    return 0 if ok == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())

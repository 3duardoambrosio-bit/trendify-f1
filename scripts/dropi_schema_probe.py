from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _extract_items(dump: Any) -> list[dict]:
    if isinstance(dump, list):
        return [x for x in dump if isinstance(x, dict)]
    if isinstance(dump, dict):
        for k in ("items", "results", "candidates", "data", "products"):
            v = dump.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        vals = list(dump.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return vals
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    p = Path(args.dump)
    dump = json.loads(p.read_text(encoding="utf-8"))
    items = _extract_items(dump)

    c = Counter()
    nested = Counter()

    for it in items:
        for k, v in it.items():
            c[k] += 1
            if isinstance(v, dict):
                for kk in v.keys():
                    nested[f"{k}.{kk}"] += 1

    print("dropi_schema_probe: OK")
    print(f"- items: {len(items)}")
    print("- top_keys:")
    for k, n in c.most_common(args.n):
        print(f"  {k}: {n}")

    if nested:
        print("- top_nested_keys:")
        for k, n in nested.most_common(args.n):
            print(f"  {k}: {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
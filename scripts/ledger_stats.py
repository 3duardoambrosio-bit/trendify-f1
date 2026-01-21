from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/ledger/events.ndjson")
    ap.add_argument("--tail", type=int, default=10)
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"[ERR] ledger not found: {p}")
        return 2

    counts = Counter()
    total = 0
    bad = 0
    tail = []

    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        try:
            ev = json.loads(line)
            counts[ev.get("event_type","UNKNOWN")] += 1
            tail.append(ev)
            if len(tail) > args.tail:
                tail.pop(0)
        except Exception:
            bad += 1

    print("LEDGER_STATS")
    print("path=", str(p))
    print("total_lines=", total)
    print("bad_json_lines=", bad)
    print("by_event_type=", dict(counts))

    print("\nTAIL")
    for ev in tail:
        ts = (ev.get("ts_utc") or ev.get("ts") or ev.get("timestamp") or ev.get("time") or ev.get("created_at") or "?")
        et = ev.get("event_type","?")
        ent = f'{ev.get("entity_type","?")}:{ev.get("entity_id","?")}'
        print(f"- {ts} | {et} | {ent}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


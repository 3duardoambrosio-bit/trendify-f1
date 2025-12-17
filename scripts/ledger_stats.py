from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerStats:
    total_lines: int
    parsed_events: int
    invalid_json: int
    by_event_type: dict[str, int]
    by_entity_type: dict[str, int]


def compute_stats(lines: list[str]) -> LedgerStats:
    total = 0
    parsed = 0
    invalid = 0
    by_event = Counter()
    by_entity = Counter()

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        total += 1
        try:
            obj: Any = json.loads(raw)
        except Exception:
            invalid += 1
            by_event["_INVALID_JSON"] += 1
            continue

        parsed += 1
        ev = str(obj.get("event_type", "_MISSING_EVENT_TYPE"))
        ent = str(obj.get("entity_type", "_MISSING_ENTITY_TYPE"))
        by_event[ev] += 1
        by_entity[ent] += 1

    return LedgerStats(
        total_lines=total,
        parsed_events=parsed,
        invalid_json=invalid,
        by_event_type=dict(by_event),
        by_entity_type=dict(by_entity),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/ledger/events.ndjson")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"LEDGER_STATS: MISSING_LEDGER path={p}")
        return 0

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    s = compute_stats(lines)

    print("=== LEDGER STATS ===")
    print(f"path: {p}")
    print(f"lines: {s.total_lines} parsed: {s.parsed_events} invalid_json: {s.invalid_json}")

    def show(title: str, d: dict[str, int]) -> None:
        print(f"\n{title}")
        for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[: args.top]:
            print(f"- {k}: {v}")

    show("Top event_type:", s.by_event_type)
    show("Top entity_type:", s.by_entity_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

from pathlib import Path
import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "mission": "sell_before_june_with_assisted_synapse",
        "direction_changed": 0,
        "automation_cancelled": 0,
        "automation_after_signals": 1,
        "next_front": "A8-R42B Product Decision Packet local",
        "repo": str(repo),
    }

    output = out_dir / "a8_r42_mission_lock.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"MISSION_LOCK_JSON={output}")
    print("MISSION=sell_before_june_with_assisted_synapse")
    print("DIRECTION_CHANGED=0")
    print("AUTOMATION_CANCELLED=0")
    print("AUTOMATION_AFTER_SIGNALS=1")
    print("NEXT_FRONT=A8-R42B Product Decision Packet local")
    print("A8_R42_MISSION_LOCK_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

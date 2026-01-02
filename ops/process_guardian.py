from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml  # requires PyYAML; if not installed, user can `pip install pyyaml` or we fallback.

from ops.ledger_writer import LedgerWriter

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

@dataclass
class CheckResult:
    passed: bool
    check_type: str
    details: Dict[str, Any]

class EvidenceChecks:
    def __init__(self, ledger_path_hint: str = "data/ledger/events.ndjson") -> None:
        self.ledger_path_hint = ledger_path_hint

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def glob_exists(self, pattern: str) -> bool:
        return len(glob.glob(pattern)) > 0

    def ledger_event_exists(self, event_type: str) -> bool:
        # Best-effort: check fallback NDJSON; if your core ledger uses another file, set LEDGER_PATH.
        path = os.getenv("LEDGER_PATH", self.ledger_path_hint)
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("type") == event_type:
                        return True
        except Exception:
            return False
        return False

class Staircase:
    def __init__(self, map_path: str = "ops/staircase_map.yaml") -> None:
        self.map_path = map_path
        self.ledger = LedgerWriter()

        try:
            with open(map_path, "r", encoding="utf-8") as f:
                self.map = yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load staircase map: {e}")

        self.checks = EvidenceChecks()

    def _get_step(self, step_id: str) -> Dict[str, Any]:
        steps = self.map.get("steps") or {}
        if step_id not in steps:
            raise RuntimeError(f"Unknown step: {step_id}")
        return steps[step_id]

    def check_step(self, step_id: str) -> Dict[str, Any]:
        step = self._get_step(step_id)
        dod = step.get("dod_checks") or []

        results: List[CheckResult] = []
        missing: List[Dict[str, Any]] = []

        for chk in dod:
            ctype = chk.get("type")
            args = chk.get("args") or {}
            optional = bool(chk.get("optional", False))

            passed = False
            if ctype == "file_exists":
                passed = self.checks.file_exists(args["path"])
            elif ctype == "glob_exists":
                passed = self.checks.glob_exists(args["pattern"])
            elif ctype == "ledger_event_exists":
                passed = self.checks.ledger_event_exists(args["event_type"])
            else:
                # Unknown check => fail hard
                passed = False

            results.append(CheckResult(passed=passed, check_type=ctype, details=args))
            if not passed and not optional:
                missing.append({"type": ctype, "args": args})

        allowed = len(missing) == 0
        payload = {
            "step_id": step_id,
            "allowed": allowed,
            "missing": missing,
            "checks": [r.__dict__ for r in results],
        }
        self.ledger.emit("STEP_GATE_CHECKED", payload)
        return payload

    def whisper(self, step_id: str, expectation: str, reality: str, learning: str, obstacle: str) -> Dict[str, Any]:
        payload = {
            "step_id": step_id,
            "ts_utc": _utc_now_iso(),
            "expectation": expectation,
            "reality": reality,
            "learning": learning,
            "implications_for_next": [],
            "obstacle_type": obstacle,
        }
        self.ledger.emit("STEP_WHISPER_RECORDED", payload)
        return payload

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="process_guardian")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check")
    p_check.add_argument("--step", required=True)

    p_wh = sub.add_parser("whisper")
    p_wh.add_argument("--step", required=True)
    p_wh.add_argument("--expectation", required=True)
    p_wh.add_argument("--reality", required=True)
    p_wh.add_argument("--learning", required=True)
    p_wh.add_argument("--obstacle", required=True, choices=["LIFE_OBSTACLE","SELF_INFLICTED","SYSTEM_GAP","MARKET_REALITY"])

    args = p.parse_args(argv)
    sc = Staircase()

    if args.cmd == "check":
        out = sc.check_step(args.step)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["allowed"] else 2

    if args.cmd == "whisper":
        out = sc.whisper(args.step, args.expectation, args.reality, args.learning, args.obstacle)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    return 1

if __name__ == "__main__":
    raise SystemExit(main())

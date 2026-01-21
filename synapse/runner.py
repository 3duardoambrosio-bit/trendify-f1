from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from synapse.learning.learning_loop import LearningLoop, LearningLoopConfig, __LL_MARKER__


RUNNER_MARKER = "RUNNER_2026-01-12_V2_TSUTC"
LEDGER_REL = Path("data/ledger/events.ndjson")


def _utc_now_z() -> str:
    # reuse the same style across repo
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_ts_utc(ts: Optional[str]) -> str:
    s = (ts or "").strip()
    if not s:
        return _utc_now_z()
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    if s.endswith("Z"):
        return s
    tail = s[-6:]
    if (len(tail) == 6) and (tail[0] in ("+", "-")) and (tail[3] == ":"):
        return s
    return s + "Z"


class NdjsonLedger:
    """
    Ledger mínimo para Fase 1:
    - read: lista eventos (dicts)
    - write: append evento con contrato ts_utc + payload
    """
    def __init__(self, path: Path):
        self.path = path
        self.writes: List[Dict[str, Any]] = []

    def _read_lines(self) -> List[str]:
        if not self.path.exists():
            return []
        try:
            return self.path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

    def iter_events(self) -> List[Any]:
        out: List[Any] = []
        for ln in self._read_lines():
            ln = (ln or "").strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    @property
    def events(self) -> List[Any]:
        return self.iter_events()

    def write(self, payload_like: Dict[str, Any]) -> None:
        # LearningLoop manda dict plano (event_type, timestamp, status, ...)
        ts_in = payload_like.get("ts_utc") or payload_like.get("ts") or payload_like.get("timestamp")
        ts_utc = _normalize_ts_utc(str(ts_in) if ts_in is not None else None)

        ev = {
            "ts_utc": ts_utc,
            "ts": ts_utc,  # legacy compat
            "payload": dict(payload_like),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

        self.writes.append(ev)

    # Compat aliases por si alguien llama write_event/emit/etc
    def write_event(self, payload_like: Dict[str, Any]) -> None:
        self.write(payload_like)

    def emit(self, payload_like: Dict[str, Any]) -> None:
        self.write(payload_like)

    def record(self, payload_like: Dict[str, Any]) -> None:
        self.write(payload_like)

    def add_event(self, payload_like: Dict[str, Any]) -> None:
        self.write(payload_like)


class NullLedger:
    def __init__(self) -> None:
        self.writes: List[Dict[str, Any]] = []

    def iter_events(self) -> List[Any]:
        return []

    @property
    def events(self) -> List[Any]:
        return []

    def write(self, payload_like: Dict[str, Any]) -> None:
        self.writes.append(payload_like)

    write_event = emit = record = add_event = write


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.runner", description="Synapse Fase 1 runner (learning loop).")
    ap.add_argument("--min-records", type=int, default=8)
    ap.add_argument("--min-spend-before-learn", type=float, default=15.0)
    ap.add_argument("--require-evidence", action="store_true", default=True)
    ap.add_argument("--no-require-evidence", action="store_true", default=False)
    ap.add_argument("--force", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--no-ledger", action="store_true", default=False)
    args = ap.parse_args(argv)

    repo = Path.cwd()
    ledger_path = repo / LEDGER_REL

    require_evidence = bool(args.require_evidence) and (not bool(args.no_require_evidence))

    cfg = LearningLoopConfig(
        min_records=int(args.min_records),
        min_spend_before_learn=float(args.min_spend_before_learn),
        require_evidence=require_evidence,
    )

    readonly = os.getenv("SYNAPSE_READONLY", "").strip() in ("1", "true", "TRUE", "yes", "YES")

    if args.no_ledger or readonly:
        ledger: Any = NullLedger()
    else:
        ledger = NdjsonLedger(ledger_path)

    loop = LearningLoop(repo=repo)
    res = loop.run(ledger, cfg=cfg, force=bool(args.force), dry_run=bool(args.dry_run))

    # counts
    try:
        ledger_events = len(getattr(ledger, "events"))
    except Exception:
        ledger_events = 0
    try:
        ledger_writes = len(getattr(ledger, "writes"))
    except Exception:
        ledger_writes = 0

    out: Dict[str, Any] = {
        "runner": "synapse.runner",
        "marker": RUNNER_MARKER,
        "ts": _utc_now_z(),
        "repo": str(repo),
        "learning_loop_marker": __LL_MARKER__,
        "effective_config": asdict(cfg),
        "learning_loop_result": {
            "status": res.status,
            "input_hash": res.input_hash,
            "state_path": res.state_path,
            "report_path": res.report_path,
            "weights_path": res.weights_path,
        },
        "ledger_path": str(ledger_path),
        "ledger_events": int(ledger_events),
        "ledger_writes": int(ledger_writes),
        "readonly": bool(readonly),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
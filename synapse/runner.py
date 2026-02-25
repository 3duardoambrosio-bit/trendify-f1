from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import deal

# keep pack semantics import (present in repo)
from infra.result import Err, Ok, Result  # noqa: F401


LEDGER_REL = Path("data") / "ledger" / "events.ndjson"


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_ts_utc(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload)
    if "ts_utc" not in out:
        out["ts_utc"] = _utc_now_iso_z()
    return out


def _build_ndjson_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = _normalize_ts_utc(payload)
    return {"payload": p, "ts": _utc_now_iso_z(), "ts_utc": p.get("ts_utc", _utc_now_iso_z())}


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    root: Path
    ledger_path: Path
    quiet: bool
    no_ledger: bool


class NdjsonLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.writes: List[Dict[str, Any]] = []

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def write(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        evt = _build_ndjson_event(payload)

        # ensure_ascii=True prevents Unicode NEL (U+0085) from being treated as newline by splitlines()
        line = json.dumps(evt, ensure_ascii=True, separators=(",", ":"))

        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        self.writes.append(payload)

    @deal.pre(lambda self: True, message="NdjsonLedger.iter_events contract")
    @deal.post(lambda result: isinstance(result, list), message="iter_events must return list")
    @deal.raises(deal.RaisesContractError)
    def iter_events(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    @property
    @deal.pre(lambda self: True, message="NdjsonLedger.events contract")
    @deal.post(lambda result: isinstance(result, list), message="events must be list")
    @deal.raises(deal.RaisesContractError)
    def events(self) -> List[Dict[str, Any]]:
        return list(self.writes)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def write_event(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def emit(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def record(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def add_event(self, payload: Dict[str, Any]) -> None:
        self.write(payload)


class NullLedger:
    def __init__(self) -> None:
        self.writes: List[Dict[str, Any]] = []

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def write(self, payload: Dict[str, Any]) -> None:
        self.writes.append(payload)

    @deal.pre(lambda self: True, message="NullLedger.iter_events contract")
    @deal.post(lambda result: isinstance(result, list), message="iter_events must return list")
    @deal.raises(deal.RaisesContractError)
    def iter_events(self) -> List[Dict[str, Any]]:
        return []

    @property
    @deal.pre(lambda self: True, message="NullLedger.events contract")
    @deal.post(lambda result: isinstance(result, list), message="events must be list")
    @deal.raises(deal.RaisesContractError)
    def events(self) -> List[Dict[str, Any]]:
        return list(self.writes)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def write_event(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def emit(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def record(self, payload: Dict[str, Any]) -> None:
        self.write(payload)

    @deal.pre(lambda self, payload: isinstance(payload, dict), message="payload must be dict")
    @deal.raises(deal.RaisesContractError)
    def add_event(self, payload: Dict[str, Any]) -> None:
        self.write(payload)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=".")
    ap.add_argument("--ledger", type=str, default=str(LEDGER_REL))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-ledger", action="store_true")
    return ap.parse_args(argv)


def _build_config(ns: argparse.Namespace) -> RunnerConfig:
    root = Path(ns.root).resolve()
    ledger_path = (root / ns.ledger).resolve()
    return RunnerConfig(root=root, ledger_path=ledger_path, quiet=bool(ns.quiet), no_ledger=bool(ns.no_ledger))


def _ledger_for(cfg: RunnerConfig) -> NdjsonLedger | NullLedger:
    if cfg.no_ledger:
        return NullLedger()
    return NdjsonLedger(cfg.ledger_path)


@deal.pre(lambda argv=None: True, message="main contract")
@deal.post(lambda result: isinstance(result, int), message="main must return int")
@deal.raises(deal.RaisesContractError)
def main(argv: Optional[Sequence[str]] = None) -> int:
    ns = _parse_args(argv)
    cfg = _build_config(ns)
    ledger = _ledger_for(cfg)

    from synapse.learning.learning_loop import LearningLoop, LearningLoopConfig

    llc = LearningLoopConfig(root=str(cfg.root), ledger=str(cfg.ledger_path), quiet=cfg.quiet)
    loop = LearningLoop(llc)
    rc = loop.run(ledger=ledger)
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import argparse
import json
import os
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
    mode = ap.add_mutually_exclusive_group(required=False)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return ap.parse_args(argv)


def _build_config(ns: argparse.Namespace) -> RunnerConfig:
    root = Path(ns.root).resolve()
    ledger_path = (root / ns.ledger).resolve()
    return RunnerConfig(root=root, ledger_path=ledger_path, quiet=bool(ns.quiet), no_ledger=bool(ns.no_ledger))


def _ledger_for(cfg: RunnerConfig) -> NdjsonLedger | NullLedger:
    if cfg.no_ledger:
        return NullLedger()
    return NdjsonLedger(cfg.ledger_path)


def _make_learning_loop_config(*, root, ledger, quiet):
    import inspect
    from synapse.learning.learning_loop import LearningLoopConfig

    sig = inspect.signature(LearningLoopConfig)
    params = {
        name: param
        for name, param in sig.parameters.items()
        if name != "self"
    }

    kwargs = {}
    if "root" in params:
        kwargs["root"] = root
    if "ledger" in params:
        kwargs["ledger"] = ledger
    if "quiet" in params:
        kwargs["quiet"] = quiet

    missing = [
        name
        for name, param in params.items()
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and param.default is inspect._empty
        and name not in kwargs
    ]
    if missing:
        raise TypeError(
            f"LearningLoopConfig missing required params unsupported by runner adapter: {missing}"
        )

    return LearningLoopConfig(**kwargs)


def _run_learning_loop(loop, *, ledger, cfg, force=False, dry_run=False):
    import inspect

    sig = inspect.signature(loop.run)
    params = {
        name: param
        for name, param in sig.parameters.items()
        if name != "self"
    }

    kwargs = {}
    if "ledger_obj" in params:
        kwargs["ledger_obj"] = ledger
    elif "ledger" in params:
        kwargs["ledger"] = ledger

    if "cfg" in params:
        kwargs["cfg"] = cfg
    if "force" in params:
        kwargs["force"] = force
    if "dry_run" in params:
        kwargs["dry_run"] = dry_run

    missing = [
        name
        for name, param in params.items()
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
        and param.default is inspect._empty
        and name not in kwargs
    ]
    if missing:
        raise TypeError(
            f"LearningLoop.run missing required params unsupported by runner adapter: {missing}"
        )

    return loop.run(**kwargs)


def _readonly_enabled() -> bool:
    return os.getenv("SYNAPSE_READONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _learning_result_rc(result: Any) -> int:
    if isinstance(result, int) and not isinstance(result, bool):
        return result if result in (0, 2, 3) else 3

    status = getattr(result, "status", None)
    if status in {"COMPLETED", "COMPLETED_DRY_RUN", "SKIPPED"}:
        return 0
    if status in {
        "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_SPEND",
        "INSUFFICIENT_RECORDS",
    }:
        return 2
    return 3


def _learning_result_status(result: Any, rc: int) -> str:
    status = getattr(result, "status", None)
    if isinstance(status, str) and status:
        return status
    return {0: "COMPLETED", 2: "BLOCKED", 3: "EXECUTION_ERROR"}[rc]


def _emit_learning_output(
    *,
    status: str,
    dry_run: bool,
    apply_requested: bool,
    writes_allowed: bool,
    rc: int,
    result: Any = None,
) -> None:
    print(f"LEARNING_STATUS={status}")
    print(f"LEARNING_DRY_RUN={str(dry_run).lower()}")
    print(f"LEARNING_APPLY_REQUESTED={str(apply_requested).lower()}")
    print(f"LEARNING_WRITES_ALLOWED={str(writes_allowed).lower()}")
    print(f"LEARNING_RC={rc}")

    for field, output_name in (
        ("input_hash", "LEARNING_INPUT_HASH"),
        ("state_path", "LEARNING_STATE_PATH"),
        ("report_path", "LEARNING_REPORT_PATH"),
        ("weights_path", "LEARNING_WEIGHTS_PATH"),
    ):
        value = getattr(result, field, None)
        if value:
            print(f"{output_name}={value}")


@deal.pre(lambda argv=None: True, message="main contract")
@deal.post(lambda result: isinstance(result, int), message="main must return int")
@deal.raises(deal.RaisesContractError)
def main(argv: Optional[Sequence[str]] = None) -> int:
    ns = _parse_args(argv)
    apply_requested = bool(ns.apply)

    if not apply_requested:
        status = "DRY_RUN_NOOP" if ns.dry_run else "DEFAULT_NOOP"
        _emit_learning_output(
            status=status,
            dry_run=True,
            apply_requested=False,
            writes_allowed=False,
            rc=0,
        )
        return 0

    if _readonly_enabled():
        _emit_learning_output(
            status="READONLY_BLOCKED",
            dry_run=False,
            apply_requested=True,
            writes_allowed=False,
            rc=2,
        )
        return 2

    try:
        cfg = _build_config(ns)
        ledger = _ledger_for(cfg)

        from synapse.learning.learning_loop import LearningLoop

        llc = _make_learning_loop_config(
            root=cfg.root,
            ledger=ledger,
            quiet=cfg.quiet,
        )
        loop = LearningLoop(cfg.root)
        result = _run_learning_loop(
            loop,
            ledger=ledger,
            cfg=llc,
            force=False,
            dry_run=False,
        )
        rc = _learning_result_rc(result)
        _emit_learning_output(
            status=_learning_result_status(result, rc),
            dry_run=False,
            apply_requested=True,
            writes_allowed=True,
            rc=rc,
            result=result,
        )
        return rc
    except Exception:
        _emit_learning_output(
            status="EXECUTION_ERROR",
            dry_run=False,
            apply_requested=True,
            writes_allowed=True,
            rc=3,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

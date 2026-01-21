from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__LL_MARKER__ = "LL_PATCH_2026-01-10_EVIDENCE_FIRST_HOTFIX_ABSPATH_V3"

STATE_REL = Path("data/learning/learning_state.json")
REPORT_REL = Path("data/learning/learning_report.json")
WEIGHTS_REL = Path("data/config/weights.json")

STATUS_COMPLETED = "COMPLETED"
STATUS_COMPLETED_DRY_RUN = "COMPLETED_DRY_RUN"
STATUS_SKIPPED = "SKIPPED"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUS_INSUFFICIENT_SPEND = "INSUFFICIENT_SPEND"
STATUS_INSUFFICIENT_RECORDS = "INSUFFICIENT_RECORDS"

EV_COMPLETED = "LEARNING_LOOP_COMPLETED"
EV_SKIPPED = "LEARNING_LOOP_SKIPPED"

EVIDENCE_KEYS = {
    "spend",
    "roas",
    "hook_rate_3s",
    "clicks",
    "conversions",
    "impressions",
    "platform",
    "product_id",
    "creative_id",
    "campaign_id",
    "utm_content",
    "utm",
    "hook_id",
    "angle",
    "format",
}


def _utc_now_z() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_utm_content(utm: str | None) -> Dict[str, Any]:
    """
    Expected format: Hh0_Adolor_Fhands_V1
    Mapping:
      Hh0 -> hook_id="h0"
      Adolor -> angle="dolor"
      Fhands -> format="hands"
      V1 -> version=1
    If invalid -> {}
    """
    if not utm or not isinstance(utm, str):
        return {}
    utm = utm.strip()
    if not utm:
        return {}

    out: Dict[str, Any] = {}
    parts = [p for p in utm.split("_") if p]

    for p in parts:
        if len(p) < 2:
            continue
        head = p[0]
        tail = p[1:]
        if not tail:
            continue

        if head in ("H", "h"):
            out["hook_id"] = tail
        elif head in ("A", "a"):
            out["angle"] = str(tail).lower()
        elif head in ("F", "f"):
            out["format"] = str(tail).lower()
        elif head in ("V", "v"):
            try:
                out["version"] = int(tail)
            except Exception:
                out["version"] = tail

    return out if out else {}


def parse_utm(utm: str | None) -> Dict[str, Any]:
    return parse_utm_content(utm)


@dataclass(frozen=True)
class LearningLoopConfig:
    min_records: int = 8
    min_spend_before_learn: float = 15.0
    require_evidence: bool = True


@dataclass(frozen=True)
class LearningRunResult:
    status: str
    input_hash: str
    state_path: str
    weights_path: str
    report_path: str


def _safe_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash_payloads(payloads: List[Dict[str, Any]]) -> str:
    s = _safe_dumps(payloads)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _try_json_str(x: Any) -> Any:
    if not isinstance(x, str):
        return None
    s = x.strip()
    if not s or not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _iter_events(ledger_obj: Any) -> List[Any]:
    for attr in ("events", "_events", "rows"):
        if hasattr(ledger_obj, attr):
            try:
                ev = getattr(ledger_obj, attr)
                if callable(ev):
                    out = ev()
                    return list(out) if out is not None else []
                return list(ev) if ev is not None else []
            except Exception:
                pass

    for m in ("iter_events", "read_events", "load_events", "get_events", "list_events"):
        fn = getattr(ledger_obj, m, None)
        if callable(fn):
            try:
                out = fn()
                return list(out) if out is not None else []
            except Exception:
                pass

    try:
        return list(ledger_obj)
    except Exception:
        return []


def _extract_payload(e: Any) -> Dict[str, Any]:
    if isinstance(e, dict):
        for k in ("payload", "data", "record", "event", "body"):
            if k in e:
                v = e.get(k)
                if isinstance(v, dict):
                    return v
                parsed = _try_json_str(v)
                if isinstance(parsed, dict):
                    return parsed
        if any(k in e for k in EVIDENCE_KEYS):
            return e

    for k in ("payload", "data", "record", "event", "body"):
        try:
            v = getattr(e, k, None)
        except Exception:
            v = None
        if isinstance(v, dict):
            return v
        parsed = _try_json_str(v)
        if isinstance(parsed, dict):
            return parsed

    try:
        d = vars(e)
        if isinstance(d, dict):
            if isinstance(d.get("payload"), dict):
                return d["payload"]
            if any(k in d for k in EVIDENCE_KEYS):
                return d
    except Exception:
        pass

    return {}


def _has_evidence(p: Dict[str, Any]) -> bool:
    for k in EVIDENCE_KEYS:
        if k in p:
            v = p.get(k)
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return True
    ev = p.get("evidence")
    return isinstance(ev, dict) and bool(ev)


def _get_spend(p: Dict[str, Any]) -> float:
    for k in ("spend", "cost", "amount_spent", "spend_total"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _get_roas(p: Dict[str, Any]) -> float:
    for k in ("roas", "roas_mean"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _get_hook_rate(p: Dict[str, Any]) -> float:
    for k in ("hook_rate_3s", "hook_rate_3s_mean"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _classify(p: Dict[str, Any]) -> Tuple[str, str, str]:
    utm = p.get("utm_content") or p.get("utm")
    parsed = parse_utm_content(utm) if isinstance(utm, str) else {}

    angle = p.get("angle") or parsed.get("angle") or "unknown"
    fmt = p.get("format") or parsed.get("format") or "unknown"
    hook = p.get("hook_id") or parsed.get("hook_id") or "unknown"

    return str(angle).lower(), str(fmt).lower(), str(hook).lower()


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        out = json.loads(path.read_text(encoding="utf-8"))
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _ledger_write(ledger_obj: Any, *, event_type: str, status: str, input_hash: str, total_spend: Optional[float] = None) -> None:
    ev: Dict[str, Any] = {
        "event_type": event_type,
        "timestamp": _utc_now_z(),
        "status": status,
        "input_hash": input_hash,
    }
    if total_spend is not None:
        ev["total_spend"] = float(total_spend)

    for m in ("write", "write_event", "emit", "record", "add_event"):
        fn = getattr(ledger_obj, m, None)
        if callable(fn):
            try:
                fn(ev)
                return
            except Exception:
                pass

    try:
        writes = getattr(ledger_obj, "writes", None)
        if isinstance(writes, list):
            writes.append(ev)
    except Exception:
        pass


class LearningLoop:
    def __init__(self, repo: Path | str | None = None):
        self.repo = Path(repo) if repo is not None else Path.cwd()

    def run(self, ledger_obj: Any, cfg: LearningLoopConfig = LearningLoopConfig(), force: bool = False, dry_run: bool = False) -> LearningRunResult:
        state_abs = self.repo / STATE_REL
        report_abs = self.repo / REPORT_REL
        weights_abs = self.repo / WEIGHTS_REL

        # Absolutos que regresamos (clave del bug)
        state_path = str(state_abs)
        report_path = str(report_abs)
        weights_path = str(weights_abs)

        # Ensure dirs exist
        state_abs.parent.mkdir(parents=True, exist_ok=True)
        report_abs.parent.mkdir(parents=True, exist_ok=True)
        weights_abs.parent.mkdir(parents=True, exist_ok=True)

        events = _iter_events(ledger_obj)
        payloads_all = [_extract_payload(e) for e in events]
        payloads_all = [p for p in payloads_all if isinstance(p, dict) and p]

        payloads_used = payloads_all
        if cfg.require_evidence:
            payloads_used = [p for p in payloads_all if _has_evidence(p)]

        input_hash = _hash_payloads(payloads_used)

        # Idempotencia => SKIPPED
        if (not force) and state_abs.exists():
            prev = _read_json_dict(state_abs)
            if prev.get("input_hash") == input_hash and prev.get("status") in (STATUS_COMPLETED, STATUS_COMPLETED_DRY_RUN, STATUS_SKIPPED):
                status = STATUS_SKIPPED
                _write_json(
                    state_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": int(prev.get("records_used", 0) or 0),
                    },
                )
                _write_json(
                    report_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": int(prev.get("records_used", 0) or 0),
                        "total_spend": 0.0,
                        "reason": "IDEMPOTENT_SKIP",
                    },
                )
                _ledger_write(ledger_obj, event_type=EV_SKIPPED, status=status, input_hash=input_hash, total_spend=0.0)
                return LearningRunResult(status, input_hash, state_path, weights_path, report_path)

        # Gates
        if cfg.require_evidence:
            # evidence-first manda: NO devolver INSUFFICIENT_RECORDS aquí
            if len(payloads_used) < int(cfg.min_records):
                status = STATUS_INSUFFICIENT_EVIDENCE
                _write_json(
                    state_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": int(len(payloads_used)),
                    },
                )
                _write_json(
                    report_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": int(len(payloads_used)),
                        "total_spend": 0.0,
                        "min_records": int(cfg.min_records),
                        "require_evidence": True,
                    },
                )
                _ledger_write(ledger_obj, event_type=EV_SKIPPED, status=status, input_hash=input_hash, total_spend=0.0)
                return LearningRunResult(status, input_hash, state_path, weights_path, report_path)
        else:
            if len(events) < int(cfg.min_records):
                status = STATUS_INSUFFICIENT_RECORDS
                _write_json(
                    state_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": 0,
                    },
                )
                _write_json(
                    report_abs,
                    {
                        "marker": __LL_MARKER__,
                        "generated_at": _utc_now_z(),
                        "status": status,
                        "input_hash": input_hash,
                        "records_used": 0,
                        "total_spend": 0.0,
                        "min_records": int(cfg.min_records),
                        "require_evidence": False,
                    },
                )
                _ledger_write(ledger_obj, event_type=EV_SKIPPED, status=status, input_hash=input_hash, total_spend=0.0)
                return LearningRunResult(status, input_hash, state_path, weights_path, report_path)

        total_spend = sum(_get_spend(p) for p in payloads_used)

        if float(total_spend) < float(cfg.min_spend_before_learn):
            status = STATUS_INSUFFICIENT_SPEND
            _write_json(
                state_abs,
                {
                    "marker": __LL_MARKER__,
                    "generated_at": _utc_now_z(),
                    "status": status,
                    "input_hash": input_hash,
                    "records_used": int(len(payloads_used)),
                },
            )
            _write_json(
                report_abs,
                {
                    "marker": __LL_MARKER__,
                    "generated_at": _utc_now_z(),
                    "status": status,
                    "input_hash": input_hash,
                    "records_used": int(len(payloads_used)),
                    "total_spend": float(total_spend),
                    "min_spend_before_learn": float(cfg.min_spend_before_learn),
                },
            )
            _ledger_write(ledger_obj, event_type=EV_SKIPPED, status=status, input_hash=input_hash, total_spend=float(total_spend))
            return LearningRunResult(status, input_hash, state_path, weights_path, report_path)

        # Dry run: report+state sí, weights NO
        if dry_run:
            status = STATUS_COMPLETED_DRY_RUN
            _write_json(
                state_abs,
                {
                    "marker": __LL_MARKER__,
                    "generated_at": _utc_now_z(),
                    "status": status,
                    "input_hash": input_hash,
                    "records_used": int(len(payloads_used)),
                },
            )
            _write_json(
                report_abs,
                {
                    "marker": __LL_MARKER__,
                    "generated_at": _utc_now_z(),
                    "status": status,
                    "input_hash": input_hash,
                    "records_used": int(len(payloads_used)),
                    "total_spend": float(total_spend),
                    "dry_run": True,
                },
            )
            _ledger_write(ledger_obj, event_type=EV_COMPLETED, status=status, input_hash=input_hash, total_spend=float(total_spend))
            return LearningRunResult(status, input_hash, state_path, weights_path, report_path)

        # COMPLETED: weights sí
        roas_vals = [_get_roas(p) for p in payloads_used]
        hook_vals = [_get_hook_rate(p) for p in payloads_used]
        roas_mean = (sum(roas_vals) / len(roas_vals)) if roas_vals else 0.0
        hook_mean = (sum(hook_vals) / len(hook_vals)) if hook_vals else 0.0

        angles: Dict[str, Dict[str, float]] = {}
        formats: Dict[str, Dict[str, float]] = {}
        hooks: Dict[str, Dict[str, float]] = {}

        def _acc(bucket: Dict[str, Dict[str, float]], key: str, spend: float, roas: float, hookr: float) -> None:
            b = bucket.setdefault(key, {"count": 0.0, "spend": 0.0, "roas_sum": 0.0, "roas_n": 0.0, "hook_sum": 0.0, "hook_n": 0.0})
            b["count"] += 1.0
            b["spend"] += float(spend)
            b["roas_sum"] += float(roas)
            b["roas_n"] += 1.0
            b["hook_sum"] += float(hookr)
            b["hook_n"] += 1.0

        for p in payloads_used:
            a, f, h = _classify(p)
            _acc(angles, a, _get_spend(p), _get_roas(p), _get_hook_rate(p))
            _acc(formats, f, _get_spend(p), _get_roas(p), _get_hook_rate(p))
            _acc(hooks, h, _get_spend(p), _get_roas(p), _get_hook_rate(p))

        def _finalize(raw: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for k, b in raw.items():
                roas_m = (b["roas_sum"] / b["roas_n"]) if b["roas_n"] else 0.0
                hook_m = (b["hook_sum"] / b["hook_n"]) if b["hook_n"] else 0.0
                out[k] = {
                    "count": int(b["count"]),
                    "spend": float(b["spend"]),
                    "roas_mean": float(roas_m),
                    "hook_rate_3s_mean": float(hook_m),
                }
            return out

        weights_obj: Dict[str, Any] = {
            "schema_version": "1.0.0",
            "generated_at": _utc_now_z(),
            "marker": __LL_MARKER__,
            "records": int(len(events)),
            "records_used": int(len(payloads_used)),
            "total_spend": float(total_spend),
            "roas_mean": float(roas_mean),
            "hook_rate_3s_mean": float(hook_mean),
            "angles": _finalize(angles),
            "formats": _finalize(formats),
            "hooks": _finalize(hooks),
        }
        _write_json(weights_abs, weights_obj)

        status = STATUS_COMPLETED
        _write_json(
            state_abs,
            {
                "marker": __LL_MARKER__,
                "generated_at": _utc_now_z(),
                "status": status,
                "input_hash": input_hash,
                "records_used": int(len(payloads_used)),
            },
        )
        _write_json(
            report_abs,
            {
                "marker": __LL_MARKER__,
                "generated_at": _utc_now_z(),
                "status": status,
                "input_hash": input_hash,
                "records_used": int(len(payloads_used)),
                "total_spend": float(total_spend),
                "dry_run": False,
            },
        )
        _ledger_write(ledger_obj, event_type=EV_COMPLETED, status=status, input_hash=input_hash, total_spend=float(total_spend))
        return LearningRunResult(status, input_hash, state_path, weights_path, report_path)


__all__ = [
    "__LL_MARKER__",
    "parse_utm_content",
    "parse_utm",
    "LearningLoop",
    "LearningLoopConfig",
    "LearningRunResult",
]

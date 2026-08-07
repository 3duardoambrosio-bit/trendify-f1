from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


__LL_MARKER__ = "LL_PATCH_2026-01-12_SYNTHETIC_GUARD_V5"

STATE_REL = Path("data/learning/learning_state.json")
REPORT_REL = Path("data/learning/learning_report.json")
WEIGHTS_REL = Path("data/config/weights.json")

STATUS_COMPLETED = "COMPLETED"
STATUS_COMPLETED_DRY_RUN = "COMPLETED_DRY_RUN"
STATUS_SKIPPED = "SKIPPED"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUS_INSUFFICIENT_SPEND = "INSUFFICIENT_SPEND"
STATUS_INSUFFICIENT_RECORDS = "INSUFFICIENT_RECORDS"
STATUS_LEDGER_UNREADABLE = "LEDGER_UNREADABLE"
STATUS_PAYLOAD_SHAPE_DRIFT = "PAYLOAD_SHAPE_DRIFT"
STATUS_LEARNING_LOOP_LEDGER_FAILED = "LEARNING_LOOP_LEDGER_FAILED"

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


class LearningLoopError(Exception):
    """Base class for high-integrity learning loop failures."""


class LedgerReadError(LearningLoopError):
    """The ledger could not be read safely."""


class LedgerWriteError(LearningLoopError):
    """The loop could not persist its observability event to the ledger."""


class PayloadExtractError(LearningLoopError):
    """The payload shape could not be inspected safely."""


class SyntheticCheckError(LearningLoopError):
    """The synthetic-data safety latch could not classify a payload safely."""


@dataclass(frozen=True)
class LearningLoopConfig:
    min_records: int = 8
    min_spend_before_learn: float = 15.0
    require_evidence: bool = True
    payload_shape_drift_ratio_threshold: float = 0.5
    payload_shape_drift_min_drops: int = 3


@dataclass(frozen=True)
class LearningRunResult:
    status: str
    input_hash: str
    state_path: str
    weights_path: str
    report_path: str


def _utc_now_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utm_content(utm: str | None) -> Dict[str, Any]:
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
            except (ValueError, TypeError):
                out["version"] = tail

    return out if out else {}


def parse_utm(utm: str | None) -> Dict[str, Any]:
    return parse_utm_content(utm)


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
    except (json.JSONDecodeError, TypeError):
        return None


def _as_event_list(source: Any) -> List[Any]:
    if source is None:
        return []
    if isinstance(source, list):
        return list(source)
    try:
        return list(source)
    except TypeError as exc:
        raise LedgerReadError(f"ledger source is not iterable: {type(source).__name__}") from exc


def _iter_events(ledger_obj: Any) -> List[Any]:
    missing = object()

    for method_name in ("iter_events", "read_events", "load_events", "get_events", "list_events"):
        fn = getattr(ledger_obj, method_name, None)
        if callable(fn):
            try:
                return _as_event_list(fn())
            except LedgerReadError:
                raise
            except Exception as exc:
                raise LedgerReadError(f"ledger method '{method_name}()' failed") from exc

    for attr in ("events", "_events", "rows"):
        try:
            ev = getattr(ledger_obj, attr, missing)
        except Exception as exc:
            raise LedgerReadError(f"ledger attribute '{attr}' is unreadable") from exc
        if ev is missing:
            continue
        try:
            if callable(ev):
                return _as_event_list(ev())
            return _as_event_list(ev)
        except LedgerReadError:
            raise
        except Exception as exc:  # pragma: no cover - guarded by explicit tests below
            raise LedgerReadError(f"ledger attribute '{attr}' is unreadable") from exc

    try:
        return list(ledger_obj)
    except Exception as exc:
        raise LedgerReadError("ledger object does not expose a readable event stream") from exc


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
        return {}

    for k in ("payload", "data", "record", "event", "body"):
        try:
            v = getattr(e, k, None)
        except AttributeError:
            v = None
        except Exception as exc:
            raise PayloadExtractError(f"payload attribute access failed for '{k}'") from exc
        if isinstance(v, dict):
            return v
        parsed = _try_json_str(v)
        if isinstance(parsed, dict):
            return parsed

    try:
        d = vars(e)
    except TypeError:
        return {}
    except Exception as exc:
        raise PayloadExtractError("payload vars() inspection failed") from exc

    if isinstance(d, dict):
        if isinstance(d.get("payload"), dict):
            return d["payload"]
        if any(k in d for k in EVIDENCE_KEYS):
            return d
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


def _is_synthetic(p: Dict[str, Any]) -> bool:
    try:
        marker_raw = p.get("marker")
        marker = str(marker_raw or "").strip().upper()
        if marker.startswith("SYNTHETIC") or marker.startswith("DEMO"):
            return True

        source_raw = p.get("source")
        source = str(source_raw or "").strip().lower()
        if source in ("seed", "demo", "synthetic"):
            return True
    except Exception as exc:
        raise SyntheticCheckError("synthetic safety latch could not classify payload") from exc
    return False


def _get_spend(p: Dict[str, Any]) -> float:
    for k in ("spend", "cost", "amount_spent", "spend_total"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except (ValueError, TypeError):
                return 0.0
    return 0.0


def _get_roas(p: Dict[str, Any]) -> float:
    for k in ("roas", "roas_mean"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except (ValueError, TypeError):
                return 0.0
    return 0.0


def _get_hook_rate(p: Dict[str, Any]) -> float:
    for k in ("hook_rate_3s", "hook_rate_3s_mean"):
        if k in p:
            try:
                return float(p.get(k) or 0.0)
            except (ValueError, TypeError):
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
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _ledger_write(
    ledger_obj: Any,
    *,
    event_type: str,
    status: str,
    input_hash: str,
    total_spend: Optional[float] = None,
) -> None:
    ev: Dict[str, Any] = {
        "event_type": event_type,
        "timestamp": _utc_now_z(),
        "status": status,
        "input_hash": input_hash,
    }
    if total_spend is not None:
        ev["total_spend"] = float(total_spend)

    write_fn = getattr(ledger_obj, "write", None)
    if callable(write_fn):
        try:
            write_fn(ev)
            return
        except TypeError:
            try:
                write_fn(event_type, "learning_loop", input_hash, ev)
                return
            except TypeError:
                pass
        except Exception as exc:
            raise LedgerWriteError("ledger write() failed") from exc

    for method_name in ("write_event", "emit", "record", "add_event"):
        fn = getattr(ledger_obj, method_name, None)
        if callable(fn):
            try:
                fn(ev)
                return
            except TypeError:
                pass
            except Exception as exc:
                raise LedgerWriteError(f"ledger {method_name}() failed") from exc

    raise LedgerWriteError("ledger does not expose a supported write contract")


def _build_paths(repo: Path) -> Tuple[Path, Path, Path]:
    state_abs = repo / STATE_REL
    report_abs = repo / REPORT_REL
    weights_abs = repo / WEIGHTS_REL
    state_abs.parent.mkdir(parents=True, exist_ok=True)
    report_abs.parent.mkdir(parents=True, exist_ok=True)
    weights_abs.parent.mkdir(parents=True, exist_ok=True)
    return state_abs, report_abs, weights_abs


def _with_common_fields(base: Dict[str, Any], *, status: str, input_hash: str, records_seen: int, records_used: int) -> Dict[str, Any]:
    out = dict(base)
    out.update(
        {
            "marker": __LL_MARKER__,
            "generated_at": _utc_now_z(),
            "status": status,
            "input_hash": input_hash,
            "records_seen": int(records_seen),
            "records_used": int(records_used),
        }
    )
    return out


class LearningLoop:
    def __init__(self, repo: Path | str | None = None):
        self.repo = Path(repo) if repo is not None else Path.cwd()

    def _finalize(
        self,
        *,
        ledger_obj: Any,
        state_abs: Path,
        report_abs: Path,
        weights_abs: Path,
        status: str,
        input_hash: str,
        event_type: str,
        state_payload: Dict[str, Any],
        report_payload: Dict[str, Any],
        total_spend: Optional[float],
    ) -> LearningRunResult:
        _write_json(state_abs, state_payload)
        _write_json(report_abs, report_payload)

        try:
            _ledger_write(
                ledger_obj,
                event_type=event_type,
                status=status,
                input_hash=input_hash,
                total_spend=total_spend,
            )
            return LearningRunResult(status, input_hash, str(state_abs), str(weights_abs), str(report_abs))
        except LedgerWriteError as exc:
            failed_status = STATUS_LEARNING_LOOP_LEDGER_FAILED
            failed_state = dict(state_payload)
            failed_report = dict(report_payload)
            failed_state.update(
                {
                    "status": failed_status,
                    "intended_status": status,
                    "ledger_write_error": str(exc),
                    "ledger_write_error_type": type(exc).__name__,
                }
            )
            failed_report.update(
                {
                    "status": failed_status,
                    "intended_status": status,
                    "ledger_write_error": str(exc),
                    "ledger_write_error_type": type(exc).__name__,
                    "ledger_event_type": event_type,
                }
            )
            _write_json(state_abs, failed_state)
            _write_json(report_abs, failed_report)
            return LearningRunResult(failed_status, input_hash, str(state_abs), str(weights_abs), str(report_abs))

    def run(
        self,
        ledger_obj: Any,
        cfg: LearningLoopConfig = LearningLoopConfig(),
        force: bool = False,
        dry_run: bool = False,
    ) -> LearningRunResult:
        state_abs, report_abs, weights_abs = _build_paths(self.repo)

        try:
            events = _iter_events(ledger_obj)
        except LedgerReadError as exc:
            input_hash = _hash_payloads([])
            status = STATUS_LEDGER_UNREADABLE
            state_payload = _with_common_fields({}, status=status, input_hash=input_hash, records_seen=0, records_used=0)
            state_payload["ledger_read_error"] = str(exc)
            state_payload["ledger_read_error_type"] = type(exc).__name__

            report_payload = _with_common_fields({}, status=status, input_hash=input_hash, records_seen=0, records_used=0)
            report_payload.update(
                {
                    "total_spend": 0.0,
                    "ledger_read_error": str(exc),
                    "ledger_read_error_type": type(exc).__name__,
                }
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_SKIPPED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=0.0,
            )

        payload_candidates_total = len(events)
        payloads_all: List[Dict[str, Any]] = []
        payloads_dropped_by_shape = 0
        payload_extract_errors = 0

        for event in events:
            try:
                payload = _extract_payload(event)
            except PayloadExtractError:
                payload_extract_errors += 1
                payloads_dropped_by_shape += 1
                continue
            if isinstance(payload, dict) and payload:
                payloads_all.append(payload)
            else:
                payloads_dropped_by_shape += 1

        payload_shape_drift_ratio = 0.0
        if payload_candidates_total > 0:
            payload_shape_drift_ratio = payloads_dropped_by_shape / payload_candidates_total

        if (
            payloads_dropped_by_shape >= int(cfg.payload_shape_drift_min_drops)
            and payload_shape_drift_ratio >= float(cfg.payload_shape_drift_ratio_threshold)
        ):
            input_hash = _hash_payloads([])
            status = STATUS_PAYLOAD_SHAPE_DRIFT
            state_payload = _with_common_fields(
                {
                    "payload_candidates_total": int(payload_candidates_total),
                    "payloads_extracted_ok": int(len(payloads_all)),
                    "payloads_dropped_by_shape": int(payloads_dropped_by_shape),
                    "payload_extract_errors": int(payload_extract_errors),
                    "payload_shape_drift_ratio": float(payload_shape_drift_ratio),
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=0,
            )
            report_payload = _with_common_fields(
                {
                    "payload_candidates_total": int(payload_candidates_total),
                    "payloads_extracted_ok": int(len(payloads_all)),
                    "payloads_dropped_by_shape": int(payloads_dropped_by_shape),
                    "payload_extract_errors": int(payload_extract_errors),
                    "payload_shape_drift_ratio": float(payload_shape_drift_ratio),
                    "payload_shape_drift_ratio_threshold": float(cfg.payload_shape_drift_ratio_threshold),
                    "payload_shape_drift_min_drops": int(cfg.payload_shape_drift_min_drops),
                    "total_spend": 0.0,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=0,
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_SKIPPED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=0.0,
            )

        non_synthetic_payloads: List[Dict[str, Any]] = []
        synthetic_payloads_filtered = 0
        synthetic_check_errors = 0
        for payload in payloads_all:
            try:
                if _is_synthetic(payload):
                    synthetic_payloads_filtered += 1
                    continue
            except SyntheticCheckError:
                synthetic_check_errors += 1
                continue
            non_synthetic_payloads.append(payload)

        payloads_used = non_synthetic_payloads
        if cfg.require_evidence:
            payloads_used = [p for p in non_synthetic_payloads if _has_evidence(p)]

        input_hash = _hash_payloads(payloads_used)
        common_metrics = {
            "payload_candidates_total": int(payload_candidates_total),
            "payloads_extracted_ok": int(len(payloads_all)),
            "payloads_dropped_by_shape": int(payloads_dropped_by_shape),
            "payload_extract_errors": int(payload_extract_errors),
            "payload_shape_drift_ratio": float(payload_shape_drift_ratio),
            "synthetic_payloads_filtered": int(synthetic_payloads_filtered),
            "synthetic_check_errors": int(synthetic_check_errors),
        }

        if (not force) and state_abs.exists():
            prev = _read_json_dict(state_abs)
            if prev.get("input_hash") == input_hash and prev.get("status") in (
                STATUS_COMPLETED,
                STATUS_COMPLETED_DRY_RUN,
                STATUS_SKIPPED,
            ):
                status = STATUS_SKIPPED
                state_payload = _with_common_fields(
                    {
                        **common_metrics,
                        "reason": "IDEMPOTENT_SKIP",
                    },
                    status=status,
                    input_hash=input_hash,
                    records_seen=len(events),
                    records_used=int(prev.get("records_used", 0) or 0),
                )
                report_payload = _with_common_fields(
                    {
                        **common_metrics,
                        "reason": "IDEMPOTENT_SKIP",
                        "total_spend": 0.0,
                    },
                    status=status,
                    input_hash=input_hash,
                    records_seen=len(events),
                    records_used=int(prev.get("records_used", 0) or 0),
                )
                return self._finalize(
                    ledger_obj=ledger_obj,
                    state_abs=state_abs,
                    report_abs=report_abs,
                    weights_abs=weights_abs,
                    status=status,
                    input_hash=input_hash,
                    event_type=EV_SKIPPED,
                    state_payload=state_payload,
                    report_payload=report_payload,
                    total_spend=0.0,
                )

        if cfg.require_evidence and len(payloads_used) < int(cfg.min_records):
            status = STATUS_INSUFFICIENT_EVIDENCE
            state_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_records": int(cfg.min_records),
                    "require_evidence": True,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=len(payloads_used),
            )
            report_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_records": int(cfg.min_records),
                    "require_evidence": True,
                    "total_spend": 0.0,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=len(payloads_used),
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_SKIPPED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=0.0,
            )

        if (not cfg.require_evidence) and len(events) < int(cfg.min_records):
            status = STATUS_INSUFFICIENT_RECORDS
            state_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_records": int(cfg.min_records),
                    "require_evidence": False,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=0,
            )
            report_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_records": int(cfg.min_records),
                    "require_evidence": False,
                    "total_spend": 0.0,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=0,
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_SKIPPED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=0.0,
            )

        total_spend = sum(_get_spend(p) for p in payloads_used)
        if float(total_spend) < float(cfg.min_spend_before_learn):
            status = STATUS_INSUFFICIENT_SPEND
            state_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_spend_before_learn": float(cfg.min_spend_before_learn),
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=len(payloads_used),
            )
            report_payload = _with_common_fields(
                {
                    **common_metrics,
                    "min_spend_before_learn": float(cfg.min_spend_before_learn),
                    "total_spend": float(total_spend),
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=len(payloads_used),
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_SKIPPED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=float(total_spend),
            )

        if dry_run:
            status = STATUS_COMPLETED_DRY_RUN
            state_payload = _with_common_fields(common_metrics, status=status, input_hash=input_hash, records_seen=len(events), records_used=len(payloads_used))
            report_payload = _with_common_fields(
                {
                    **common_metrics,
                    "total_spend": float(total_spend),
                    "dry_run": True,
                },
                status=status,
                input_hash=input_hash,
                records_seen=len(events),
                records_used=len(payloads_used),
            )
            return self._finalize(
                ledger_obj=ledger_obj,
                state_abs=state_abs,
                report_abs=report_abs,
                weights_abs=weights_abs,
                status=status,
                input_hash=input_hash,
                event_type=EV_COMPLETED,
                state_payload=state_payload,
                report_payload=report_payload,
                total_spend=float(total_spend),
            )

        roas_vals = [_get_roas(p) for p in payloads_used]
        hook_vals = [_get_hook_rate(p) for p in payloads_used]
        roas_mean = (sum(roas_vals) / len(roas_vals)) if roas_vals else 0.0
        hook_mean = (sum(hook_vals) / len(hook_vals)) if hook_vals else 0.0

        angles: Dict[str, Dict[str, float]] = {}
        formats: Dict[str, Dict[str, float]] = {}
        hooks: Dict[str, Dict[str, float]] = {}

        def _acc(bucket: Dict[str, Dict[str, float]], key: str, spend: float, roas: float, hookr: float) -> None:
            b = bucket.setdefault(
                key,
                {
                    "count": 0.0,
                    "spend": 0.0,
                    "roas_sum": 0.0,
                    "roas_n": 0.0,
                    "hook_sum": 0.0,
                    "hook_n": 0.0,
                },
            )
            b["count"] += 1.0
            b["spend"] += float(spend)
            b["roas_sum"] += float(roas)
            b["roas_n"] += 1.0
            b["hook_sum"] += float(hookr)
            b["hook_n"] += 1.0

        for p in payloads_used:
            angle, fmt, hook = _classify(p)
            _acc(angles, angle, _get_spend(p), _get_roas(p), _get_hook_rate(p))
            _acc(formats, fmt, _get_spend(p), _get_roas(p), _get_hook_rate(p))
            _acc(hooks, hook, _get_spend(p), _get_roas(p), _get_hook_rate(p))

        def _finalize_bucket(raw: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for key, bucket in raw.items():
                roas_bucket_mean = (bucket["roas_sum"] / bucket["roas_n"]) if bucket["roas_n"] else 0.0
                hook_bucket_mean = (bucket["hook_sum"] / bucket["hook_n"]) if bucket["hook_n"] else 0.0
                out[key] = {
                    "count": int(bucket["count"]),
                    "spend": float(bucket["spend"]),
                    "roas_mean": float(roas_bucket_mean),
                    "hook_rate_3s_mean": float(hook_bucket_mean),
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
            "angles": _finalize_bucket(angles),
            "formats": _finalize_bucket(formats),
            "hooks": _finalize_bucket(hooks),
        }
        _write_json(weights_abs, weights_obj)

        status = STATUS_COMPLETED
        state_payload = _with_common_fields(common_metrics, status=status, input_hash=input_hash, records_seen=len(events), records_used=len(payloads_used))
        report_payload = _with_common_fields(
            {
                **common_metrics,
                "total_spend": float(total_spend),
                "dry_run": False,
            },
            status=status,
            input_hash=input_hash,
            records_seen=len(events),
            records_used=len(payloads_used),
        )
        return self._finalize(
            ledger_obj=ledger_obj,
            state_abs=state_abs,
            report_abs=report_abs,
            weights_abs=weights_abs,
            status=status,
            input_hash=input_hash,
            event_type=EV_COMPLETED,
            state_payload=state_payload,
            report_payload=report_payload,
            total_spend=float(total_spend),
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate the CLI contract lazily to the canonical learning runner."""
    from synapse.runner import main as runner_main

    rc = runner_main(argv)
    return rc if isinstance(rc, int) else 3


__all__ = [
    "__LL_MARKER__",
    "STATUS_COMPLETED",
    "STATUS_COMPLETED_DRY_RUN",
    "STATUS_SKIPPED",
    "STATUS_INSUFFICIENT_EVIDENCE",
    "STATUS_INSUFFICIENT_SPEND",
    "STATUS_INSUFFICIENT_RECORDS",
    "STATUS_LEDGER_UNREADABLE",
    "STATUS_PAYLOAD_SHAPE_DRIFT",
    "STATUS_LEARNING_LOOP_LEDGER_FAILED",
    "LearningLoopError",
    "LedgerReadError",
    "LedgerWriteError",
    "PayloadExtractError",
    "SyntheticCheckError",
    "parse_utm_content",
    "parse_utm",
    "LearningLoop",
    "LearningLoopConfig",
    "LearningRunResult",
    "main",
]

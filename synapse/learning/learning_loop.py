# synapse/learning/learning_loop.py
"""
Learning Loop (OLEADA 12)
========================

HOTFIX 12C:
- Soporta LedgerEvent (objetos) además de dicts: _event_to_dict()
- Evita runpy warning moviendo imports fuera de synapse.learning.__init__

Objetivo:
- Convertir SYNAPSE en sistema adaptativo: aprende de resultados reales y ajusta pesos.

Inputs:
- Ledger NDJSON (preferido via synapse.infra.ledger.Ledger si existe)
- O bien: carpeta data/ledger/*.ndjson

Outputs:
- data/config/learning_weights.json (pesos/priors para CreativeFactory/ExperimentEngine)
- data/learning/learning_report_latest.md (reporte ejecutivo)
- data/learning/learning_state.json (idempotencia por input_hash)
- Ledger event: LEARNING_LOOP_COMPLETED / SKIPPED / INSUFFICIENT_EVIDENCE

Reglas:
- Idempotente: si el hash de entrada no cambia => no modifica pesos.
- Bounded updates: evita “volverte loco” por 1 día de data mala.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
from dataclasses import dataclass, asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Models
# -----------------------------

@dataclass(frozen=True)
class PerformanceRecord:
    product_id: str
    creative_id: str
    angle: str = ""
    format: str = ""
    hook_id: str = ""
    platform: str = ""
    spend: float = 0.0
    impressions: float = 0.0
    clicks: float = 0.0
    conversions: float = 0.0
    cpa: float = float("inf")
    roas: float = 0.0
    ctr: float = 0.0
    cvr: float = 0.0
    hook_rate_3s: float = 0.0
    ts: str = ""  # best-effort

    @property
    def has_signal(self) -> bool:
        return (self.spend > 0.0) or (self.impressions > 0.0) or (self.clicks > 0.0)


@dataclass
class LearningLoopConfig:
    lookback_days: int = 7
    min_spend_before_learn: float = 15.0
    min_records: int = 8
    learning_rate: float = 0.15
    clamp_min: float = 0.60
    clamp_max: float = 1.60
    require_evidence: bool = True


@dataclass
class LearningRunResult:
    status: str  # COMPLETED | COMPLETED_DRY_RUN | SKIPPED | INSUFFICIENT_EVIDENCE
    input_hash: str
    records_used: int
    winners: Dict[str, List[Tuple[str, float]]]
    weights_path: str
    report_path: str
    state_path: str


# -----------------------------
# UTM parsing helper
# -----------------------------

_UTM_RE = re.compile(r"(?:^|[_\-])H(?P<hook>[^_]+).*?(?:^|[_\-])A(?P<angle>[^_]+).*?(?:^|[_\-])F(?P<fmt>[^_]+)", re.IGNORECASE)

def parse_utm_content(utm_content: str) -> Dict[str, str]:
    if not utm_content:
        return {}
    m = _UTM_RE.search(utm_content)
    if not m:
        return {}
    return {
        "hook_id": (m.group("hook") or "").strip(),
        "angle": (m.group("angle") or "").strip(),
        "format": (m.group("fmt") or "").strip(),
    }


# -----------------------------
# Adapter: LedgerEvent -> dict
# -----------------------------

def _event_to_dict(ev: Any) -> Dict[str, Any]:
    """
    Soporta:
    - dict
    - dataclass (LedgerEvent)
    - objetos con .to_dict()
    - objetos con atributos (timestamp, event_type, entity_type, entity_id, payload)
    """
    if ev is None:
        return {}
    if isinstance(ev, dict):
        return ev
    if hasattr(ev, "to_dict") and callable(getattr(ev, "to_dict")):
        try:
            out = ev.to_dict()
            return out if isinstance(out, dict) else dict(out)
        except Exception:
            pass
    if is_dataclass(ev):
        try:
            return asdict(ev)
        except Exception:
            pass
    if hasattr(ev, "__dict__"):
        try:
            d = dict(ev.__dict__)
            if d:
                return d
        except Exception:
            pass

    # fallback: map atributos comunes
    out: Dict[str, Any] = {}
    for k in ("timestamp", "ts", "event_type", "entity_type", "entity_id", "payload", "wave_id"):
        try:
            out[k] = getattr(ev, k)
        except Exception:
            pass
    return out


# -----------------------------
# IO helpers (ledger)
# -----------------------------

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return default
        return float(x)
    except Exception:
        return default


def _now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def _list_ledger_files(ledger_dir: Path) -> List[Path]:
    if not ledger_dir.exists():
        return []
    return sorted([p for p in ledger_dir.glob("*.ndjson") if p.is_file()])


def _get_events_from_ledger_dir(ledger_dir: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for f in _list_ledger_files(ledger_dir):
        events.extend(_read_ndjson(f))
    return events


def _get_events_from_ledger_obj(ledger_obj: Any) -> List[Dict[str, Any]]:
    if ledger_obj is None:
        return []

    if hasattr(ledger_obj, "query"):
        try:
            out = ledger_obj.query()
            return [_event_to_dict(e) for e in (list(out) if out is not None else [])]
        except Exception:
            pass

    if hasattr(ledger_obj, "read_all"):
        try:
            out = ledger_obj.read_all()
            return [_event_to_dict(e) for e in (list(out) if out is not None else [])]
        except Exception:
            pass

    if hasattr(ledger_obj, "iter_events"):
        try:
            out = ledger_obj.iter_events()
            return [_event_to_dict(e) for e in list(out)]
        except Exception:
            pass

    return []


def _ledger_write_best_effort(ledger_obj: Any, event_type: str, entity_type: str, entity_id: str, payload: Dict[str, Any]) -> None:
    if ledger_obj is None:
        return
    if hasattr(ledger_obj, "write"):
        try:
            ledger_obj.write(event_type=event_type, entity_type=entity_type, entity_id=entity_id, payload=payload)
            return
        except Exception:
            return
    if hasattr(ledger_obj, "log"):
        try:
            ledger_obj.log(event_type=event_type, entity_type=entity_type, entity_id=entity_id, payload=payload)
        except Exception:
            return


def _compute_input_hash(events: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for ev in events:
        ev = _event_to_dict(ev)
        core = {
            "ts": ev.get("timestamp") or ev.get("ts") or "",
            "event_type": ev.get("event_type") or "",
            "entity_type": ev.get("entity_type") or "",
            "entity_id": ev.get("entity_id") or "",
            "payload": ev.get("payload") or {},
        }
        blob = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
        h.update(blob)
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


# -----------------------------
# Extraction: events -> PerformanceRecord
# -----------------------------

def _extract_records(events: List[Dict[str, Any]]) -> List[PerformanceRecord]:
    out: List[PerformanceRecord] = []

    for raw in events:
        ev = _event_to_dict(raw)
        payload = ev.get("payload") or {}
        event_type = (ev.get("event_type") or "").upper()

        spend = _safe_float(payload.get("spend", payload.get("spend_usd", 0.0)))
        impressions = _safe_float(payload.get("impressions", 0.0))
        clicks = _safe_float(payload.get("clicks", 0.0))
        conversions = _safe_float(payload.get("conversions", payload.get("purchases", 0.0)))
        cpa = payload.get("cpa", payload.get("cpa_usd", None))
        roas = _safe_float(payload.get("roas", 0.0))
        ctr = payload.get("ctr", None)
        cvr = payload.get("cvr", None)
        hook_rate = payload.get("hook_rate_3s", payload.get("hook_rate", 0.0))

        impressions_safe = impressions if impressions > 0 else 0.0
        clicks_safe = clicks if clicks > 0 else 0.0
        conversions_safe = conversions if conversions > 0 else 0.0

        derived_ctr = (clicks_safe / impressions_safe * 100.0) if impressions_safe else 0.0
        derived_cvr = (conversions_safe / clicks_safe * 100.0) if clicks_safe else 0.0
        derived_cpa = (spend / conversions_safe) if conversions_safe else float("inf")

        ctr_v = _safe_float(ctr, derived_ctr)
        cvr_v = _safe_float(cvr, derived_cvr)
        cpa_v = _safe_float(cpa, derived_cpa) if cpa is not None else derived_cpa

        creative_id = str(payload.get("creative_id") or payload.get("ad_id") or payload.get("utm_content") or payload.get("content_id") or "").strip()
        utm = parse_utm_content(str(payload.get("utm_content") or ""))

        angle = str(payload.get("angle") or utm.get("angle") or "").strip()
        fmt = str(payload.get("format") or utm.get("format") or payload.get("creative_format") or "").strip()
        hook_id = str(payload.get("hook_id") or utm.get("hook_id") or "").strip()

        product_id = str(payload.get("product_id") or ev.get("entity_id") or "").strip()
        platform = str(payload.get("platform") or payload.get("source") or "").strip()

        has_any_metric = any([
            spend > 0, impressions > 0, clicks > 0, conversions > 0,
            roas > 0, (_safe_float(hook_rate) > 0)
        ])
        if not creative_id and not has_any_metric:
            continue

        if not product_id:
            product_id = "UNKNOWN_PRODUCT"

        ts = str(ev.get("timestamp") or ev.get("ts") or "")
        if not ts:
            ts = _now_iso()

        if event_type and ("METRIC" in event_type or "PERFORMANCE" in event_type or "EXPERIMENT" in event_type):
            pass

        out.append(PerformanceRecord(
            product_id=product_id,
            creative_id=creative_id or f"{product_id}:{len(out)}",
            angle=angle,
            format=fmt,
            hook_id=hook_id,
            platform=platform,
            spend=spend,
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            cpa=cpa_v,
            roas=roas,
            ctr=ctr_v,
            cvr=cvr_v,
            hook_rate_3s=_safe_float(hook_rate, 0.0),
            ts=ts,
        ))

    return out


# -----------------------------
# Scoring + learning
# -----------------------------

def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def _normalize(val: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (val - lo) / (hi - lo)))


def _score_records(records: List[PerformanceRecord]) -> List[Tuple[PerformanceRecord, float]]:
    roas_vals = sorted([r.roas for r in records if r.roas is not None])
    ctr_vals = sorted([r.ctr for r in records])
    hook_vals = sorted([r.hook_rate_3s for r in records])
    cpa_vals = sorted([r.cpa for r in records if math.isfinite(r.cpa)])

    roas_lo, roas_hi = _percentile(roas_vals, 10), _percentile(roas_vals, 90)
    ctr_lo, ctr_hi = _percentile(ctr_vals, 10), _percentile(ctr_vals, 90)
    hook_lo, hook_hi = _percentile(hook_vals, 10), _percentile(hook_vals, 90)
    cpa_lo, cpa_hi = _percentile(cpa_vals, 10), _percentile(cpa_vals, 90)

    scored: List[Tuple[PerformanceRecord, float]] = []
    for r in records:
        roas_n = _normalize(r.roas, roas_lo, roas_hi) if roas_vals else 0.0
        ctr_n = _normalize(r.ctr, ctr_lo, ctr_hi) if ctr_vals else 0.0
        hook_n = _normalize(r.hook_rate_3s, hook_lo, hook_hi) if hook_vals else 0.0

        if math.isfinite(r.cpa) and cpa_vals:
            cpa_n = _normalize(r.cpa, cpa_lo, cpa_hi)
            cpa_good = 1.0 - cpa_n
        else:
            cpa_good = 0.0

        score = (0.40 * roas_n) + (0.25 * cpa_good) + (0.20 * ctr_n) + (0.15 * hook_n)
        if r.conversions and r.conversions > 0:
            score = min(1.0, score + 0.05)

        scored.append((r, float(score)))

    return scored


def _aggregate_winners(scored: List[Tuple[PerformanceRecord, float]], top_k: int = 5) -> Dict[str, List[Tuple[str, float]]]:
    dims = {
        "angles": lambda r: r.angle.strip(),
        "formats": lambda r: r.format.strip(),
        "hooks": lambda r: r.hook_id.strip(),
    }

    winners: Dict[str, List[Tuple[str, float]]] = {}
    for dim_name, key_fn in dims.items():
        bucket: Dict[str, Tuple[float, float]] = {}
        for rec, sc in scored:
            k = key_fn(rec)
            if not k:
                continue
            w = rec.spend if rec.spend > 0 else 1.0
            s, sw = bucket.get(k, (0.0, 0.0))
            bucket[k] = (s + sc * w, sw + w)

        ranked = [(k, (s / sw if sw else 0.0)) for k, (s, sw) in bucket.items()]
        ranked.sort(key=lambda x: x[1], reverse=True)
        winners[dim_name] = ranked[:top_k]

    return winners


def _load_weights(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "1.0.0",
            "generated_at": "",
            "angles": {},
            "formats": {},
            "hooks": {},
            "meta": {"note": "auto-created"},
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema_version", "1.0.0")
    data.setdefault("angles", {})
    data.setdefault("formats", {})
    data.setdefault("hooks", {})
    data.setdefault("meta", {})
    return data


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _update_dimension_weights(current: Dict[str, float], ranked: List[Tuple[str, float]], lr: float, lo: float, hi: float) -> Dict[str, float]:
    out = dict(current or {})
    for key, sc in ranked:
        if not key:
            continue
        old = float(out.get(key, 1.0))
        target = 0.85 + (0.30 * float(sc))
        newv = (1.0 - lr) * old + lr * target
        out[key] = float(_clamp(newv, lo, hi))
    return out


def _render_report_md(result: LearningRunResult, winners: Dict[str, List[Tuple[str, float]]]) -> str:
    lines: List[str] = []
    lines.append("# SYNAPSE — Learning Loop Report (latest)")
    lines.append("")
    lines.append(f"- status: **{result.status}**")
    lines.append(f"- input_hash: `{result.input_hash}`")
    lines.append(f"- records_used: **{result.records_used}**")
    lines.append("")
    lines.append("## Winners (top)")
    for dim, vals in winners.items():
        lines.append(f"### {dim}")
        if not vals:
            lines.append("- (sin data suficiente)")
            continue
        for k, sc in vals:
            lines.append(f"- **{k}** — score={sc:.3f}")
        lines.append("")
    lines.append("## Nota")
    lines.append("- Ajuste incremental bounded. No es “profecía”, es steering.")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


# -----------------------------
# Main orchestrator
# -----------------------------

class LearningLoop:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(
        self,
        *,
        ledger_obj: Any = None,
        ledger_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        config_dir: Optional[Path] = None,
        cfg: Optional[LearningLoopConfig] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> LearningRunResult:
        cfg = cfg or LearningLoopConfig()

        ledger_dir = ledger_dir or (self.repo_root / "data" / "ledger")
        output_dir = output_dir or (self.repo_root / "data" / "learning")
        config_dir = config_dir or (self.repo_root / "data" / "config")
        output_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)

        events = _get_events_from_ledger_obj(ledger_obj)
        if not events:
            events = _get_events_from_ledger_dir(ledger_dir)

        # Lookback filter (best-effort)
        cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=int(cfg.lookback_days))
        filtered: List[Dict[str, Any]] = []
        for raw in events:
            ev = _event_to_dict(raw)
            ts = str(ev.get("timestamp") or ev.get("ts") or "")
            if not ts:
                filtered.append(ev)
                continue
            try:
                ts2 = ts.replace("Z", "+00:00")
                dt = _dt.datetime.fromisoformat(ts2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_dt.timezone.utc)
                if dt >= cutoff.replace(tzinfo=_dt.timezone.utc):
                    filtered.append(ev)
            except Exception:
                filtered.append(ev)

        input_hash = _compute_input_hash(filtered)

        state_path = output_dir / "learning_state.json"
        prev = {}
        if state_path.exists():
            try:
                prev = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}

        if (not force) and prev.get("input_hash") == input_hash:
            res = LearningRunResult(
                status="SKIPPED",
                input_hash=input_hash,
                records_used=int(prev.get("records_used", 0)),
                winners=prev.get("winners", {}),
                weights_path=str(config_dir / "learning_weights.json"),
                report_path=str(output_dir / "learning_report_latest.md"),
                state_path=str(state_path),
            )
            _ledger_write_best_effort(
                ledger_obj,
                event_type="LEARNING_LOOP_SKIPPED",
                entity_type="system",
                entity_id="learning_loop",
                payload={"input_hash": input_hash, "reason": "same_input_hash"},
            )
            return res

        records = _extract_records(filtered)
        records = [r for r in records if r.has_signal]

        if len(records) < int(cfg.min_records):
            res = LearningRunResult(
                status="INSUFFICIENT_EVIDENCE",
                input_hash=input_hash,
                records_used=len(records),
                winners={},
                weights_path=str(config_dir / "learning_weights.json"),
                report_path=str(output_dir / "learning_report_latest.md"),
                state_path=str(state_path),
            )
            report_txt = _render_report_md(res, {})
            (output_dir / "learning_report_latest.md").write_text(report_txt, encoding="utf-8")
            state_path.write_text(json.dumps({
                "input_hash": input_hash,
                "generated_at": _now_iso(),
                "records_used": len(records),
                "winners": {},
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            _ledger_write_best_effort(
                ledger_obj,
                event_type="LEARNING_LOOP_INSUFFICIENT_EVIDENCE",
                entity_type="system",
                entity_id="learning_loop",
                payload={"input_hash": input_hash, "records_used": len(records)},
            )
            return res

        total_spend = sum([r.spend for r in records])
        if total_spend < float(cfg.min_spend_before_learn):
            res = LearningRunResult(
                status="INSUFFICIENT_EVIDENCE",
                input_hash=input_hash,
                records_used=len(records),
                winners={},
                weights_path=str(config_dir / "learning_weights.json"),
                report_path=str(output_dir / "learning_report_latest.md"),
                state_path=str(state_path),
            )
            report_txt = _render_report_md(res, {})
            (output_dir / "learning_report_latest.md").write_text(report_txt, encoding="utf-8")
            state_path.write_text(json.dumps({
                "input_hash": input_hash,
                "generated_at": _now_iso(),
                "records_used": len(records),
                "winners": {},
                "note": f"total_spend<{cfg.min_spend_before_learn}",
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            _ledger_write_best_effort(
                ledger_obj,
                event_type="LEARNING_LOOP_INSUFFICIENT_EVIDENCE",
                entity_type="system",
                entity_id="learning_loop",
                payload={"input_hash": input_hash, "records_used": len(records), "total_spend": total_spend},
            )
            return res

        scored = _score_records(records)
        winners = _aggregate_winners(scored, top_k=5)

        weights_path = config_dir / "learning_weights.json"
        current = _load_weights(weights_path)

        updated_angles = _update_dimension_weights(current.get("angles", {}) or {}, winners.get("angles", []), cfg.learning_rate, cfg.clamp_min, cfg.clamp_max)
        updated_formats = _update_dimension_weights(current.get("formats", {}) or {}, winners.get("formats", []), cfg.learning_rate, cfg.clamp_min, cfg.clamp_max)
        updated_hooks = _update_dimension_weights(current.get("hooks", {}) or {}, winners.get("hooks", []), cfg.learning_rate, cfg.clamp_min, cfg.clamp_max)

        new_weights = {
            "schema_version": "1.0.0",
            "generated_at": _now_iso(),
            "input_hash": input_hash,
            "angles": updated_angles,
            "formats": updated_formats,
            "hooks": updated_hooks,
            "meta": {
                "lookback_days": cfg.lookback_days,
                "min_spend_before_learn": cfg.min_spend_before_learn,
                "records_used": len(records),
                "total_spend": total_spend,
            },
        }

        report_res = LearningRunResult(
            status="COMPLETED" if not dry_run else "COMPLETED_DRY_RUN",
            input_hash=input_hash,
            records_used=len(records),
            winners=winners,
            weights_path=str(weights_path),
            report_path=str(output_dir / "learning_report_latest.md"),
            state_path=str(state_path),
        )

        report_txt = _render_report_md(report_res, winners)

        if not dry_run:
            weights_path.write_text(json.dumps(new_weights, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "learning_report_latest.md").write_text(report_txt, encoding="utf-8")

        state_payload = {
            "input_hash": input_hash,
            "generated_at": _now_iso(),
            "records_used": len(records),
            "winners": winners,
            "weights_path": str(weights_path),
            "report_path": str(output_dir / "learning_report_latest.md"),
        }
        state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        _ledger_write_best_effort(
            ledger_obj,
            event_type="LEARNING_LOOP_COMPLETED",
            entity_type="system",
            entity_id="learning_loop",
            payload={
                "input_hash": input_hash,
                "records_used": len(records),
                "total_spend": total_spend,
                "weights_path": str(weights_path),
                "report_path": str(output_dir / "learning_report_latest.md"),
                "dry_run": dry_run,
            },
        )

        return report_res


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".", help="Path raíz del repo (default: .)")
    p.add_argument("--ledger-dir", default="", help="Override: carpeta data/ledger")
    p.add_argument("--out-dir", default="", help="Override: carpeta data/learning")
    p.add_argument("--config-dir", default="", help="Override: carpeta data/config")
    p.add_argument("--lookback-days", type=int, default=7)
    p.add_argument("--min-spend", type=float, default=15.0)
    p.add_argument("--min-records", type=int, default=8)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ledger_dir = Path(args.ledger_dir).resolve() if args.ledger_dir else None
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    cfg_dir = Path(args.config_dir).resolve() if args.config_dir else None

    ledger_obj = None
    try:
        from synapse.infra.ledger import Ledger  # type: ignore
        if ledger_dir is None:
            ledger_dir = repo_root / "data" / "ledger"
        ledger_obj = Ledger(str(ledger_dir))
    except Exception:
        ledger_obj = None

    cfg = LearningLoopConfig(
        lookback_days=args.lookback_days,
        min_spend_before_learn=args.min_spend,
        min_records=args.min_records,
    )

    runner = LearningLoop(repo_root)
    res = runner.run(
        ledger_obj=ledger_obj,
        ledger_dir=ledger_dir,
        output_dir=out_dir,
        config_dir=cfg_dir,
        cfg=cfg,
        force=args.force,
        dry_run=args.dry_run,
    )

    print(json.dumps(asdict(res), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    from dataclasses import asdict
    raise SystemExit(_cli())

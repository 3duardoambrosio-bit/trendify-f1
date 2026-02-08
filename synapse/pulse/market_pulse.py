# synapse/pulse/market_pulse.py
"""
Market Pulse — OLEADA 13
=======================

Objetivo:
- Registrar señales del mercado MX (manuales) con evidencia obligatoria.
- CERO scraping. CERO "se rumorea". CERO numeritos sin URL.
- Output: memo JSON + reporte Markdown.
- Idempotente por input_hash. Soporta --dry-run y --force.
- Loggea eventos al Ledger si existe.

Input (JSON):
{
  "schema_version": "1.0.0",
  "signals": [
    {
      "signal_id": "trend_audio_001",
      "source_type": "google_trends|ad_library|inegi|banxico|news|other",
      "evidence_url": "https://...",
      "headline": "Búsquedas suben para ...",
      "description": "Descripción concreta. Sin humo.",
      "metric_name": "trend_index|cpm|cpc|inflation|etc",
      "metric_value": 12.3,
      "confidence": 0.7
    }
  ]
}

Reglas:
- evidence_url obligatorio y debe iniciar con http/https.
- confidence ∈ [0,1]
- Si confidence > 0.5, description/headline no puede contener: "podría", "tal vez", "se rumorea", "quizá", "chance", "dicen que".
- Si <2 señales válidas => INSUFFICIENT_EVIDENCE (no inventar).
"""

from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ---------------------------
# Models
# ---------------------------

_ALLOWED_SOURCE_TYPES = {
    "google_trends",
    "ad_library",
    "inegi",
    "banxico",
    "news",
    "other",
}

_SPECULATIVE_RE = re.compile(
    r"\b(podr[ií]a|tal\s*vez|se\s*rumorea|quiz[aá]|chance|dicen\s*que)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PulseSignal:
    signal_id: str
    source_type: str
    evidence_url: str
    headline: str
    description: str
    metric_name: str = ""
    metric_value: float = 0.0
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketPulseMemo:
    schema_version: str
    generated_at: str
    status: str  # SUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE
    input_hash: str
    signals_used: int
    signals: List[Dict[str, Any]]
    notes: List[str]


# ---------------------------
# Helpers
# ---------------------------

def _now_iso() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _sha256_json(obj: Any) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8", errors="replace")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _is_valid_http_url(u: str) -> bool:
    if not u or not isinstance(u, str):
        return False
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    try:
        p = urlparse(u)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _json_load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _md_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


# ---------------------------
# Validation
# ---------------------------

class PulseValidationError(ValueError):
    pass


def validate_signal(raw: Dict[str, Any]) -> Tuple[Optional[PulseSignal], List[str]]:
    errs: List[str] = []

    signal_id = str(raw.get("signal_id") or "").strip()
    source_type = str(raw.get("source_type") or "").strip()
    evidence_url = str(raw.get("evidence_url") or "").strip()
    headline = str(raw.get("headline") or "").strip()
    description = str(raw.get("description") or "").strip()
    metric_name = str(raw.get("metric_name") or "").strip()
    metric_value = raw.get("metric_value", 0.0)
    confidence = _clamp01(raw.get("confidence", 0.5))

    if not signal_id:
        errs.append("signal_id requerido")
    if source_type not in _ALLOWED_SOURCE_TYPES:
        errs.append(f"source_type inválido: {source_type}")
    if not _is_valid_http_url(evidence_url):
        errs.append("evidence_url inválido (requiere http/https + dominio)")
    if not headline:
        errs.append("headline requerido")
    if not description:
        errs.append("description requerido")

    # Anti-alucin: si vas a hablar con seguridad, no uses lenguaje especulativo.
    if confidence > 0.5:
        combined = f"{headline} {description}"
        if _SPECULATIVE_RE.search(combined):
            errs.append("lenguaje especulativo con confidence>0.5 (no permitido)")

    try:
        metric_value_f = float(metric_value)
    except Exception:
        metric_value_f = 0.0
        errs.append("metric_value debe ser numérico")

    if errs:
        return None, errs

    return PulseSignal(
        signal_id=signal_id,
        source_type=source_type,
        evidence_url=evidence_url,
        headline=headline,
        description=description,
        metric_name=metric_name,
        metric_value=metric_value_f,
        confidence=confidence,
    ), []


# ---------------------------
# Ledger integration (best effort)
# ---------------------------

def _get_ledger(repo_root: Path, ledger_dir: Optional[Path] = None):
    try:
        from synapse.infra.ledger import Ledger  # type: ignore
        ld = ledger_dir or (repo_root / "data" / "ledger")
        return Ledger(str(ld))
    except Exception:
        return None


def _ledger_write(ledger_obj: Any, event_type: str, payload: Dict[str, Any]) -> None:
    if ledger_obj is None:
        return
    if hasattr(ledger_obj, "write"):
        try:
            ledger_obj.write(event_type=event_type, entity_type="system", entity_id="market_pulse", payload=payload)
        except Exception:
            return


# ---------------------------
# Runner
# ---------------------------

class MarketPulseRunner:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(
        self,
        *,
        input_path: Path,
        out_dir: Optional[Path] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> MarketPulseMemo:
        out_dir = out_dir or (self.repo_root / "data" / "pulse")
        out_dir.mkdir(parents=True, exist_ok=True)

        state_path = out_dir / "market_pulse_state.json"
        memo_path = out_dir / "market_pulse_latest.json"
        report_path = out_dir / "market_pulse_latest.md"

        raw = _json_load(input_path)
        schema_version = str(raw.get("schema_version") or "1.0.0")
        raw_signals = raw.get("signals") or []
        if not isinstance(raw_signals, list):
            raise PulseValidationError("signals debe ser lista")

        # input hash (solo lo que importa)
        input_hash = _sha256_json({"schema_version": schema_version, "signals": raw_signals})

        if state_path.exists() and not force:
            prev = _json_load(state_path)
            if prev.get("input_hash") == input_hash:
                # Idempotent skip: regresamos memo anterior si existe
                if memo_path.exists():
                    m = _json_load(memo_path)
                    return MarketPulseMemo(**m)  # type: ignore
                # fallback
                return MarketPulseMemo(
                    schema_version="1.0.0",
                    generated_at=_now_iso(),
                    status="INSUFFICIENT_EVIDENCE",
                    input_hash=input_hash,
                    signals_used=0,
                    signals=[],
                    notes=["SKIPPED: same input_hash, memo missing (edge case)"],
                )

        valid: List[PulseSignal] = []
        notes: List[str] = []
        errors_accum: List[str] = []

        for i, rs in enumerate(raw_signals):
            if not isinstance(rs, dict):
                errors_accum.append(f"signal[{i}] no es objeto")
                continue
            sig, errs = validate_signal(rs)
            if errs:
                errors_accum.append(f"signal[{i}] inválida: " + "; ".join(errs))
                continue
            assert sig is not None
            valid.append(sig)

        if errors_accum:
            notes.append("Se detectaron señales inválidas (ignoradas):")
            notes.extend([f"- {e}" for e in errors_accum])

        status = "SUFFICIENT_EVIDENCE" if len(valid) >= 2 else "INSUFFICIENT_EVIDENCE"

        memo = MarketPulseMemo(
            schema_version="1.0.0",
            generated_at=_now_iso(),
            status=status,
            input_hash=input_hash,
            signals_used=len(valid),
            signals=[s.to_dict() for s in valid],
            notes=notes,
        )

        report_md = self._render_report(memo)

        # Persistencia
        if not dry_run:
            _json_write(memo_path, asdict(memo))
            _md_write(report_path, report_md)
            _json_write(state_path, {"input_hash": input_hash, "generated_at": memo.generated_at})
        else:
            _md_write(report_path, report_md)
            _json_write(state_path, {"input_hash": input_hash, "generated_at": memo.generated_at, "dry_run": True})

        # Ledger
        ledger = _get_ledger(self.repo_root)
        _ledger_write(
            ledger,
            "MARKET_PULSE_RECORDED" if status == "SUFFICIENT_EVIDENCE" else "MARKET_PULSE_INSUFFICIENT_EVIDENCE",
            {
                "input_hash": input_hash,
                "signals_used": len(valid),
                "status": status,
                "memo_path": str(memo_path),
                "report_path": str(report_path),
                "dry_run": dry_run,
            },
        )

        return memo

    def _render_report(self, memo: MarketPulseMemo) -> str:
        lines: List[str] = []
        lines.append("# Market Pulse (latest)")
        lines.append("")
        lines.append(f"- status: **{memo.status}**")
        lines.append(f"- generated_at: `{memo.generated_at}`")
        lines.append(f"- input_hash: `{memo.input_hash}`")
        lines.append(f"- signals_used: **{memo.signals_used}**")
        lines.append("")
        lines.append("## Señales")
        if not memo.signals:
            lines.append("- (sin señales válidas suficientes)")
        for s in memo.signals:
            lines.append(f"- **{s.get('headline','')}**")
            lines.append(f"  - source_type: `{s.get('source_type','')}`")
            lines.append(f"  - confidence: `{s.get('confidence',0.0)}`")
            if s.get("metric_name"):
                lines.append(f"  - metric: `{s.get('metric_name')}` = `{s.get('metric_value')}`")
            lines.append(f"  - evidencia: {s.get('evidence_url','')}")
            lines.append(f"  - detalle: {s.get('description','')}")
            lines.append("")
        if memo.notes:
            lines.append("## Notas / Validación")
            lines.extend(memo.notes)
            lines.append("")
        lines.append("## Regla de oro")
        lines.append("- Si no hay evidencia suficiente, el sistema **no inventa**. Punto.")
        return "\n".join(lines).strip() + "\n"


# ---------------------------
# CLI
# ---------------------------

def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Ruta a JSON de señales (ej: data/evidence/pulse/signals.json)")
    ap.add_argument("--out-dir", default="", help="Override output dir (default: data/pulse)")
    ap.add_argument("--force", action="store_true", help="Ignora idempotencia")
    ap.add_argument("--dry-run", action="store_true", help="No escribe memo JSON (solo report/state)")
    args = ap.parse_args()

    repo_root = Path(".").resolve()
    input_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None

    runner = MarketPulseRunner(repo_root)
    memo = runner.run(
        input_path=input_path,
        out_dir=out_dir,
        force=args.force,
        dry_run=args.dry_run,
    )
    cli_print(json.dumps(asdict(memo), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast
import hashlib
import json
from typing import Any, Dict, List


WRAP_KEYS = ("payload", "data", "record", "event", "body")
EVIDENCE_KEYS = {
    "spend", "roas", "hook_rate_3s", "clicks", "conversions", "impressions",
    "platform", "product_id", "creative_id", "utm_content", "hook_id",
}


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


class LearningLoop:
    """
    Test-driven contract:
    - Si hay >= min_records eventos y spend total >= min_spend_before_learn:
      - con require_evidence=True debe completar cuando los eventos traen payload (dict/JSON/repr).
    - dry_run=True => COMPLETED_DRY_RUN y NO escribir weights.json
    - idempotencia: mismo input_hash y ya COMPLETED/COMPLETED_DRY_RUN => NOOP
    """

    def __init__(self, repo: Path | str):
        self.repo = Path(repo)

    def _state_file(self) -> Path:
        return self.repo / "data" / "learning" / "learning_state.json"

    def _weights_file(self) -> Path:
        return self.repo / "data" / "config" / "weights.json"

    def _ensure_dirs(self) -> None:
        (self.repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
        (self.repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    def _iter_events(self, ledger_obj: Any) -> List[Any]:
        for attr in ("events", "_events"):
            if hasattr(ledger_obj, attr):
                try:
                    ev = getattr(ledger_obj, attr)
                    if callable(ev):
                        out = ev()
                        return list(out) if out is not None else []
                    return list(ev) if ev is not None else []
                except Exception:
                    pass

        for m in ("iter_events", "read_events", "load_events", "get_events"):
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

    def _parse_event_str(self, s: str) -> Any:
        ss = s.strip()
        if not ss:
            return None
        # 1) JSON real
        try:
            if ss.startswith("{") or ss.startswith("["):
                return json.loads(ss)
        except Exception:
            pass
        # 2) repr de dict con comillas simples (Python)
        try:
            if ss.startswith("{") or ss.startswith("["):
                return ast.literal_eval(ss)
        except Exception:
            return None

        return None

    def _normalize_event(self, e: Any) -> Any:
        if isinstance(e, (bytes, bytearray)):
            try:
                e = e.decode("utf-8", errors="ignore")
            except Exception:
                return e

        if isinstance(e, str):
            parsed = self._parse_event_str(e)
            return parsed if parsed is not None else e

        return e

    def _extract_payload(self, e: Any) -> Dict[str, Any]:
        e = self._normalize_event(e)

        # dict normal
        if isinstance(e, dict):
            # wrappers
            for k in WRAP_KEYS:
                if k in e:
                    v = e.get(k)
                    v = self._normalize_event(v)
                    if isinstance(v, dict):
                        return v
            # a veces viene plano
            if any(k in e for k in EVIDENCE_KEYS):
                return e
            return {}

        # objetos con attrs
        for k in WRAP_KEYS:
            try:
                v = getattr(e, k, None)
            except Exception:
                v = None
            v = self._normalize_event(v)
            if isinstance(v, dict):
                return v

        # __dict__ fallback
        try:
            d = vars(e)
            if isinstance(d, dict):
                if "payload" in d and isinstance(d["payload"], dict):
                    return d["payload"]
                if any(k in d for k in EVIDENCE_KEYS):
                    return d
        except Exception:
            pass

        return {}

    def _hash_payloads(self, payloads: List[Dict[str, Any]]) -> str:
        s = json.dumps(payloads, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()
        return f"sha256:{h}"

    def _read_state(self) -> Dict[str, Any]:
        p = self._state_file()
        if not p.exists():
            return {}
        try:
            x = json.loads(p.read_text(encoding="utf-8"))
            return x if isinstance(x, dict) else {}
        except Exception:
            return {}

    def _write_state(self, input_hash: str, status: str) -> None:
        self._state_file().write_text(
            json.dumps({"input_hash": input_hash, "status": status}, ensure_ascii=False),
            encoding="utf-8",
        )

    def run(self, *, ledger_obj: Any, cfg: LearningLoopConfig, force: bool = False, dry_run: bool = False) -> LearningRunResult:
        self._ensure_dirs()

        events = self._iter_events(ledger_obj)

        # extrae payloads (y aquí arreglamos el evidence fantasma)
        payloads: List[Dict[str, Any]] = []
        for e in events:
            p = self._extract_payload(e)
            if isinstance(p, dict) and p:
                payloads.append(p)

        input_hash = self._hash_payloads(payloads)

        # Idempotencia
        if (not force) and self._state_file().exists():
            prev = self._read_state()
            if prev.get("input_hash") == input_hash and prev.get("status") in ("COMPLETED", "COMPLETED_DRY_RUN", "NOOP"):
                self._write_state(input_hash, "NOOP")
                return LearningRunResult("NOOP", input_hash, str(self._state_file()))

        # Gates
        if len(events) < cfg.min_records:
            self._write_state(input_hash, "INSUFFICIENT_RECORDS")
            return LearningRunResult("INSUFFICIENT_RECORDS", input_hash, str(self._state_file()))

        total_spend = 0.0
        for p in payloads:
            try:
                total_spend += float(p.get("spend", 0.0))
            except Exception:
                pass

        if total_spend < cfg.min_spend_before_learn:
            self._write_state(input_hash, "INSUFFICIENT_SPEND")
            return LearningRunResult("INSUFFICIENT_SPEND", input_hash, str(self._state_file()))

        if cfg.require_evidence and len(payloads) < cfg.min_records:
            # Si esto vuelve a salir, ya NO es extractor: es que el ledger está entregando otra cosa.
            self._write_state(input_hash, "INSUFFICIENT_EVIDENCE")
            return LearningRunResult("INSUFFICIENT_EVIDENCE", input_hash, str(self._state_file()))

        if dry_run:
            self._write_state(input_hash, "COMPLETED_DRY_RUN")
            return LearningRunResult("COMPLETED_DRY_RUN", input_hash, str(self._state_file()))

        # escribe weights.json
        roas_vals: List[float] = []
        hook_vals: List[float] = []
        for p in payloads:
            if "roas" in p:
                try: roas_vals.append(float(p["roas"]))
                except Exception: pass
            if "hook_rate_3s" in p:
                try: hook_vals.append(float(p["hook_rate_3s"]))
                except Exception: pass

        def _mean(xs: List[float]) -> float:
            return (sum(xs) / len(xs)) if xs else 0.0

        weights = {
            "roas_mean": _mean(roas_vals),
            "hook_rate_3s_mean": _mean(hook_vals),
            "records": len(events),
            "payloads": len(payloads),
            "total_spend": total_spend,
        }

        self._weights_file().write_text(json.dumps(weights, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        self._write_state(input_hash, "COMPLETED")
        return LearningRunResult("COMPLETED", input_hash, str(self._state_file()))
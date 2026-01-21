# tests/pulse/test_market_pulse.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse.pulse.market_pulse import MarketPulseRunner, validate_signal


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_signal_requires_http_url():
    sig, errs = validate_signal({
        "signal_id": "x1",
        "source_type": "news",
        "evidence_url": "ftp://nope.com",
        "headline": "hola",
        "description": "desc",
        "confidence": 0.6,
    })
    assert sig is None
    assert any("evidence_url" in e for e in errs)


def test_speculative_language_blocked_when_high_confidence():
    sig, errs = validate_signal({
        "signal_id": "x2",
        "source_type": "news",
        "evidence_url": "https://example.com/a",
        "headline": "Esto podría ser grande",
        "description": "tal vez suba",
        "confidence": 0.9,
    })
    assert sig is None
    assert any("especulativo" in e.lower() for e in errs)


def test_runner_insufficient_evidence_creates_report_and_state(tmp_path: Path):
    repo = tmp_path
    inp = repo / "data" / "evidence" / "pulse" / "signals.json"
    out_dir = repo / "data" / "pulse"

    _write_json(inp, {
        "schema_version": "1.0.0",
        "signals": [
            {
                "signal_id": "s1",
                "source_type": "google_trends",
                "evidence_url": "https://example.com/trends",
                "headline": "Sube búsquedas",
                "description": "Se detecta incremento con evidencia.",
                "metric_name": "trend_index",
                "metric_value": 12.3,
                "confidence": 0.6,
            }
        ]
    })

    r = MarketPulseRunner(repo)
    memo = r.run(input_path=inp, out_dir=out_dir, force=True, dry_run=False)

    assert memo.status == "INSUFFICIENT_EVIDENCE"
    assert (out_dir / "market_pulse_latest.md").exists()
    assert (out_dir / "market_pulse_state.json").exists()


def test_runner_sufficient_evidence_writes_memo(tmp_path: Path):
    repo = tmp_path
    inp = repo / "data" / "evidence" / "pulse" / "signals.json"
    out_dir = repo / "data" / "pulse"

    _write_json(inp, {
        "schema_version": "1.0.0",
        "signals": [
            {
                "signal_id": "s1",
                "source_type": "google_trends",
                "evidence_url": "https://example.com/trends",
                "headline": "Sube búsquedas",
                "description": "Evidencia directa.",
                "metric_name": "trend_index",
                "metric_value": 12.3,
                "confidence": 0.6,
            },
            {
                "signal_id": "s2",
                "source_type": "ad_library",
                "evidence_url": "https://example.com/ads",
                "headline": "Competidor escala creatives",
                "description": "Se observa incremento de anuncios activos (ver evidencia).",
                "metric_name": "ads_count",
                "metric_value": 48,
                "confidence": 0.7,
            },
        ]
    })

    r = MarketPulseRunner(repo)
    memo = r.run(input_path=inp, out_dir=out_dir, force=True, dry_run=False)

    assert memo.status == "SUFFICIENT_EVIDENCE"
    assert memo.signals_used == 2
    assert (out_dir / "market_pulse_latest.json").exists()
    assert (out_dir / "market_pulse_latest.md").exists()


def test_idempotency_skips_when_same_input_hash(tmp_path: Path):
    repo = tmp_path
    inp = repo / "data" / "evidence" / "pulse" / "signals.json"
    out_dir = repo / "data" / "pulse"

    payload = {
        "schema_version": "1.0.0",
        "signals": [
            {
                "signal_id": "s1",
                "source_type": "news",
                "evidence_url": "https://example.com/n1",
                "headline": "Nota 1",
                "description": "Evidencia directa.",
                "confidence": 0.6,
            },
            {
                "signal_id": "s2",
                "source_type": "news",
                "evidence_url": "https://example.com/n2",
                "headline": "Nota 2",
                "description": "Evidencia directa.",
                "confidence": 0.6,
            },
        ]
    }
    _write_json(inp, payload)

    r = MarketPulseRunner(repo)
    memo1 = r.run(input_path=inp, out_dir=out_dir, force=True, dry_run=False)
    memo2 = r.run(input_path=inp, out_dir=out_dir, force=False, dry_run=False)

    assert memo2.input_hash == memo1.input_hash
    assert memo2.status == memo1.status


def test_dry_run_does_not_write_json_memo(tmp_path: Path):
    repo = tmp_path
    inp = repo / "data" / "evidence" / "pulse" / "signals.json"
    out_dir = repo / "data" / "pulse"

    _write_json(inp, {
        "schema_version": "1.0.0",
        "signals": [
            {
                "signal_id": "s1",
                "source_type": "news",
                "evidence_url": "https://example.com/n1",
                "headline": "Nota 1",
                "description": "Evidencia directa.",
                "confidence": 0.6,
            },
            {
                "signal_id": "s2",
                "source_type": "news",
                "evidence_url": "https://example.com/n2",
                "headline": "Nota 2",
                "description": "Evidencia directa.",
                "confidence": 0.6,
            },
        ]
    })

    r = MarketPulseRunner(repo)
    memo = r.run(input_path=inp, out_dir=out_dir, force=True, dry_run=True)

    assert memo.status in ("SUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE")
    assert (out_dir / "market_pulse_latest.md").exists()
    assert not (out_dir / "market_pulse_latest.json").exists()

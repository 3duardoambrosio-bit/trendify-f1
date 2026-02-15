"""Tests for synapse.cli.cockpit CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cockpit(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "synapse.cli.cockpit", *args],
        capture_output=True, text=True, timeout=30,
    )


def test_health_json_parseable():
    r = _run_cockpit("health", "--json")
    obj = json.loads(r.stdout)
    assert isinstance(obj["ok"], bool)
    assert obj["mode"] == "health"
    assert "checks" in obj
    assert "errors" in obj
    assert "ts_utc" in obj
    assert "meta" in obj


def test_flags_json_has_required_keys():
    r = _run_cockpit("flags", "--json")
    obj = json.loads(r.stdout)
    for key in ("ok", "mode", "checks", "errors"):
        assert key in obj, f"missing key: {key}"
    assert obj["mode"] == "flags"


def test_last_ledger_missing_file_degraded(tmp_path: Path):
    missing = tmp_path / "missing.ndjson"
    r = _run_cockpit("last-ledger", "--json", "--ledger-path", str(missing))
    obj = json.loads(r.stdout)
    assert obj["ok"] is True
    assert r.returncode == 2
    assert obj["checks"]["ledger"]["available"] is False


def test_last_ledger_valid_file(tmp_path: Path):
    ledger = tmp_path / "ledger.ndjson"
    event = {"event": "test", "ts": "2026-01-01T00:00:00Z"}
    ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
    r = _run_cockpit("last-ledger", "--json", "--ledger-path", str(ledger))
    obj = json.loads(r.stdout)
    assert obj["ok"] is True
    assert r.returncode == 0
    assert obj["checks"]["ledger"]["available"] is True
    assert obj["checks"]["ledger"]["last_event"] == event


def test_last_ledger_corrupt_json(tmp_path: Path):
    ledger = tmp_path / "ledger.ndjson"
    ledger.write_text("not-json\n", encoding="utf-8")
    r = _run_cockpit("last-ledger", "--json", "--ledger-path", str(ledger))
    obj = json.loads(r.stdout)
    assert obj["ok"] is True
    assert r.returncode == 2
    errors = [e["code"] for e in obj["errors"]]
    assert "ledger_parse_error" in errors


def test_budget_json_parseable():
    r = _run_cockpit("budget", "--json")
    obj = json.loads(r.stdout)
    assert obj["ok"] is True
    assert "budget" in obj["checks"]
    assert isinstance(obj["checks"]["budget"]["available"], bool)


def test_safety_json_parseable():
    r = _run_cockpit("safety", "--json")
    obj = json.loads(r.stdout)
    assert obj["ok"] is True
    assert "safety" in obj["checks"]
    assert isinstance(obj["checks"]["safety"]["available"], bool)


def test_all_json_mode():
    r = _run_cockpit("all", "--json")
    obj = json.loads(r.stdout)
    assert obj["mode"] == "all"
    assert "summary" in obj["checks"]
    assert obj["checks"]["summary"]["overall"] in ("GREEN", "YELLOW", "RED")

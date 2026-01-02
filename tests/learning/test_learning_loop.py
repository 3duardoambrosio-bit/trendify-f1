# tests/learning/test_learning_loop.py
import json
from pathlib import Path

import pytest

from synapse.learning.learning_loop import (
    LearningLoop,
    LearningLoopConfig,
    parse_utm_content,
)


class FakeLedger:
    def __init__(self, events):
        self._events = list(events)
        self.writes = []

    def query(self):
        return list(self._events)

    def write(self, event_type, entity_type, entity_id, payload):
        self.writes.append(
            {"event_type": event_type, "entity_type": entity_type, "entity_id": entity_id, "payload": payload}
        )


def _mk_event(ts, payload, event_type="EXPERIMENT_METRICS_RECORDED", entity_id="34357"):
    return {
        "timestamp": ts,
        "event_type": event_type,
        "entity_type": "product",
        "entity_id": entity_id,
        "payload": payload,
    }


def test_parse_utm_content():
    utm = "Hhook01_Astatus_Fhands_V1"
    out = parse_utm_content(utm)
    assert out["hook_id"] == "hook01"
    assert out["angle"] == "status"
    assert out["format"] == "hands"


def test_learning_loop_insufficient_evidence_writes_report(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    ledger = FakeLedger(events=[])
    cfg = LearningLoopConfig(min_records=8, require_evidence=True)

    runner = LearningLoop(repo)
    res = runner.run(ledger_obj=ledger, cfg=cfg)

    assert res.status == "INSUFFICIENT_EVIDENCE"
    report_path = Path(res.report_path)
    assert report_path.exists()
    txt = report_path.read_text(encoding="utf-8")
    assert "INSUFFICIENT_EVIDENCE" in txt


def test_learning_loop_updates_weights_and_is_idempotent(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    events = []
    # enough spend + multiple records
    for i in range(10):
        payload = {
            "product_id": "34357",
            "platform": "meta",
            "utm_content": f"Hh{i}_Adolor_Fhands_V1",
            "spend": 5.0,  # total 50
            "impressions": 1000,
            "clicks": 20 + i,
            "conversions": 1,
            "roas": 1.5 + (i * 0.05),
            "hook_rate_3s": 18 + i,
        }
        events.append(_mk_event("2026-01-01T00:00:00Z", payload))

    ledger = FakeLedger(events=events)
    cfg = LearningLoopConfig(min_records=8, min_spend_before_learn=15.0, require_evidence=True)

    runner = LearningLoop(repo)
    res1 = runner.run(ledger_obj=ledger, cfg=cfg, force=False, dry_run=False)
    assert res1.status in ("COMPLETED", "COMPLETED_DRY_RUN")
    weights_path = Path(res1.weights_path)
    assert weights_path.exists()

    data1 = json.loads(weights_path.read_text(encoding="utf-8"))
    assert data1["schema_version"] == "1.0.0"
    assert "angles" in data1 and "formats" in data1 and "hooks" in data1

    # second run with same input => SKIPPED
    res2 = runner.run(ledger_obj=ledger, cfg=cfg, force=False, dry_run=False)
    assert res2.status == "SKIPPED"

    # verify ledger writes include completed + skipped
    types = [w["event_type"] for w in ledger.writes]
    assert "LEARNING_LOOP_COMPLETED" in types
    assert "LEARNING_LOOP_SKIPPED" in types


def test_learning_loop_respects_dry_run(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    events = []
    for i in range(8):
        payload = {
            "product_id": "34357",
            "platform": "tiktok",
            "creative_id": f"cr_{i}",
            "angle": "status",
            "format": "voiceover",
            "hook_id": f"h{i}",
            "spend": 3.0,  # total 24
            "impressions": 800,
            "clicks": 10,
            "conversions": 1,
            "roas": 1.2,
            "hook_rate_3s": 22,
        }
        events.append(_mk_event("2026-01-01T00:00:00Z", payload))

    ledger = FakeLedger(events=events)
    cfg = LearningLoopConfig(min_records=8, min_spend_before_learn=15.0, require_evidence=True)

    runner = LearningLoop(repo)
    res = runner.run(ledger_obj=ledger, cfg=cfg, dry_run=True)

    assert res.status == "COMPLETED_DRY_RUN"
    # dry run still writes report + state, but weights may or may not exist
    assert Path(res.report_path).exists()
    assert Path(res.state_path).exists()

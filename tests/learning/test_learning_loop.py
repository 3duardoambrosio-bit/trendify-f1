import json
from pathlib import Path

from synapse.learning.learning_loop import (
    LearningLoop,
    LearningLoopConfig,
    STATUS_COMPLETED_DRY_RUN,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_LEARNING_LOOP_LEDGER_FAILED,
    STATUS_LEDGER_UNREADABLE,
    STATUS_PAYLOAD_SHAPE_DRIFT,
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
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
            }
        )


class LegacyOnlyLedger:
    def __init__(self, events):
        self._events = list(events)
        self.calls = []

    def write(self, event_type, entity_type, entity_id, payload):
        self.calls.append(
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
            }
        )


class DictWriteLedger:
    def __init__(self, events):
        self._events = list(events)
        self.calls = []

    def write(self, event):
        self.calls.append(event)


class MissingWriteLedger:
    def __init__(self, events):
        self._events = list(events)


class BrokenReadLedger:
    def iter_events(self):
        raise OSError("ledger backend unavailable")


class BrokenReadButWritableLedger(BrokenReadLedger):
    def __init__(self):
        self.calls = []

    def write(self, event_type, entity_type, entity_id, payload):
        self.calls.append(
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
            }
        )


class EvilStr:
    def __str__(self):
        raise RuntimeError("boom")


def _mk_event(ts, payload, event_type="EXPERIMENT_METRICS_RECORDED", entity_id="34357"):
    return {
        "timestamp": ts,
        "event_type": event_type,
        "entity_type": "product",
        "entity_id": entity_id,
        "payload": payload,
    }


def _read_json(path_str: str):
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


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

    assert res.status == STATUS_INSUFFICIENT_EVIDENCE
    report_path = Path(res.report_path)
    assert report_path.exists()
    txt = report_path.read_text(encoding="utf-8")
    assert STATUS_INSUFFICIENT_EVIDENCE in txt


def test_learning_loop_updates_weights_and_is_idempotent(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    events = []
    for i in range(10):
        payload = {
            "product_id": "34357",
            "platform": "meta",
            "utm_content": f"Hh{i}_Adolor_Fhands_V1",
            "creative_id": f"cr_{i}",
            "spend": 5.0,
            "impressions": 1000,
            "clicks": 20,
            "conversions": 2,
            "roas": 1.8,
            "hook_rate_3s": 28,
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

    res2 = runner.run(ledger_obj=ledger, cfg=cfg, force=False, dry_run=False)
    assert res2.status == "SKIPPED"

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
            "spend": 3.0,
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

    assert res.status == STATUS_COMPLETED_DRY_RUN
    assert Path(res.report_path).exists()
    assert Path(res.state_path).exists()


def test_learning_loop_writes_legacy_four_arg_contract_explicitly(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    ledger = LegacyOnlyLedger(events=[])
    cfg = LearningLoopConfig(min_records=8, require_evidence=True)

    runner = LearningLoop(repo)
    res = runner.run(ledger_obj=ledger, cfg=cfg)

    assert res.status == STATUS_INSUFFICIENT_EVIDENCE
    assert len(ledger.calls) == 1
    assert ledger.calls[0]["event_type"] == "LEARNING_LOOP_SKIPPED"
    assert ledger.calls[0]["entity_type"] == "learning_loop"
    assert ledger.calls[0]["payload"]["status"] == STATUS_INSUFFICIENT_EVIDENCE


def test_learning_loop_writes_single_dict_contract_explicitly(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    ledger = DictWriteLedger(events=[])
    cfg = LearningLoopConfig(min_records=8, require_evidence=True)

    runner = LearningLoop(repo)
    res = runner.run(ledger_obj=ledger, cfg=cfg)

    assert res.status == STATUS_INSUFFICIENT_EVIDENCE
    assert len(ledger.calls) == 1
    assert ledger.calls[0]["event_type"] == "LEARNING_LOOP_SKIPPED"
    assert ledger.calls[0]["status"] == STATUS_INSUFFICIENT_EVIDENCE


def test_learning_loop_marks_ledger_failed_but_preserves_local_report(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    ledger = MissingWriteLedger(events=[])
    runner = LearningLoop(repo)

    res = runner.run(ledger_obj=ledger, cfg=LearningLoopConfig())

    assert res.status == STATUS_LEARNING_LOOP_LEDGER_FAILED
    state = _read_json(res.state_path)
    report = _read_json(res.report_path)
    assert state["status"] == STATUS_LEARNING_LOOP_LEDGER_FAILED
    assert report["status"] == STATUS_LEARNING_LOOP_LEDGER_FAILED
    assert state["intended_status"] == STATUS_INSUFFICIENT_EVIDENCE
    assert report["intended_status"] == STATUS_INSUFFICIENT_EVIDENCE


def test_learning_loop_marks_ledger_unreadable_when_event_stream_breaks(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    ledger = BrokenReadButWritableLedger()
    runner = LearningLoop(repo)

    res = runner.run(ledger_obj=ledger, cfg=LearningLoopConfig())

    assert res.status == STATUS_LEDGER_UNREADABLE
    report = _read_json(res.report_path)
    assert report["status"] == STATUS_LEDGER_UNREADABLE
    assert report["ledger_read_error_type"] == "LedgerReadError"


def test_learning_loop_marks_payload_shape_drift_when_drop_ratio_is_high(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    malformed = [{"payload": "not-json"} for _ in range(6)]
    valid = [
        _mk_event(
            "2026-01-01T00:00:00Z",
            {
                "product_id": "34357",
                "platform": "meta",
                "spend": 5.0,
                "roas": 1.2,
                "hook_rate_3s": 20,
                "utm_content": "Hh1_Astatus_Fhands_V1",
            },
        )
        for _ in range(2)
    ]
    ledger = FakeLedger(events=malformed + valid)
    runner = LearningLoop(repo)

    res = runner.run(ledger_obj=ledger, cfg=LearningLoopConfig(min_records=1))

    assert res.status == STATUS_PAYLOAD_SHAPE_DRIFT
    report = _read_json(res.report_path)
    assert report["payloads_dropped_by_shape"] == 6
    assert report["payload_candidates_total"] == 8
    assert report["payload_shape_drift_ratio"] >= 0.5


def test_learning_loop_discards_synthetic_check_errors_fail_closed_and_counts_them(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    events = []
    for i in range(7):
        events.append(
            _mk_event(
                "2026-01-01T00:00:00Z",
                {
                    "product_id": "34357",
                    "platform": "meta",
                    "creative_id": f"cr_{i}",
                    "utm_content": f"Hh{i}_Astatus_Fhands_V1",
                    "spend": 3.0,
                    "impressions": 1000,
                    "clicks": 20,
                    "conversions": 2,
                    "roas": 1.7,
                    "hook_rate_3s": 27,
                },
            )
        )

    events.append(
        _mk_event(
            "2026-01-01T00:00:00Z",
            {
                "product_id": "34357",
                "platform": "meta",
                "creative_id": "cr_bad",
                "utm_content": "Hbad_Astatus_Fhands_V1",
                "marker": EvilStr(),
                "spend": 3.0,
                "impressions": 1000,
                "clicks": 20,
                "conversions": 2,
                "roas": 1.7,
                "hook_rate_3s": 27,
            },
        )
    )

    ledger = FakeLedger(events=events)
    runner = LearningLoop(repo)
    cfg = LearningLoopConfig(min_records=7, min_spend_before_learn=15.0, require_evidence=True)

    res = runner.run(ledger_obj=ledger, cfg=cfg, dry_run=True)

    assert res.status == STATUS_COMPLETED_DRY_RUN
    report = _read_json(res.report_path)
    assert report["synthetic_check_errors"] == 1
    assert report["records_used"] == 7


def test_learning_loop_never_reports_completed_or_skipped_on_internal_failures(tmp_path):
    repo = tmp_path
    (repo / "data" / "learning").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "config").mkdir(parents=True, exist_ok=True)

    runner = LearningLoop(repo)

    ledger_failure = runner.run(ledger_obj=MissingWriteLedger(events=[]), cfg=LearningLoopConfig())
    read_failure = runner.run(ledger_obj=BrokenReadLedger(), cfg=LearningLoopConfig())
    malformed = runner.run(
        ledger_obj=FakeLedger(events=[{"payload": "not-json"} for _ in range(6)]),
        cfg=LearningLoopConfig(min_records=1),
    )

    assert ledger_failure.status not in ("COMPLETED", "SKIPPED")
    assert read_failure.status not in ("COMPLETED", "SKIPPED")
    assert malformed.status not in ("COMPLETED", "SKIPPED")

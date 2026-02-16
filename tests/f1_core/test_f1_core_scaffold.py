import json
from pathlib import Path

def test_feature_flags_load_defaults():
    from synapse.infra.feature_flags import FeatureFlags
    flags = FeatureFlags.load()
    assert isinstance(flags.values, dict)

def test_idempotency_store_roundtrip(tmp_path: Path):
    from synapse.infra.idempotency_store import IdempotencyStore
    p = tmp_path / "idempo.json"
    s = IdempotencyStore.open(p)
    assert s.has("k") is False
    s.put("k", "v1")
    s2 = IdempotencyStore.open(p)
    assert s2.has("k") is True
    assert s2.get("k") == "v1"

def test_ledger_append(tmp_path: Path):
    from synapse.infra.ledger_f1_core import Ledger
    p = tmp_path / "ledger.ndjson"
    l = Ledger.open(p)
    l.append("test.event", "corr1", "idem1", payload={"a": 1})
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_type"] == "test.event"
    assert rec["correlation_id"] == "corr1"
    assert rec["idempotency_key"] == "idem1"
    assert rec["payload"]["a"] == 1

from core.ledger_analyzer_v1 import analyze_ndjson

def test_analyze_ndjson_counts():
    lines = [
        '{"event_type":"A","entity_type":"product"}',
        '{"event_type":"A","entity_type":"product"}',
        '{"event_type":"B","entity_type":"system"}',
        'not-json',
        '',
    ]
    s = analyze_ndjson(lines)
    assert s.total == 4
    assert s.by_event["A"] == 2
    assert s.by_event["B"] == 1
    assert s.by_event["_INVALID_JSON"] == 1
    assert s.by_entity["product"] == 2
    assert s.by_entity["system"] == 1
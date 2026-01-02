# tests/reporting/test_audit_viewer.py
import os
import json
import tempfile

from synapse.reporting.audit_viewer import AuditQuery, query_events, render_markdown, write_report


def _write_ndjson(fp: str, rows):
    with open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_query_events_parses_ndjson_and_filters():
    with tempfile.TemporaryDirectory() as d:
        ledger_dir = os.path.join(d, "ledger")
        os.makedirs(ledger_dir, exist_ok=True)
        fp = os.path.join(ledger_dir, "ledger_2026_01.ndjson")
        _write_ndjson(fp, [
            {"timestamp":"t1","event_type":"A","entity_type":"product","entity_id":"1","wave_id":"w1","payload":{"status":"ok"}},
            {"timestamp":"t2","event_type":"B","entity_type":"product","entity_id":"2","wave_id":"w2","payload":{"status":"ok"}},
        ])

        evs = query_events(ledger_dir, AuditQuery(entity_id="1"))
        assert len(evs) == 1
        assert evs[0]["event_type"] == "A"


def test_render_and_write_report():
    md = render_markdown([{"timestamp":"t1","event_type":"X","entity_type":"product","entity_id":"9","wave_id":"w","payload":{"message":"hi"}}])
    assert "| t1 | X | product:9 | w | hi |" in md

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "r.md")
        write_report(md, out)
        assert os.path.exists(out)

from __future__ import annotations

from infra.ledger_v2 import AMENDMENT_DOCUMENT_TYPE, APPEND_ONLY_DOCUMENT_TYPE
from synapse.meta.governed_write_anchor import (
    ANCHOR_CONTRACT_VERSION,
    ANCHOR_SOURCE,
    attach_governed_anchor,
    build_governed_anchor,
)


def test_build_governed_anchor_append_only_shape():
    anchor = build_governed_anchor(
        event_type="meta.create_campaign.attempt",
        correlation_id="corr-1",
        idempotency_key="idem-1",
        payload={"name": "Campaign A"},
        severity="INFO",
        critical=True,
    )

    assert anchor["document_type"] == APPEND_ONLY_DOCUMENT_TYPE
    assert anchor["status"] == "APPENDED"
    assert anchor["clock_source_id"] == "synapse.time_utc.v1"
    assert anchor["payload"]["event_type"] == "meta.create_campaign.attempt"
    assert anchor["payload"]["correlation_id"] == "corr-1"
    assert anchor["payload"]["idempotency_key"] == "idem-1"
    assert anchor["payload"]["payload"]["name"] == "Campaign A"
    assert anchor["metadata"]["anchor_contract_version"] == ANCHOR_CONTRACT_VERSION
    assert anchor["metadata"]["source"] == ANCHOR_SOURCE
    assert anchor["metadata"]["critical"] is True


def test_build_governed_anchor_amendment_shape():
    anchor = build_governed_anchor(
        event_type="meta.create_campaign.result",
        correlation_id="corr-2",
        idempotency_key="idem-2",
        payload={"campaign_id": "123"},
        base_event_id="corr-1",
    )

    assert anchor["document_type"] == AMENDMENT_DOCUMENT_TYPE
    assert anchor["status"] == "AMENDED"
    assert anchor["base_event_id"] == "corr-1"


def test_attach_governed_anchor_does_not_mutate_original_payload():
    original = {"ok": True, "campaign_id": "abc"}
    wrapped = attach_governed_anchor(
        event_type="meta.create_campaign.result",
        correlation_id="corr-3",
        idempotency_key="idem-3",
        payload=original,
    )

    assert "governed_anchor" not in original
    assert "governed_anchor" in wrapped
    assert wrapped["campaign_id"] == "abc"
    assert wrapped["governed_anchor"]["payload"]["payload"]["campaign_id"] == "abc"

from __future__ import annotations

import copy

import pytest

from synapse.ui.system_checkpoint_report import (
    SystemCheckpointReportError,
    render_system_checkpoint_report,
)


def _report_data() -> dict:
    return {
        "sample_input": True,
        "commercial_evidence": False,
        "offline_only": True,
        "external_write": False,
        "live_action": False,
        "published": False,
        "product": {
            "product_id": "local-001",
            "title": "Local product",
        },
        "financial": {
            "authority": "synapse.financial.evaluation",
            "decision": "PASS",
            "contribution_margin_mxn": "180.00",
        },
        "decision": {
            "authority": "CHECKPOINT_DECISION_ADAPTER_V1",
            "verdict": "READY_FOR_REVIEW",
        },
        "methodology": {
            "status": "accepted",
            "selected_rule_id": "ANG-D001",
            "operator_review_required": False,
        },
        "customer_copy": {
            "title": "Operator-approved title",
            "description": "Bounded local preview copy.",
            "content_state": "OPERATOR_APPROVED_LOCAL_COPY",
        },
        "canonical_product": {
            "product_id": "local-001",
            "candidate_sha256": "a" * 64,
            "approval_sha256": "b" * 64,
        },
        "storefront_read_model": {
            "preview_status": "READY",
            "publication_status": "NOT_AUTHORIZED",
        },
        "shopify_boundary": {
            "shopify_mode": "draft_export",
            "published": False,
            "external_write": False,
            "shopify_api_called": False,
            "operator_publication_approval": False,
        },
        "execution_trace": [
            {
                "step": "catalog_normalization",
                "status": "PASS",
                "manual": False,
                "external_write": False,
                "fixture_used": False,
            },
            {
                "step": "promotion_approval",
                "status": "PASS",
                "manual": True,
                "external_write": False,
                "fixture_used": False,
                "digest": "c" * 64,
            },
        ],
    }


def test_report_contains_fixed_a_to_i_sections_and_boundaries() -> None:
    document = render_system_checkpoint_report(_report_data())

    expected_sections = (
        ("a-product", "A. Product"),
        ("b-financial", "B. Financial evaluation"),
        ("c-decision", "C. Checkpoint decision"),
        ("d-methodology", "D. Methodology"),
        ("e-customer-copy", "E. Customer copy"),
        ("f-canonical-product", "F. Canonical product custody"),
        ("g-storefront-read-model", "G. Storefront read model"),
        ("h-shopify-boundary", "H. Shopify boundary"),
        ("i-execution-trace", "I. Execution trace"),
    )

    positions = []
    for section_id, heading in expected_sections:
        marker = f'<section id="{section_id}"'
        assert marker in document
        assert f"<h2>{heading}</h2>" in document
        positions.append(document.index(marker))

    assert positions == sorted(positions)
    assert "LOCAL-ONLY" in document
    assert "NO LIVE ACTIONS" in document
    assert "NO EXTERNAL WRITES" in document
    assert "NOT PUBLISHED" in document
    assert "does not authorize publication" in document


def test_every_operator_value_is_escaped_and_urls_are_omitted() -> None:
    data = _report_data()
    data["customer_copy"]["title"] = (
        '<script>alert("unsafe & active")</script>'
    )
    data["customer_copy"]["description"] = (
        'Visit https://example.invalid/path?q="x" '
        'or <a href="javascript:alert(1)">click</a>.'
    )

    document = render_system_checkpoint_report(data)
    lowered = document.casefold()

    assert "<script" not in lowered
    assert "</script" not in lowered
    assert "<a " not in lowered
    assert "https://" not in lowered
    assert "javascript:" not in lowered
    assert "&lt;script&gt;" in document
    assert "unsafe &amp; active" in document
    assert "[absolute URL omitted]" in document

    for active_tag in ("<link", "<form", "<iframe", "<object"):
        assert active_tag not in lowered


def test_report_is_byte_deterministic_and_non_mutating() -> None:
    data = _report_data()
    before = copy.deepcopy(data)

    first = render_system_checkpoint_report(data)
    second = render_system_checkpoint_report(data)

    assert data == before
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.endswith("\n")


def test_sample_is_prominently_not_commercial_evidence() -> None:
    document = render_system_checkpoint_report(_report_data())

    assert "SAMPLE INPUT — NOT COMMERCIAL EVIDENCE" in document
    assert "sample_input=true" in document
    assert "commercial_evidence=false" in document
    assert "offline_only=true" in document
    assert "external_write=false" in document
    assert "live_action=false" in document
    assert "published=false" in document


def test_execution_trace_preserves_step_order_and_fields() -> None:
    document = render_system_checkpoint_report(_report_data())

    first = document.index("catalog_normalization")
    second = document.index("promotion_approval")

    assert first < second
    assert "fixture_used" in document
    assert "external_write" in document
    assert "manual" in document
    assert "digest" in document


@pytest.mark.parametrize(
    "section",
    (
        "product",
        "financial",
        "decision",
        "methodology",
        "customer_copy",
        "canonical_product",
        "storefront_read_model",
        "shopify_boundary",
        "execution_trace",
    ),
)
def test_missing_section_fails_closed(section: str) -> None:
    data = _report_data()
    data.pop(section)

    with pytest.raises(
        SystemCheckpointReportError,
        match="missing required section",
    ):
        render_system_checkpoint_report(data)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("commercial_evidence", True),
        ("offline_only", False),
        ("external_write", True),
        ("live_action", True),
        ("published", True),
    ),
)
def test_unsafe_report_flags_fail_closed(
    field: str,
    unsafe_value: bool,
) -> None:
    data = _report_data()
    data[field] = unsafe_value

    with pytest.raises(
        SystemCheckpointReportError,
        match=field,
    ):
        render_system_checkpoint_report(data)


def test_user_supplied_input_remains_non_commercial_evidence() -> None:
    data = _report_data()
    data["sample_input"] = False

    document = render_system_checkpoint_report(data)

    assert "USER-SUPPLIED INPUT — NOT COMMERCIAL EVIDENCE" in document
    assert "sample_input=false" in document
    assert "commercial_evidence=false" in document


@pytest.mark.parametrize("value", (None, 0, 1, "false"))
def test_sample_input_must_be_an_exact_boolean(value: object) -> None:
    data = _report_data()
    data["sample_input"] = value

    with pytest.raises(
        SystemCheckpointReportError,
        match="sample_input must be a boolean",
    ):
        render_system_checkpoint_report(data)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    (
        ("shopify_mode", "live"),
        ("published", True),
        ("external_write", True),
        ("shopify_api_called", True),
        ("operator_publication_approval", True),
    ),
)
def test_unsafe_shopify_boundary_fails_closed(
    field: str,
    unsafe_value: object,
) -> None:
    data = _report_data()
    data["shopify_boundary"][field] = unsafe_value

    with pytest.raises(
        SystemCheckpointReportError,
        match=field,
    ):
        render_system_checkpoint_report(data)


def test_non_mapping_report_and_non_mapping_section_fail_closed() -> None:
    with pytest.raises(
        SystemCheckpointReportError,
        match="report_data must be a mapping",
    ):
        render_system_checkpoint_report([])  # type: ignore[arg-type]

    data = _report_data()
    data["financial"] = []

    with pytest.raises(
        SystemCheckpointReportError,
        match=r"report_data\.financial must be a mapping",
    ):
        render_system_checkpoint_report(data)

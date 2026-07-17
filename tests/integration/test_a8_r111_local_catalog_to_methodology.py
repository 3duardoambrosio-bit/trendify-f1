from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from synapse.integration.local_catalog_to_methodology import (
    LocalCatalogMethodologyBridgeError,
    build_methodology_input,
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.ui.local_catalog_workspace import parse_catalog_csv


ROOT = Path(__file__).resolve().parents[2]

NOMINAL_CSV = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r110_catalog"
    / "catalog_nominal.csv"
)

CONTEXT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r111_methodology_context"
    / "nominal_context.json"
)

BRIDGE_PATH = (
    ROOT
    / "synapse"
    / "integration"
    / "local_catalog_to_methodology.py"
)


def _fixture() -> dict:
    result = parse_catalog_csv(NOMINAL_CSV)
    return copy.deepcopy(dict(result.fixtures[0]))


def _context() -> dict:
    return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "field",
    (
        "product_facts",
        "buyer_state",
        "proof_available",
        "claim_risk",
        "channel",
        "margin_profile",
        "category",
    ),
)
def test_missing_required_context_fails_closed(field: str) -> None:
    context = _context()
    context.pop(field)

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match=f"missing_context_fields={field}",
    ):
        build_methodology_input(_fixture(), context)


def test_explicit_context_maps_without_defaults() -> None:
    context = _context()

    decision_input = build_methodology_input(
        _fixture(),
        context,
    )

    assert decision_input.product_facts == tuple(
        context["product_facts"]
    )
    assert decision_input.buyer_state == context["buyer_state"]
    assert decision_input.proof_available == tuple(
        context["proof_available"]
    )
    assert decision_input.claim_risk == context["claim_risk"]
    assert decision_input.channel == context["channel"]
    assert decision_input.margin_profile == context["margin_profile"]
    assert decision_input.candidate_output == ""
    assert decision_input.category == context["category"]


def test_empty_proof_sequence_is_explicitly_allowed() -> None:
    context = _context()
    context["proof_available"] = []

    decision_input = build_methodology_input(
        _fixture(),
        context,
    )

    assert decision_input.proof_available == ()


def test_category_mismatch_fails_closed() -> None:
    context = _context()
    context["category"] = "otra_categoria"

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="must exactly match",
    ):
        build_methodology_input(_fixture(), context)


def test_unknown_context_field_fails_closed() -> None:
    context = _context()
    context["derived_buyer_state"] = "forbidden"

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="unexpected_context_fields=derived_buyer_state",
    ):
        build_methodology_input(_fixture(), context)


def test_wrong_source_kind_fails_closed() -> None:
    fixture = _fixture()
    fixture["source_kind"] = "frozen_local_fixture"

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="source_kind",
    ):
        build_methodology_input(fixture, _context())


def test_non_review_gate_fails_closed() -> None:
    fixture = _fixture()
    fixture["decision"]["permission_gate"] = "PASS"

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="must remain REVIEW",
    ):
        build_methodology_input(fixture, _context())


def test_enrichment_is_non_mutating_and_preserves_review_gate() -> None:
    fixture = _fixture()
    before = copy.deepcopy(fixture)

    enriched = enrich_local_catalog_fixture_with_methodology(
        fixture,
        _context(),
    )

    assert fixture == before
    assert enriched is not fixture
    assert enriched["decision"]["outcome"] == before["decision"]["outcome"]
    assert enriched["decision"]["permission_gate"] == "REVIEW"

    methodology = enriched["decision"]["methodology"]

    assert (
        methodology["schema_version"]
        == "synapse.marketing_methodology.decision_engine.v1"
    )
    assert methodology["selected_rule_id"] == "ANG-D001"
    assert methodology["status"] == "accepted"
    assert "Hook:" in methodology["safe_output"]

def test_no_standalone_commercial_objects_are_generated() -> None:
    enriched = enrich_local_catalog_fixture_with_methodology(
        _fixture(),
        _context(),
    )

    assert "marketing" not in enriched
    assert "shopify" not in enriched

    methodology = enriched["decision"]["methodology"]

    assert "safe_output" in methodology
    assert "Hook:" in methodology["safe_output"]

    bridge_envelope_keys = {
        "bridge_schema_version",
        "source",
        "permission_gate",
        "methodology_safe_output_generated",
        "safe_output_is_publication_authorization",
        "standalone_marketing_pack_generated",
        "shopify_pack_generated",
        "campaign_or_ad_objects_generated",
        "budget_or_spend_authorization_generated",
        "boundaries",
        "engine_decision",
    }

    assert set(methodology).isdisjoint(bridge_envelope_keys)

def test_bridge_is_deterministic_and_json_ready() -> None:
    fixture = _fixture()
    context = _context()

    first = enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )

    second = enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )

    first_json = json.dumps(
        first,
        ensure_ascii=False,
        sort_keys=True,
    )

    second_json = json.dumps(
        second,
        ensure_ascii=False,
        sort_keys=True,
    )

    assert first == second
    assert first_json == second_json


def test_existing_methodology_is_never_overwritten() -> None:
    fixture = _fixture()
    fixture["decision"]["methodology"] = {"existing": True}

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="already exists",
    ):
        enrich_local_catalog_fixture_with_methodology(
            fixture,
            _context(),
        )


def test_loader_failure_is_wrapped_and_fails_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="methodology_engine_failed",
    ):
        enrich_local_catalog_fixture_with_methodology(
            _fixture(),
            _context(),
            spec_path=tmp_path / "missing_spec.json",
        )


def test_bridge_has_no_live_or_external_dependencies() -> None:
    source = BRIDGE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".")[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    forbidden_import_roots = {
        "os",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "urllib",
        "ftplib",
        "smtplib",
    }

    assert not (imported_roots & forbidden_import_roots)

    for forbidden_dependency in (
        "expert_foundation",
        "brief_builder",
        "category_angle_from_methodology",
    ):
        assert forbidden_dependency not in source

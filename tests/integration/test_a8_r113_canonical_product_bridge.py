from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from synapse.integration.a8_r70_smoke import (
    run_a8_r70_smoke_integration,
)
from synapse.integration.canonical_product_bridge import (
    APPROVAL_SCOPE,
    APPROVAL_STATUS,
    SCHEMA_VERSION,
    SOURCE_KIND,
    CanonicalProductBridgeError,
    discovery_candidate_sha256,
    promote_smoke_result_to_local_fixture,
    serialize_discovery_candidate,
    validate_promoted_fixture_custody,
    validate_promotion_approval,
)
from synapse.integration.local_catalog_to_methodology import (
    ALLOWED_SOURCE_KINDS as METHODOLOGY_SOURCE_KINDS,
)
from synapse.integration.local_catalog_to_methodology import (
    LocalCatalogMethodologyBridgeError,
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.ui.storefront_customer_copy import (
    customer_copy_sha256,
)
from synapse.ui.storefront_read_model import (
    ALLOWED_SOURCE_KINDS as STOREFRONT_SOURCE_KINDS,
)
from synapse.ui.storefront_read_model import (
    StorefrontReadModelError,
    build_storefront_read_model,
    serialize_storefront_read_model,
)


ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = (
    ROOT
    / "synapse"
    / "integration"
    / "canonical_product_bridge.py"
)


FIXTURE_ROOT = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r113_canonical_bridge"
)
CONTRACT_PATH = (
    ROOT
    / "docs"
    / "a8_r113"
    / "CANONICAL_PRODUCT_BRIDGE_CONTRACT.md"
)


def _load_nominal_fixture(name: str) -> dict:
    return json.loads(
        FIXTURE_ROOT.joinpath(name).read_text(
            encoding="utf-8"
        )
    )


def _smoke():
    return run_a8_r70_smoke_integration()


def _promotion_approval(result) -> dict:
    candidate = result.candidate

    return {
        "schema_version": SCHEMA_VERSION,
        "status": APPROVAL_STATUS,
        "scope": APPROVAL_SCOPE,
        "operator_id": "operator-local-001",
        "approval_record_id": "a8-r113-approval-001",
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": discovery_candidate_sha256(
            candidate
        ),
        "decision_run_id": result.decision_record.run_id,
        "financial_decision": (
            result.financial_result.decision.value
        ),
        "final_decision": (
            result.decision_record.final_decision.value
        ),
        "publication_authorized": False,
        "external_writes_authorized": False,
        "spend_authorized": False,
        "fulfillment_authorized": False,
    }


def _methodology_context(candidate) -> dict:
    return {
        "product_facts": [
            (
                "Identidad sintética local: "
                + candidate.product_name
            ),
            (
                "Uso declarado en discovery: "
                + candidate.use_case
            ),
        ],
        "product_id": candidate.candidate_id,
        "buyer_state": "problem-aware",
        "proof_available": [
            (
                "Registro sintético local con identidad "
                "y economía explícitas"
            )
        ],
        "claim_risk": "low",
        "channel": "Meta",
        "margin_profile": "acceptable",
        "category": candidate.category,
        "candidate_output": "",
    }


def _customer_copy_approval(candidate) -> dict:
    customer_copy = {
        "product_id": candidate.candidate_id,
        "title": candidate.product_name,
        "description": (
            "Luz para complementar la iluminación de un "
            "escritorio con monitor durante sesiones nocturnas."
        ),
        "facts": [
            (
                "Formato de barra para colocación "
                "sobre monitor."
            ),
            (
                "Pensada para complementar la iluminación "
                "del área de trabajo."
            ),
        ],
        "proof": [],
    }

    return {
        "copy": customer_copy,
        "approval": {
            "status": "APPROVED_FOR_LOCAL_PREVIEW",
            "scope": "LOCAL_PREVIEW_ONLY",
            "approved_copy_sha256": customer_copy_sha256(
                customer_copy
            ),
            "publication_authorized": False,
            "external_writes_authorized": False,
        },
    }


def _pipeline() -> tuple:
    result = _smoke()
    candidate = result.candidate
    approval = _promotion_approval(result)

    fixture = promote_smoke_result_to_local_fixture(
        result,
        approval,
    )

    context = _methodology_context(candidate)

    enriched = enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )

    item = {
        "fixture": enriched,
        "methodology_context": context,
        "customer_copy_approval": (
            _customer_copy_approval(candidate)
        ),
    }

    model = build_storefront_read_model([item])

    return result, approval, fixture, context, enriched, model


def test_candidate_serialization_is_deterministic_and_bound() -> None:
    candidate = _smoke().candidate

    first = serialize_discovery_candidate(candidate)
    second = serialize_discovery_candidate(candidate)
    payload = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert payload["candidate_id"] == candidate.candidate_id
    assert payload["product_id"] == candidate.candidate_id
    assert len(discovery_candidate_sha256(candidate)) == 64


def test_nominal_promotion_approval_is_valid() -> None:
    result = _smoke()
    approval = _promotion_approval(result)

    validated = validate_promotion_approval(
        approval,
        candidate=result.candidate,
        decision_run_id=result.decision_record.run_id,
        financial_decision=(
            result.financial_result.decision.value
        ),
        final_decision=(
            result.decision_record.final_decision.value
        ),
    )

    assert validated == approval
    assert validated["candidate_id"] == (
        result.candidate.candidate_id
    )


@pytest.mark.parametrize(
    "field",
    (
        "publication_authorized",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
    ),
)
@pytest.mark.parametrize("unsafe_value", (True, 0, None, "false"))
def test_authorization_fields_require_exact_false(
    field: str,
    unsafe_value: object,
) -> None:
    result = _smoke()
    approval = _promotion_approval(result)
    approval[field] = unsafe_value

    with pytest.raises(
        CanonicalProductBridgeError,
        match=f"{field} must be false",
    ):
        promote_smoke_result_to_local_fixture(
            result,
            approval,
        )


def test_candidate_digest_mutation_fails_closed() -> None:
    result = _smoke()
    approval = _promotion_approval(result)
    approval["candidate_sha256"] = "0" * 64

    with pytest.raises(
        CanonicalProductBridgeError,
        match="candidate_sha256 mismatch",
    ):
        promote_smoke_result_to_local_fixture(
            result,
            approval,
        )


def test_uppercase_digest_fails_closed() -> None:
    result = _smoke()
    approval = _promotion_approval(result)
    approval["candidate_sha256"] = (
        approval["candidate_sha256"].upper()
    )

    with pytest.raises(
        CanonicalProductBridgeError,
        match="64 lowercase hexadecimal",
    ):
        promote_smoke_result_to_local_fixture(
            result,
            approval,
        )


def test_unknown_and_missing_approval_fields_fail_closed() -> None:
    result = _smoke()

    unknown = _promotion_approval(result)
    unknown["unexpected"] = True

    with pytest.raises(
        CanonicalProductBridgeError,
        match="unexpected_fields=unexpected",
    ):
        promote_smoke_result_to_local_fixture(
            result,
            unknown,
        )

    missing = _promotion_approval(result)
    missing.pop("operator_id")

    with pytest.raises(
        CanonicalProductBridgeError,
        match="missing_fields=operator_id",
    ):
        promote_smoke_result_to_local_fixture(
            result,
            missing,
        )


def test_promotion_is_non_mutating_and_review_gated() -> None:
    result = _smoke()
    approval = _promotion_approval(result)
    before = copy.deepcopy(approval)

    first = promote_smoke_result_to_local_fixture(
        result,
        approval,
    )
    second = promote_smoke_result_to_local_fixture(
        result,
        approval,
    )

    assert approval == before
    assert first == second
    assert first["source_kind"] == SOURCE_KIND
    assert first["product"]["product_id"] == (
        result.candidate.candidate_id
    )
    assert first["decision"]["permission_gate"] == "REVIEW"

    assert "methodology" not in first["decision"]
    assert "customer_copy_approval" not in first
    assert "public_content" not in first


def test_one_identity_reaches_approved_local_storefront() -> None:
    (
        result,
        _,
        fixture,
        context,
        enriched,
        model,
    ) = _pipeline()

    candidate = result.candidate
    candidate_id = candidate.candidate_id
    product = model["products"][0]
    methodology = enriched["decision"]["methodology"]

    assert candidate_id == fixture["product"]["product_id"]
    assert candidate_id == enriched["product"]["product_id"]
    assert candidate_id == context["product_id"]
    assert candidate_id == product["product_id"]

    assert methodology["status"] == "accepted"
    assert methodology["operator_review_required"] is False

    assert product["preview_status"] == "READY"
    assert product["publication_status"] == "NOT_AUTHORIZED"
    assert product["public_content"]["content_state"] == (
        "OPERATOR_APPROVED_LOCAL_COPY"
    )
    assert product["public_content"]["title"] == (
        candidate.product_name
    )

    assert all(
        value is False
        for value in model["safety"].values()
    )


def test_internal_custody_and_methodology_do_not_leak() -> None:
    _, _, _, _, _, model = _pipeline()

    serialized = serialize_storefront_read_model(model)

    for forbidden in (
        "safe_output",
        "candidate_sha256",
        "approval_record_id",
        "operator_id",
        "decision_run_id",
        "buyer_state",
        "claim_risk",
        "landed_cost_mxn",
        "estimated_cac_mxn",
        "contribution_margin_mxn",
    ):
        assert forbidden not in serialized


def test_source_kind_is_explicitly_bounded_downstream() -> None:
    assert SOURCE_KIND in METHODOLOGY_SOURCE_KINDS
    assert SOURCE_KIND in STOREFRONT_SOURCE_KINDS

    assert "operator_local_catalog_import" in (
        METHODOLOGY_SOURCE_KINDS
    )
    assert "operator_local_catalog_import" in (
        STOREFRONT_SOURCE_KINDS
    )



def test_promoted_fixture_custody_is_digest_bound() -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    validated = validate_promoted_fixture_custody(fixture)

    assert validated["candidate_id"] == (
        result.candidate.candidate_id
    )
    assert validated["candidate_sha256"] == (
        discovery_candidate_sha256(result.candidate)
    )
    assert len(validated["approval_sha256"]) == 64
    assert fixture["canonical_bridge"]["schema_version"] == (
        "a8-r113.promoted_fixture_custody.v2"
    )

    tampered = copy.deepcopy(fixture)
    tampered["canonical_bridge"]["candidate_snapshot"][
        "product_name"
    ] += " alterado"

    with pytest.raises(
        CanonicalProductBridgeError,
        match="candidate_sha256 mismatch",
    ):
        validate_promoted_fixture_custody(tampered)


@pytest.mark.parametrize(
    "field",
    (
        "operator_id",
        "approval_record_id",
        "decision_run_id",
        "financial_decision",
    ),
)
def test_promoted_fixture_rejects_approval_field_tampering(
    field: str,
) -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    tampered = copy.deepcopy(fixture)
    tampered["canonical_bridge"]["approval"][field] += "-tampered"

    with pytest.raises(
        CanonicalProductBridgeError,
        match="approval_sha256 mismatch",
    ):
        validate_promoted_fixture_custody(tampered)


def test_promoted_fixture_rejects_coordinated_decision_tampering() -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    tampered = copy.deepcopy(fixture)
    tampered["canonical_bridge"]["approval"][
        "final_decision"
    ] = "WATCH_SANDBOX_BRIEF_ONLY"
    tampered["canonical_bridge"]["approval"][
        "financial_decision"
    ] = "WATCH"
    tampered["decision"]["outcome"] = (
        "WATCH_SANDBOX_BRIEF_ONLY"
    )

    with pytest.raises(
        CanonicalProductBridgeError,
        match="approval_sha256 mismatch",
    ):
        validate_promoted_fixture_custody(tampered)


def test_promoted_fixture_rejects_approval_digest_tampering() -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    tampered = copy.deepcopy(fixture)
    tampered["canonical_bridge"]["approval_sha256"] = "0" * 64

    with pytest.raises(
        CanonicalProductBridgeError,
        match="approval_sha256 mismatch",
    ):
        validate_promoted_fixture_custody(tampered)


def test_promoted_source_requires_custody_downstream() -> None:
    result = _smoke()
    candidate = result.candidate
    context = _methodology_context(candidate)

    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    forged = copy.deepcopy(fixture)
    forged.pop("canonical_bridge")

    with pytest.raises(
        LocalCatalogMethodologyBridgeError,
        match="canonical_bridge",
    ):
        enrich_local_catalog_fixture_with_methodology(
            forged,
            context,
        )

    enriched = enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )

    forged_enriched = copy.deepcopy(enriched)
    forged_enriched.pop("canonical_bridge")

    item = {
        "fixture": forged_enriched,
        "methodology_context": context,
        "customer_copy_approval": (
            _customer_copy_approval(candidate)
        ),
    }

    with pytest.raises(
        StorefrontReadModelError,
        match="canonical_bridge",
    ):
        build_storefront_read_model([item])


def test_nominal_fixtures_drive_complete_pipeline() -> None:
    result = _smoke()
    candidate = result.candidate
    candidate_id = candidate.candidate_id

    approval = _load_nominal_fixture(
        "nominal_promotion_approval.json"
    )
    context = _load_nominal_fixture(
        "nominal_methodology_context.json"
    )
    copy_approval = _load_nominal_fixture(
        "nominal_customer_copy_approval.json"
    )

    assert approval["candidate_id"] == candidate_id
    assert context["product_id"] == candidate_id
    assert copy_approval["copy"]["product_id"] == candidate_id

    validated = validate_promotion_approval(
        approval,
        candidate=candidate,
        decision_run_id=result.decision_record.run_id,
        financial_decision=(
            result.financial_result.decision.value
        ),
        final_decision=(
            result.decision_record.final_decision.value
        ),
    )

    fixture = promote_smoke_result_to_local_fixture(
        result,
        validated,
    )

    custody = validate_promoted_fixture_custody(fixture)

    enriched = enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )

    model = build_storefront_read_model(
        [
            {
                "fixture": enriched,
                "methodology_context": context,
                "customer_copy_approval": copy_approval,
            }
        ]
    )

    product = model["products"][0]

    assert custody["candidate_id"] == candidate_id
    assert len(custody["approval_sha256"]) == 64
    assert product["product_id"] == candidate_id
    assert product["preview_status"] == "READY"
    assert product["publication_status"] == "NOT_AUTHORIZED"
    assert product["public_content"]["content_state"] == (
        "OPERATOR_APPROVED_LOCAL_COPY"
    )

    assert all(
        value is False
        for value in model["safety"].values()
    )


def test_nominal_fixtures_preserve_utf8_customer_copy() -> None:
    context = _load_nominal_fixture(
        "nominal_methodology_context.json"
    )
    copy_approval = _load_nominal_fixture(
        "nominal_customer_copy_approval.json"
    )

    serialized = json.dumps(
        {
            "context": context,
            "copy_approval": copy_approval,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "sintética" in serialized
    assert "economía explícitas" in serialized
    assert "iluminación" in serialized
    assert "colocación" in serialized
    assert "área de trabajo" in serialized
    assert "?" not in serialized


def test_contract_records_identity_custody_and_safety() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    required = (
        "DiscoveryCandidate.candidate_id",
        "operator_approved_discovery_promotion",
        "disc_71c892da6f966e",
        "candidate_snapshot",
        "permission_gate",
        "publication_status=NOT_AUTHORIZED",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
        "economics.price_mxn",
        "economics.landed_cost_mxn",
    )

    for fragment in required:
        assert fragment in contract



@pytest.mark.parametrize(
    ("economics_field", "tampered_value"),
    (
        ("price_mxn", "999999999.99"),
        ("landed_cost_mxn", "999999999.99"),
    ),
)
def test_promoted_fixture_custody_binds_economics_to_snapshot(
    economics_field: str,
    tampered_value: str,
) -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    tampered = copy.deepcopy(fixture)
    tampered["economics"][economics_field] = tampered_value

    with pytest.raises(
        CanonicalProductBridgeError,
        match=rf"fixture\.economics\.{economics_field}",
    ):
        validate_promoted_fixture_custody(tampered)


def test_promoted_fixture_custody_requires_mxn_currency() -> None:
    result = _smoke()
    fixture = promote_smoke_result_to_local_fixture(
        result,
        _promotion_approval(result),
    )

    tampered = copy.deepcopy(fixture)
    tampered["economics"]["currency"] = "USD"

    with pytest.raises(
        CanonicalProductBridgeError,
        match=r"fixture\.economics\.currency must remain MXN",
    ):
        validate_promoted_fixture_custody(tampered)

def test_bridge_has_no_live_dependencies() -> None:
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
            imported_roots.add(
                node.module.split(".")[0]
            )

    forbidden = {
        "os",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "urllib",
        "ftplib",
        "smtplib",
        "shopify",
        "boto3",
    }

    assert not (imported_roots & forbidden)
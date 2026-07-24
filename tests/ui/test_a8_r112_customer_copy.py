from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from synapse.ui.storefront_customer_copy import (
    APPROVAL_SCOPE,
    APPROVAL_STATUS,
    CONTENT_STATE,
    CustomerCopyApprovalError,
    customer_copy_sha256,
    serialize_customer_copy,
    validate_operator_approved_customer_copy,
)
from synapse.ui.storefront_read_model import (
    StorefrontReadModelError,
    build_storefront_read_model,
    serialize_storefront_read_model,
)


ROOT = Path(__file__).resolve().parents[2]
ITEM_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r112_storefront"
    / "nominal_item.json"
)
APPROVAL_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r112_customer_copy"
    / "nominal_approved_copy.json"
)
COPY_MODULE_PATH = (
    ROOT
    / "synapse"
    / "ui"
    / "storefront_customer_copy.py"
)


def _item() -> dict:
    return json.loads(ITEM_PATH.read_text(encoding="utf-8"))


def _approval() -> dict:
    return json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))


def _approved_item() -> dict:
    item = _item()
    item["customer_copy_approval"] = _approval()
    return item


def _product(model: dict) -> dict:
    return model["products"][0]


def test_nominal_approval_projects_operator_copy_locally() -> None:
    item = _approved_item()
    model = build_storefront_read_model([item])
    product = _product(model)
    envelope = item["customer_copy_approval"]

    assert product["public_content"] == {
        "title": envelope["copy"]["title"],
        "description": envelope["copy"]["description"],
        "facts": envelope["copy"]["facts"],
        "proof": envelope["copy"]["proof"],
        "content_state": CONTENT_STATE,
    }
    assert product["publication_status"] == "NOT_AUTHORIZED"
    assert model["safety"] == {
        "checkout_enabled": False,
        "publication_enabled": False,
        "external_writes_enabled": False,
        "fulfillment_enabled": False,
        "spend_enabled": False,
    }


def test_missing_approval_preserves_identity_only_contract() -> None:
    model = build_storefront_read_model([_item()])

    assert _product(model)["public_content"] == {
        "title": "Organizador de Cables Compacto",
        "description": "",
        "facts": [],
        "proof": [],
        "content_state": "IDENTITY_ONLY",
    }


def test_nominal_fixture_digest_matches_canonical_copy() -> None:
    envelope = _approval()

    assert envelope["approval"]["status"] == APPROVAL_STATUS
    assert envelope["approval"]["scope"] == APPROVAL_SCOPE
    assert (
        envelope["approval"]["approved_copy_sha256"]
        == customer_copy_sha256(envelope["copy"])
    )
    assert serialize_customer_copy(envelope["copy"]).endswith("\n")


def test_copy_mutation_invalidates_approval() -> None:
    envelope = _approval()
    envelope["copy"]["description"] += " Cambio no aprobado."

    with pytest.raises(
        CustomerCopyApprovalError,
        match="approved_copy_sha256 mismatch",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


def test_product_binding_mismatch_fails_closed() -> None:
    envelope = _approval()
    envelope["copy"]["product_id"] = "other-product"
    envelope["approval"]["approved_copy_sha256"] = (
        customer_copy_sha256(envelope["copy"])
    )

    with pytest.raises(
        CustomerCopyApprovalError,
        match="must exactly match",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


@pytest.mark.parametrize(
    "location",
    ("envelope", "copy", "approval"),
)
def test_unknown_fields_fail_closed(location: str) -> None:
    envelope = _approval()

    if location == "envelope":
        envelope["unexpected"] = True
    else:
        envelope[location]["unexpected"] = True

    with pytest.raises(
        CustomerCopyApprovalError,
        match="unexpected_fields=unexpected",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


@pytest.mark.parametrize("field", ("copy", "approval"))
def test_missing_envelope_fields_fail_closed(field: str) -> None:
    envelope = _approval()
    envelope.pop(field)

    with pytest.raises(
        CustomerCopyApprovalError,
        match="missing_fields",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


@pytest.mark.parametrize(
    "field,value,pattern",
    (
        ("status", "APPROVED_FOR_PUBLICATION", "approval.status"),
        ("scope", "SHOPIFY_LIVE", "approval.scope"),
        (
            "approved_copy_sha256",
            "not-a-digest",
            "64 lowercase hexadecimal",
        ),
    ),
)
def test_invalid_approval_identity_fails_closed(
    field: str,
    value: str,
    pattern: str,
) -> None:
    envelope = _approval()
    envelope["approval"][field] = value

    with pytest.raises(CustomerCopyApprovalError, match=pattern):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


def test_uppercase_digest_is_rejected() -> None:
    envelope = _approval()
    envelope["approval"]["approved_copy_sha256"] = (
        envelope["approval"]["approved_copy_sha256"].upper()
    )

    with pytest.raises(
        CustomerCopyApprovalError,
        match="64 lowercase hexadecimal",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("publication_authorized", True),
        ("publication_authorized", 0),
        ("external_writes_authorized", True),
        ("external_writes_authorized", 0),
    ),
)
def test_authorization_flags_must_be_exact_false(
    field: str,
    value: object,
) -> None:
    envelope = _approval()
    envelope["approval"][field] = value

    with pytest.raises(
        CustomerCopyApprovalError,
        match=f"{field} must be false",
    ):
        validate_operator_approved_customer_copy(
            envelope,
            expected_product_id="cat-001",
        )


@pytest.mark.parametrize(
    "status,review_required,remove_methodology,pattern",
    (
        ("blocked", True, False, "status accepted"),
        ("fallback", True, False, "status accepted"),
        ("accepted", True, False, "review to be false"),
        ("accepted", False, True, "requires methodology"),
    ),
)
def test_methodology_prerequisites_fail_closed(
    status: str,
    review_required: bool,
    remove_methodology: bool,
    pattern: str,
) -> None:
    item = _approved_item()

    if remove_methodology:
        item["fixture"]["decision"].pop("methodology")
    else:
        methodology = item["fixture"]["decision"]["methodology"]
        methodology["status"] = status
        methodology["operator_review_required"] = review_required

    with pytest.raises(StorefrontReadModelError, match=pattern):
        build_storefront_read_model([item])


def test_approval_input_is_non_mutating_and_deterministic() -> None:
    item = _approved_item()
    before = copy.deepcopy(item)

    first = build_storefront_read_model([item])
    second = build_storefront_read_model([item])

    assert item == before
    assert first == second
    assert (
        serialize_storefront_read_model(first)
        == serialize_storefront_read_model(second)
    )


@pytest.mark.parametrize("field", ("description", "facts", "proof"))
def test_absolute_urls_in_copy_fail_closed(field: str) -> None:
    envelope = _approval()

    if field == "description":
        envelope["copy"][field] = "Consulta https://example.com"
    else:
        envelope["copy"][field] = ["Consulta https://example.com"]

    with pytest.raises(CustomerCopyApprovalError, match="absolute URL"):
        customer_copy_sha256(envelope["copy"])


def test_copy_mapping_order_does_not_change_digest() -> None:
    envelope = _approval()
    original_copy = envelope["copy"]
    reversed_copy = {
        key: original_copy[key]
        for key in reversed(tuple(original_copy))
    }

    assert customer_copy_sha256(original_copy) == (
        customer_copy_sha256(reversed_copy)
    )


def test_safe_output_is_not_automatically_projected() -> None:
    item = _approved_item()
    safe_output = item["fixture"]["decision"]["methodology"]["safe_output"]

    serialized = serialize_storefront_read_model(
        build_storefront_read_model([item])
    )

    assert safe_output not in serialized
    assert "safe_output" not in serialized
    assert "claim_risk" not in serialized
    assert "buyer_state" not in serialized
    assert "product_cost_mxn" not in serialized
    assert "shipping_cost_mxn" not in serialized


def test_customer_copy_module_has_no_live_dependencies() -> None:
    source = COPY_MODULE_PATH.read_text(encoding="utf-8")
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
        "shopify",
    }

    assert not (imported_roots & forbidden_import_roots)

    for forbidden_call in (
        "requests.post",
        "requests.put",
        "requests.patch",
        "requests.delete",
        "httpx.post",
        "httpx.put",
        "httpx.patch",
        "httpx.delete",
    ):
        assert forbidden_call not in source



def test_nominal_public_copy_avoids_internal_approval_language() -> None:
    serialized = json.dumps(
        _approval()["copy"],
        ensure_ascii=False,
    ).casefold()

    forbidden_markers = (
        "operador",
        "aprobaci\u00f3n",
        "sha-256",
        "approved_copy_sha256",
    )

    for marker in forbidden_markers:
        assert marker not in serialized

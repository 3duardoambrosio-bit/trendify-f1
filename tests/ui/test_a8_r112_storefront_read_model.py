from __future__ import annotations

import ast
import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from synapse.ui.storefront_read_model import (
    SCHEMA_VERSION,
    STATUS_METHODOLOGY_MISSING,
    STATUS_PRICE_AND_METHODOLOGY_MISSING,
    STATUS_PRICE_MISSING,
    STATUS_READY,
    StorefrontReadModelError,
    build_storefront_read_model,
    serialize_storefront_read_model,
)


ROOT = Path(__file__).resolve().parents[2]
NOMINAL_ITEM_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r112_storefront"
    / "nominal_item.json"
)
MODULE_PATH = ROOT / "synapse" / "ui" / "storefront_read_model.py"


def _item() -> dict:
    return json.loads(NOMINAL_ITEM_PATH.read_text(encoding="utf-8"))


def _product(model: dict) -> dict:
    return model["products"][0]


def test_nominal_item_builds_ready_local_preview() -> None:
    model = build_storefront_read_model([_item()])
    product = _product(model)

    assert model["schema_version"] == SCHEMA_VERSION
    assert model["mode"] == "LOCAL_PREVIEW"
    assert model["currency"] == "MXN"
    assert model["home"]["featured_product_ids"] == ["cat-001"]
    assert model["collections"] == [
        {
            "slug": "hogar-y-oficina",
            "title": "hogar_y_oficina",
            "product_ids": ["cat-001"],
            "routes": {
                "collection": "/collections/hogar-y-oficina",
            },
        }
    ]

    assert product["product_id"] == "cat-001"
    assert product["slug"] == "cat-001"
    assert product["title"] == "Organizador de Cables Compacto"
    assert product["preview_status"] == STATUS_READY
    assert product["publication_status"] == "NOT_AUTHORIZED"
    assert product["price"] == {
        "state": "AVAILABLE",
        "currency": "MXN",
        "amount": "399.00",
    }
    assert product["routes"]["product_detail"] == "/products/cat-001"


def test_safety_envelope_is_permanently_disabled() -> None:
    model = build_storefront_read_model([_item()])

    assert model["safety"] == {
        "checkout_enabled": False,
        "publication_enabled": False,
        "external_writes_enabled": False,
        "fulfillment_enabled": False,
        "spend_enabled": False,
    }


def test_price_missing_is_honest_and_not_featured() -> None:
    item = _item()
    item["fixture"].pop("economics")

    model = build_storefront_read_model([item])
    product = _product(model)

    assert product["preview_status"] == STATUS_PRICE_MISSING
    assert product["price"] == {
        "state": "MISSING",
        "currency": "MXN",
        "amount": None,
    }
    assert model["home"]["featured_product_ids"] == []


def test_methodology_missing_is_honest_and_not_featured() -> None:
    item = _item()
    item["fixture"]["decision"].pop("methodology")

    model = build_storefront_read_model([item])
    product = _product(model)

    assert product["preview_status"] == STATUS_METHODOLOGY_MISSING
    assert product["operator_context"]["methodology_present"] is False
    assert product["operator_context"]["methodology_status"] == "missing"
    assert model["home"]["featured_product_ids"] == []


def test_price_and_methodology_missing_are_distinguished() -> None:
    item = _item()
    item["fixture"].pop("economics")
    item["fixture"]["decision"].pop("methodology")

    model = build_storefront_read_model([item])

    assert (
        _product(model)["preview_status"]
        == STATUS_PRICE_AND_METHODOLOGY_MISSING
    )


def test_wrong_source_kind_fails_closed() -> None:
    item = _item()
    item["fixture"]["source_kind"] = "frozen_local_fixture"

    with pytest.raises(
        StorefrontReadModelError,
        match="source_kind",
    ):
        build_storefront_read_model([item])


def test_non_review_gate_fails_closed() -> None:
    item = _item()
    item["fixture"]["decision"]["permission_gate"] = "PASS"

    with pytest.raises(
        StorefrontReadModelError,
        match="must remain REVIEW",
    ):
        build_storefront_read_model([item])


@pytest.mark.parametrize(
    "field,new_value",
    (
        ("product_id", "other-product"),
        ("category", "otra_categoria"),
    ),
)
def test_context_binding_mismatch_fails_closed(
    field: str,
    new_value: str,
) -> None:
    item = _item()
    item["methodology_context"][field] = new_value

    with pytest.raises(
        StorefrontReadModelError,
        match="must exactly match",
    ):
        build_storefront_read_model([item])


def test_unknown_item_or_context_fields_fail_closed() -> None:
    item = _item()
    item["derived_copy"] = "forbidden"

    with pytest.raises(
        StorefrontReadModelError,
        match="unexpected_fields=derived_copy",
    ):
        build_storefront_read_model([item])

    item = _item()
    item["methodology_context"]["derived_buyer_state"] = "forbidden"

    with pytest.raises(
        StorefrontReadModelError,
        match="unexpected_fields=derived_buyer_state",
    ):
        build_storefront_read_model([item])


def test_duplicate_product_id_fails_closed() -> None:
    first = _item()
    second = copy.deepcopy(first)

    with pytest.raises(
        StorefrontReadModelError,
        match="duplicate_product_id=cat-001",
    ):
        build_storefront_read_model([first, second])


def test_distinct_ids_with_same_slug_fail_closed() -> None:
    first = _item()
    second = _item()
    second["fixture"]["product"]["product_id"] = "cat 001"
    second["methodology_context"]["product_id"] = "cat 001"

    with pytest.raises(
        StorefrontReadModelError,
        match="duplicate_product_slug=cat-001",
    ):
        build_storefront_read_model([first, second])


@pytest.mark.parametrize(
    "value",
    (
        0,
        -1,
        "NaN",
        "Infinity",
        True,
        None,
    ),
)
def test_nonpositive_or_nonfinite_price_fails_closed(
    value: object,
) -> None:
    item = _item()
    item["fixture"]["economics"]["price_mxn"] = value

    with pytest.raises(
        StorefrontReadModelError,
        match="positive finite decimal",
    ):
        build_storefront_read_model([item])


def test_money_is_canonical_and_rounds_half_up() -> None:
    item = _item()
    item["fixture"]["economics"]["price_mxn"] = "399.995"

    model = build_storefront_read_model([item])

    assert _product(model)["price"]["amount"] == "400.00"


def test_public_surface_does_not_leak_operator_or_supplier_data() -> None:
    model = build_storefront_read_model([_item()])
    product = _product(model)
    serialized = serialize_storefront_read_model(model)

    assert product["public_content"] == {
        "title": "Organizador de Cables Compacto",
        "description": "",
        "facts": [],
        "proof": [],
        "content_state": "IDENTITY_ONLY",
    }

    for forbidden in (
        "Proveedor MX Alfa",
        "Hook: ejemplo interno",
        "product_cost_mxn",
        "shipping_cost_mxn",
        "contribution_margin_mxn",
        "claim_risk",
        "buyer_state",
        "candidate_output",
        "safe_output",
        "risk_flags",
    ):
        assert forbidden not in serialized


def test_methodology_context_counts_are_operator_only() -> None:
    model = build_storefront_read_model([_item()])
    operator_context = _product(model)["operator_context"]

    assert operator_context == {
        "permission_gate": "REVIEW",
        "decision_outcome": "EVALUATING",
        "methodology_present": True,
        "methodology_status": "accepted",
        "methodology_operator_review_required": False,
        "product_fact_count": 2,
        "proof_available_count": 1,
    }


def test_builder_is_non_mutating_and_deterministic() -> None:
    item = _item()
    before = copy.deepcopy(item)

    first = build_storefront_read_model([item])
    second = build_storefront_read_model([item])

    assert item == before
    assert first == second
    assert serialize_storefront_read_model(first) == (
        serialize_storefront_read_model(second)
    )


def test_order_is_deterministic_by_product_id_and_collection() -> None:
    first = _item()
    first["fixture"]["product"]["product_id"] = "z-002"
    first["methodology_context"]["product_id"] = "z-002"
    first["fixture"]["product"]["category"] = "zeta"
    first["methodology_context"]["category"] = "zeta"

    second = _item()
    second["fixture"]["product"]["product_id"] = "a-001"
    second["methodology_context"]["product_id"] = "a-001"
    second["fixture"]["product"]["category"] = "alpha"
    second["methodology_context"]["category"] = "alpha"

    model = build_storefront_read_model([first, second])

    assert [
        product["product_id"]
        for product in model["products"]
    ] == ["a-001", "z-002"]
    assert [
        collection["slug"]
        for collection in model["collections"]
    ] == ["alpha", "zeta"]
    assert model["home"]["featured_product_ids"] == [
        "a-001",
        "z-002",
    ]


def test_empty_sequence_builds_safe_empty_preview() -> None:
    model = build_storefront_read_model([])

    assert model["products"] == []
    assert model["collections"] == []
    assert model["home"]["featured_product_ids"] == []
    assert all(value is False for value in model["safety"].values())


def test_output_is_plain_json_without_decimal_or_enum_objects() -> None:
    model = build_storefront_read_model([_item()])
    encoded = serialize_storefront_read_model(model)
    decoded = json.loads(encoded)

    assert decoded == model

    def walk(value: object) -> None:
        assert not isinstance(value, Decimal)
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(model)


def test_absolute_urls_in_context_fail_closed() -> None:
    item = _item()
    item["methodology_context"]["proof_available"] = [
        "Prueba en https://example.com"
    ]

    with pytest.raises(
        StorefrontReadModelError,
        match="absolute URL",
    ):
        build_storefront_read_model([item])


def test_module_has_no_live_or_external_dependencies() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
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

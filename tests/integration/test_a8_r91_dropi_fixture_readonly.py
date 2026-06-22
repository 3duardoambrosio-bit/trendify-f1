from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from synapse.integration.dropi_fixture_readonly import (
    DropiFixtureValidationError,
    build_supplier_surface,
    dropi_product_to_financial_candidate,
    load_dropi_fixture,
    validate_dropi_fixture_payload,
)


FIXTURE_PATH = Path("tests/fixtures/dropi_supplier_products_nominal.json")
MODULE_PATH = Path("synapse/integration/dropi_fixture_readonly.py")


def test_a8_r91_dropi_fixture_loads_readonly_contract():
    payload = load_dropi_fixture(FIXTURE_PATH)

    assert payload["metadata"]["fixture_id"] == "dropi_supplier_products_nominal_v1"
    assert payload["supplier"]["platform"] == "dropi_fixture"
    assert payload["supplier"]["read_only"] is True
    assert len(payload["products"]) == 2

    for product in payload["products"]:
        assert product["read_only"] is True
        assert product["inventory"]["read_only"] is True
        assert product["inventory"]["inventory_reservation"] is False
        assert product["fulfillment"]["read_only"] is True
        assert product["fulfillment"]["order_placement_supported"] is False
        assert product["fulfillment"]["auto_fulfillment_enabled"] is False
        assert product["safety"]["live_dropi"] is False
        assert product["safety"]["external_writes"] is False
        assert product["safety"]["spend"] is False
        assert product["safety"]["fulfillment_automation"] is False
        assert product["safety"]["order_placement"] is False
        assert product["safety"]["inventory_reservation"] is False
        assert product["safety"]["operator_review_required"] is True


def test_a8_r91_dropi_supplier_surface_is_readonly_and_counts_stock():
    payload = load_dropi_fixture(FIXTURE_PATH)
    surface = build_supplier_surface(payload)

    assert surface["read_only"] is True
    assert surface["external_side_effects"] is False
    assert surface["platform"] == "dropi_fixture"
    assert surface["product_count"] == 2
    assert surface["in_stock_count"] == 1
    assert surface["low_stock_count"] == 1
    assert surface["out_of_stock_count"] == 0
    assert surface["operator_review_required"] is True

    assert surface["boundaries"] == {
        "live_dropi": False,
        "external_writes": False,
        "spend": False,
        "fulfillment_automation": False,
        "order_placement": False,
        "inventory_reservation": False,
    }


def test_a8_r91_dropi_product_adapter_outputs_financial_candidate_without_side_effects():
    payload = load_dropi_fixture(FIXTURE_PATH)
    product = payload["products"][0]

    candidate = dropi_product_to_financial_candidate(product, payload["supplier"])

    assert candidate["candidate_id"] == "dropi_fixture_product_001"
    assert candidate["source"] == "dropi_fixture"
    assert candidate["title"] == product["title"]
    assert candidate["supplier"]["platform"] == "dropi_fixture"
    assert candidate["costs"]["product_cost"] == "149.00"
    assert candidate["costs"]["shipping_cost_estimate"] == "89.00"
    assert candidate["costs"]["fees_estimate"] == "12.00"
    assert candidate["costs"]["currency"] == "MXN"
    assert candidate["inventory"]["inventory_reservation"] is False
    assert candidate["safety"]["external_side_effects"] is False
    assert candidate["safety"]["live_dropi"] is False
    assert candidate["safety"]["external_writes"] is False
    assert candidate["safety"]["order_placement"] is False
    assert candidate["operator_review_required"] is True


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (("safety", "live_dropi"), True, "safety.live_dropi must be false"),
        (("safety", "external_writes"), True, "safety.external_writes must be false"),
        (("safety", "spend"), True, "safety.spend must be false"),
        (("safety", "fulfillment_automation"), True, "safety.fulfillment_automation must be false"),
        (("safety", "order_placement"), True, "safety.order_placement must be false"),
        (("safety", "inventory_reservation"), True, "safety.inventory_reservation must be false"),
    ],
)
def test_a8_r91_dropi_fixture_rejects_root_safety_violations(path, value, error):
    payload = load_dropi_fixture(FIXTURE_PATH)
    mutated = copy.deepcopy(payload)
    cursor = mutated
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value

    with pytest.raises(DropiFixtureValidationError, match=error):
        validate_dropi_fixture_payload(mutated)


@pytest.mark.parametrize(
    ("product_index", "section", "field", "value", "error"),
    [
        (0, "fulfillment", "order_placement_supported", True, "order_placement_supported must be false"),
        (0, "fulfillment", "auto_fulfillment_enabled", True, "auto_fulfillment_enabled must be false"),
        (0, "inventory", "inventory_reservation", True, "inventory_reservation must be false"),
        (1, "safety", "live_dropi", True, "live_dropi must be false"),
        (1, "safety", "external_writes", True, "external_writes must be false"),
    ],
)
def test_a8_r91_dropi_fixture_rejects_product_side_effect_flags(
    product_index,
    section,
    field,
    value,
    error,
):
    payload = load_dropi_fixture(FIXTURE_PATH)
    mutated = copy.deepcopy(payload)
    mutated["products"][product_index][section][field] = value

    with pytest.raises(DropiFixtureValidationError, match=error):
        validate_dropi_fixture_payload(mutated)


def test_a8_r91_dropi_fixture_module_has_no_network_process_or_write_imports():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    forbidden_import_roots = {
        "requests",
        "httpx",
        "url" + "lib",
        "socket",
        "sub" + "process",
        "os",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in forbidden_import_roots
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            assert root not in forbidden_import_roots

    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden_text = [
        "requests" + ".",
        "httpx" + ".",
        "url" + "open",
        "socket" + ".",
        "sub" + "process",
        "inventory_reservation = true",
        "order_placement_supported = true",
        "auto_fulfillment_enabled = true",
    ]
    for token in forbidden_text:
        assert token not in source
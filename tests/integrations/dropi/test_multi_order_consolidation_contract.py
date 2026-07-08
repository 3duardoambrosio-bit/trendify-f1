import copy
import json

from synapse.integrations.dropi.multi_order_consolidation import (
    build_multi_order_consolidation_contract,
)
from synapse.integrations.dropi.order_forwarder import (
    build_dropi_payload_from_shopify,
)


BASE_ORDER = {
    "id": 123,
    "currency": "MXN",
    "email": "lalo@example.com",
    "customer": {"email": "lalo@example.com", "first_name": "Lalo", "last_name": "ACERO"},
    "shipping_address": {
        "name": "Lalo ACERO",
        "address1": "Calle 1",
        "city": "CDMX",
        "zip": "00000",
        "country": "MX",
    },
    "line_items": [{"sku": "SKU1", "title": "Prod 1", "quantity": 2, "price": "99.50"}],
    "total_price": "199.00",
}


def _make_order(order_id, *, sku="SKU1", quantity=1, price="99.50"):
    order = copy.deepcopy(BASE_ORDER)
    order["id"] = order_id
    order["line_items"] = [{"sku": sku, "title": f"Prod {sku}", "quantity": quantity, "price": price}]
    order["total_price"] = f"{float(price) * quantity:.2f}"
    return order


def test_build_multi_order_consolidation_contract_returns_none_for_single_order():
    contract = build_multi_order_consolidation_contract([_make_order(1)])

    assert contract is None


def test_build_multi_order_consolidation_contract_returns_none_for_different_currency():
    o1 = _make_order(1)
    o2 = _make_order(2)
    o2["currency"] = "USD"

    contract = build_multi_order_consolidation_contract([o1, o2])

    assert contract is None


def test_build_multi_order_consolidation_contract_returns_none_for_different_address():
    o1 = _make_order(1)
    o2 = _make_order(2)
    o2["shipping_address"]["address1"] = "Otra calle"

    contract = build_multi_order_consolidation_contract([o1, o2])

    assert contract is None


def test_build_multi_order_consolidation_contract_consolidates_compatible_orders():
    o1 = _make_order(123, sku="SKU1", quantity=2, price="99.50")
    o2 = _make_order(124, sku="SKU1", quantity=1, price="99.50")

    contract = build_multi_order_consolidation_contract(
        [o1, o2],
        metadata={"source": "shopify"},
    )

    assert contract["gate_id"] == "G-02_multi_order_consolidation"
    assert contract["consolidation_status"] == "ready_to_forward_consolidated_order"
    assert contract["order_count"] == 2
    assert contract["source_order_ids"] == ["123", "124"]
    assert contract["metadata"] == {"source": "shopify"}

    consolidated = contract["consolidated_order"]
    assert consolidated["order_id"] == "multi:123,124"
    assert consolidated["currency"] == "MXN"
    assert consolidated["consolidated"] is True
    assert consolidated["source_order_ids"] == ["123", "124"]
    assert consolidated["total_price"] == "298.50"
    assert len(consolidated["line_items"]) == 1
    assert consolidated["line_items"][0]["sku"] == "SKU1"
    assert consolidated["line_items"][0]["quantity"] == 3


def test_build_multi_order_consolidation_contract_output_feeds_dropi_payload_builder():
    o1 = _make_order(201, sku="SKU1", quantity=1, price="50.00")
    o2 = _make_order(202, sku="SKU2", quantity=2, price="30.00")

    contract = build_multi_order_consolidation_contract([o1, o2])
    consolidated = contract["consolidated_order"]
    payload = build_dropi_payload_from_shopify(consolidated)

    assert payload["external_id"] == "multi:201,202"
    assert payload["currency"] == "MXN"
    assert len(payload["items"]) == 2
    assert {item["sku"] for item in payload["items"]} == {"SKU1", "SKU2"}

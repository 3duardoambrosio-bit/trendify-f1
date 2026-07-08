from synapse.shopify.order_status_auto_reply import (
    build_order_status_auto_reply_contract,
)


def test_build_order_status_auto_reply_contract_returns_none_for_unknown_status():
    contract = build_order_status_auto_reply_contract("draft")

    assert contract is None


def test_build_order_status_auto_reply_contract_returns_contract_for_shipped():
    contract = build_order_status_auto_reply_contract(
        "shipped",
        order_id="ORDER-123",
        metadata={"source": "shopify"},
    )

    assert contract is not None
    assert contract["gate_id"] == "G-01_order_status_auto_reply"
    assert contract["channel"] == "whatsapp"
    assert contract["reason"] == "notify_customer_of_order_status"
    assert contract["order_status"] == "shipped"
    assert contract["reply_template"] == "order_status_shipped"
    assert contract["auto_reply"] is True
    assert contract["order_id"] == "ORDER-123"
    assert contract["metadata"] == {"source": "shopify"}


def test_build_order_status_auto_reply_contract_normalizes_alias():
    contract = build_order_status_auto_reply_contract("fulfilled")

    assert contract is not None
    assert contract["order_status"] == "shipped"
    assert contract["reply_template"] == "order_status_shipped"


def test_build_order_status_auto_reply_contract_requires_status():
    try:
        build_order_status_auto_reply_contract(None)
    except TypeError as exc:
        assert "order_status" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for missing order_status")

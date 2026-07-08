from synapse.shopify.cod_risk_scorer import build_cod_pre_confirmation_contract


def test_build_cod_pre_confirmation_contract_returns_none_for_non_cod():
    contract = build_cod_pre_confirmation_contract("card")

    assert contract is None


def test_build_cod_pre_confirmation_contract_returns_contract_for_cod():
    contract = build_cod_pre_confirmation_contract(
        "cod",
        order_id="ORDER-123",
        metadata={"source": "shopify"},
    )

    assert contract is not None
    assert contract["gate_id"] == "cod_pre_confirmation"
    assert contract["channel"] == "whatsapp"
    assert contract["reason"] == "confirm_cod_order_before_fulfillment"
    assert contract["payment_method"] == "cod"
    assert contract["requires_customer_confirmation"] is True
    assert contract["order_id"] == "ORDER-123"
    assert contract["metadata"] == {"source": "shopify"}


def test_build_cod_pre_confirmation_contract_accepts_cash_on_delivery_alias():
    contract = build_cod_pre_confirmation_contract("cash_on_delivery")

    assert contract is not None
    assert contract["payment_method"] == "cash_on_delivery"


def test_build_cod_pre_confirmation_contract_requires_payment_method():
    try:
        build_cod_pre_confirmation_contract(None)
    except TypeError as exc:
        assert "payment_method" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for missing payment_method")

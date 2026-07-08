from synapse.integrations.dropi.guarantee_flow import (
    build_dropi_guarantee_flow_contract,
)


def test_build_dropi_guarantee_flow_contract_returns_none_for_unsupported_issue():
    contract = build_dropi_guarantee_flow_contract(
        "buyer_remorse",
        order_id="ORD-1",
        supplier_payment_ready=True,
    )

    assert contract is None


def test_build_dropi_guarantee_flow_contract_waits_when_supplier_payment_not_ready():
    contract = build_dropi_guarantee_flow_contract(
        "damaged",
        order_id="ORD-2",
        supplier_payment_ready=False,
        resolution_preference="refund",
    )

    assert contract["gate_id"] == "C-02_dropi_guarantee_flow"
    assert contract["guarantee_status"] == "awaiting_supplier_payment_resolution"
    assert contract["supplier_payment_ready"] is False
    assert contract["issue_type"] == "damaged"
    assert contract["resolution_preference"] == "refund"


def test_build_dropi_guarantee_flow_contract_opens_case_when_ready():
    contract = build_dropi_guarantee_flow_contract(
        "missing_item",
        order_id="ORD-3",
        supplier_payment_ready=True,
        metadata={"source": "shopify"},
    )

    assert contract["gate_id"] == "C-02_dropi_guarantee_flow"
    assert contract["guarantee_status"] == "dropi_guarantee_case_ready"
    assert contract["supplier_payment_ready"] is True
    assert contract["issue_type"] == "missing_item"
    assert contract["resolution_preference"] == "replacement"
    assert contract["metadata"] == {"source": "shopify"}


def test_build_dropi_guarantee_flow_contract_normalizes_invalid_resolution_to_replacement():
    contract = build_dropi_guarantee_flow_contract(
        "defective",
        order_id="ORD-4",
        supplier_payment_ready=True,
        resolution_preference="exchange",
    )

    assert contract["resolution_preference"] == "replacement"


def test_build_dropi_guarantee_flow_contract_requires_valid_types():
    try:
        build_dropi_guarantee_flow_contract(
            None,
            order_id="ORD-5",
            supplier_payment_ready=True,
        )
    except TypeError as exc:
        assert "issue_type" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for missing issue_type")

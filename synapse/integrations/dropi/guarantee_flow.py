# V3GAP:C-02_dropi_guarantee_flow

from __future__ import annotations


def build_dropi_guarantee_flow_contract(
    issue_type,
    *,
    order_id,
    supplier_payment_ready,
    resolution_preference: str = "replacement",
    channel: str = "internal",
    metadata=None,
):
    """
    Build the minimal operational guarantee-flow contract for Dropi claims.
    This models when a valid guarantee case can be opened immediately versus
    when it must wait for supplier-payment state to be resolved first.
    """
    if issue_type is None:
        raise TypeError("issue_type is required")
    if order_id is None or str(order_id).strip() == "":
        raise TypeError("order_id is required")
    if not isinstance(supplier_payment_ready, bool):
        raise TypeError("supplier_payment_ready must be bool")

    normalized_issue = str(issue_type).strip().lower()
    supported_issues = {
        "damaged",
        "defective",
        "missing_item",
        "wrong_item",
        "not_received",
    }

    if normalized_issue not in supported_issues:
        return None

    normalized_resolution = str(resolution_preference).strip().lower()
    if normalized_resolution not in {"replacement", "refund"}:
        normalized_resolution = "replacement"

    if not supplier_payment_ready:
        contract = {
            "gate_id": "C-02_dropi_guarantee_flow",
            "channel": channel,
            "reason": "await_supplier_payment_resolution_before_guarantee_case",
            "order_id": str(order_id),
            "issue_type": normalized_issue,
            "resolution_preference": normalized_resolution,
            "guarantee_status": "awaiting_supplier_payment_resolution",
            "supplier_payment_ready": False,
        }
        if metadata is not None:
            contract["metadata"] = dict(metadata)
        return contract

    contract = {
        "gate_id": "C-02_dropi_guarantee_flow",
        "channel": channel,
        "reason": "open_dropi_guarantee_case",
        "order_id": str(order_id),
        "issue_type": normalized_issue,
        "resolution_preference": normalized_resolution,
        "guarantee_status": "dropi_guarantee_case_ready",
        "supplier_payment_ready": True,
    }

    if metadata is not None:
        contract["metadata"] = dict(metadata)

    return contract

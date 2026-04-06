from datetime import datetime, timedelta, timezone

from synapse.integrations.dropi.shipping_time_tracker import (
    build_dropi_shipping_time_tracker_contract,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, 0, 0, tzinfo=timezone.utc)


def test_build_dropi_shipping_time_tracker_contract_uses_delivery_time_days():
    contract = build_dropi_shipping_time_tracker_contract(
        {"product_id": "P-1", "delivery_time_days": 7},
        observed_at=_dt(1, 10),
    )

    assert contract["gate_id"] == "C-03_shipping_time_tracker"
    assert contract["tracking_status"] == "shipping_eta_ready"
    assert contract["shipping_eta_ready"] is True
    assert contract["shipping_source_key"] == "delivery_time_days"
    assert contract["shipping_days"] == 7.0
    assert contract["shipping_eta_at"] == (_dt(1, 10) + timedelta(days=7)).isoformat()
    assert contract["product_id"] == "P-1"


def test_build_dropi_shipping_time_tracker_contract_uses_shipping_days_alias():
    contract = build_dropi_shipping_time_tracker_contract(
        {"shipping_days": "5"},
        observed_at=_dt(2, 9),
    )

    assert contract["tracking_status"] == "shipping_eta_ready"
    assert contract["shipping_source_key"] == "shipping_days"
    assert contract["shipping_days"] == 5.0
    assert contract["shipping_eta_at"] == (_dt(2, 9) + timedelta(days=5)).isoformat()


def test_build_dropi_shipping_time_tracker_contract_returns_missing_when_no_eta_data():
    contract = build_dropi_shipping_time_tracker_contract(
        {"product_id": "P-2"},
        observed_at=_dt(3, 8),
        metadata={"source": "dropi"},
    )

    assert contract["tracking_status"] == "shipping_eta_missing"
    assert contract["shipping_eta_ready"] is False
    assert contract["shipping_source_key"] is None
    assert "shipping_eta_at" not in contract
    assert contract["metadata"] == {"source": "dropi"}


def test_build_dropi_shipping_time_tracker_contract_normalizes_negative_values():
    contract = build_dropi_shipping_time_tracker_contract(
        {"delivery_days": -3},
        observed_at=_dt(4, 11),
    )

    assert contract["tracking_status"] == "shipping_eta_ready"
    assert contract["shipping_days"] == 0.0
    assert contract["shipping_eta_at"] == _dt(4, 11).isoformat()


def test_build_dropi_shipping_time_tracker_contract_requires_valid_types():
    try:
        build_dropi_shipping_time_tracker_contract(
            ["not-a-dict"],
            observed_at=_dt(5, 12),
        )
    except TypeError as exc:
        assert "payload" in str(exc)
    else:
        raise AssertionError("TypeError was not raised for invalid payload")

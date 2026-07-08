# V3GAP:E-02_checkout_mx_fields

# V3GAP:E-02_checkout_mx_fields

from __future__ import annotations

import pytest

from synapse.shopify.checkout_mx import (
    CheckoutMxValidator,
    normalize_mx_phone,
    validate_mx_postal_code,
    validate_rfc,
)


def test_normalize_phone_10_digits():
    assert normalize_mx_phone("5512345678") == "+525512345678"


def test_normalize_phone_with_prefix():
    assert normalize_mx_phone("+525512345678") == "+525512345678"


def test_normalize_phone_invalid_length():
    with pytest.raises(ValueError):
        normalize_mx_phone("123")


def test_validate_postal_code_valid():
    assert validate_mx_postal_code("06600") is True


def test_validate_rfc_persona_fisica():
    assert validate_rfc("GARC850101AB3") is True


def test_validate_shipping_address_ok():
    v = CheckoutMxValidator()
    ok, errors = v.validate_shipping_address(
        {"postal_code": "06600", "state": "CIUDAD DE MEXICO", "phone": "5512345678"}
    )
    assert ok is True
    assert errors == []

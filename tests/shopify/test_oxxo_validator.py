from __future__ import annotations

from decimal import Decimal

from synapse.shopify.oxxo_validator import OxxoValidator


def test_oxxo_within_limit_allowed():
    v = OxxoValidator()
    r = v.validate_cart(Decimal("5000"))
    assert r.allowed is True
    assert r.reason == "ok"


def test_oxxo_exceeds_limit_blocked():
    v = OxxoValidator()
    r = v.validate_cart(Decimal("15000"))
    assert r.allowed is False
    assert "exceeds" in r.reason


def test_oxxo_below_minimum_blocked():
    v = OxxoValidator()
    r = v.validate_cart(Decimal("10"))
    assert r.allowed is False
    assert "below" in r.reason


def test_oxxo_exact_limit_allowed():
    v = OxxoValidator()
    r = v.validate_cart(Decimal("10000"))
    assert r.allowed is True
    assert r.reason == "ok"

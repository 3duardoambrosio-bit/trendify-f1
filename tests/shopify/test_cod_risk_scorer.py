# V3GAP:cod_risk_scoring

# V3GAP:A-04_cod_blacklist

from __future__ import annotations

from decimal import Decimal

import pytest

from synapse.shopify.cod_risk_scorer import CodRiskConfig, CodRiskScorer


def test_low_amount_low_risk():
    s = CodRiskScorer()
    r = s.score_order(amount_mxn=Decimal("500"), postal_code="06600", is_rural=False, previous_rejections=0)
    assert r.score < Decimal("0.40")
    assert r.cod_allowed is True
    assert r.risk_level == "low"


def test_high_amount_rural_high_risk():
    s = CodRiskScorer()
    r = s.score_order(amount_mxn=Decimal("1800"), postal_code="99999", is_rural=True, previous_rejections=2)
    assert r.score >= Decimal("0.70")
    assert r.cod_allowed is False
    assert r.risk_level == "high"


def test_over_max_amount_blocked():
    s = CodRiskScorer()
    r = s.score_order(amount_mxn=Decimal("3000"), postal_code="06600", is_rural=False, previous_rejections=0)
    assert r.cod_allowed is False
    assert r.reason.startswith("amount_exceeds")


def test_blacklisted_email_blocks_cod():
    s = CodRiskScorer(
        CodRiskConfig(
            blacklist_emails=("fraud@example.com",),
        )
    )
    r = s.score_order(
        amount_mxn=Decimal("500"),
        postal_code="06600",
        is_rural=False,
        previous_rejections=0,
        customer_email="Fraud@example.com",
    )
    assert r.score == Decimal("1")
    assert r.cod_allowed is False
    assert r.risk_level == "high"
    assert r.reason == "blacklisted_email"


def test_blacklisted_phone_blocks_cod():
    s = CodRiskScorer(
        CodRiskConfig(
            blacklist_phones=("5551234567",),
        )
    )
    r = s.score_order(
        amount_mxn=Decimal("500"),
        postal_code="06600",
        is_rural=False,
        previous_rejections=0,
        customer_phone="555-123-4567",
    )
    assert r.score == Decimal("1")
    assert r.cod_allowed is False
    assert r.risk_level == "high"
    assert r.reason == "blacklisted_phone"


def test_score_is_bounded_hypothesis_optional():
    hyp = pytest.importorskip("hypothesis")
    st = pytest.importorskip("hypothesis.strategies")

    @hyp.given(st.integers(min_value=0, max_value=5000), st.integers(min_value=0, max_value=10))
    def prop(amount_i: int, rej: int) -> None:
        s = CodRiskScorer()
        r = s.score_order(amount_mxn=Decimal(amount_i), postal_code="06600", is_rural=(amount_i % 2 == 0), previous_rejections=rej)
        assert Decimal("0") <= r.score <= Decimal("1")
        assert r.risk_level in ("low", "medium", "high")

    prop()

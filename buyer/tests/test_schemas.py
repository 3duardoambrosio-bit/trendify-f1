import pytest
from buyer.schemas import ProductSchema, BuyerDecisionSchema, Decision, ProductSource


def test_product_schema_creation():
    product = ProductSchema(
        product_id="test_123",
        external_id="ext_123",
        name="Test Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=150.0,
        source=ProductSource.CSV,
    )

    assert product.product_id == "test_123"
    assert product.margin_percentage is None
    assert product.suspicion_flags == []


def test_product_schema_with_optional_fields():
    product = ProductSchema(
        product_id="test_123",
        external_id="ext_123",
        name="Test Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=150.0,
        trust_score=8.5,
        supplier="Test Supplier",
        source=ProductSource.CSV,
        suspicion_flags=["test_flag"],
    )

    assert product.trust_score == 8.5
    assert product.supplier == "Test Supplier"
    assert "test_flag" in product.suspicion_flags


def test_buyer_decision_schema():
    decision = BuyerDecisionSchema(
        decision_id="dec_123",
        product_id="prod_123",
        decision=Decision.APPROVED,
        reasons=["good_margin", "high_trust"],
        scores={"margin_score": 0.33, "trust_score": 0.9},
        evaluated_at="2024-01-15T10:30:00Z",
    )

    assert decision.decision == Decision.APPROVED
    assert len(decision.reasons) == 2
    assert decision.scores["margin_score"] == 0.33


def test_product_validation():
    with pytest.raises(ValueError):
        ProductSchema(
            product_id="test",
            external_id="test",
            name="",  # Empty name should fail
            category="Test",
            cost_price=100.0,
            sale_price=150.0,
            source=ProductSource.CSV,
        )

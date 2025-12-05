import pytest
from buyer.scoring_rules import ScoringRules
from buyer.schemas import ProductSchema, ProductSource


@pytest.fixture
def scoring_rules():
    return ScoringRules()


@pytest.fixture
def sample_product():
    return ProductSchema(
        product_id="test_123",
        external_id="ext_123",
        name="Test Product",
        category="Electronics",
        cost_price=100.0,
        sale_price=150.0,
        trust_score=8.0,
        source=ProductSource.CSV,
    )


def test_calculate_margin(scoring_rules, sample_product):
    margin = scoring_rules.calculate_margin(sample_product)
    expected_margin = (150.0 - 100.0) / 150.0
    assert margin == pytest.approx(expected_margin)


def test_calculate_margin_zero_sale_price(scoring_rules):
    product = ProductSchema(
        product_id="test",
        external_id="test",
        name="Test",
        category="Test",
        cost_price=100.0,
        sale_price=0.0,
        source=ProductSource.CSV,
    )
    margin = scoring_rules.calculate_margin(product)
    assert margin == 0.0


def test_is_margin_acceptable(scoring_rules):
    assert scoring_rules.is_margin_acceptable(0.35) is True
    assert scoring_rules.is_margin_acceptable(0.25) is False


def test_is_trust_acceptable(scoring_rules):
    assert scoring_rules.is_trust_acceptable(7.0) is True
    assert scoring_rules.is_trust_acceptable(5.0) is False
    assert scoring_rules.is_trust_acceptable(None) is False


def test_is_price_suspicious(scoring_rules):
    product = ProductSchema(
        product_id="test",
        external_id="test",
        name="Test",
        category="Test",
        cost_price=100.0,
        sale_price=50.0,  # 0.5 ratio - suspicious
        source=ProductSource.CSV,
    )
    assert scoring_rules.is_price_suspicious(product) is True

    product.sale_price = 250.0  # 2.5 ratio - suspicious
    assert scoring_rules.is_price_suspicious(product) is True

    product.sale_price = 150.0  # 1.5 ratio - not suspicious
    assert scoring_rules.is_price_suspicious(product) is False


def test_evaluate_product(scoring_rules, sample_product):
    evaluation = scoring_rules.evaluate_product(sample_product)

    assert "margin" in evaluation
    assert "trust_score" in evaluation
    assert "suspicion_flags" in evaluation
    assert "composite_score" in evaluation
    assert isinstance(evaluation["suspicion_flags"], list)

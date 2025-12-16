from intelligence.factors import (
    FactorAnalysis,
    analyze_success_factors,
    generate_insights,
)


def _sample_products() -> list[dict]:
    # Dataset sintético:
    # - margin claramente mayor en exitosos
    # - rating casi igual (poca diferencia)
    products = [
        {"id": "p1", "was_successful": True,  "margin": 0.45, "rating": 4.6},
        {"id": "p2", "was_successful": True,  "margin": 0.40, "rating": 4.5},
        {"id": "p3", "was_successful": True,  "margin": 0.50, "rating": 4.7},
        {"id": "p4", "was_successful": False, "margin": 0.25, "rating": 4.4},
        {"id": "p5", "was_successful": False, "margin": 0.30, "rating": 4.5},
        {"id": "p6", "was_successful": False, "margin": 0.28, "rating": 4.6},
    ]
    return products


def test_analyze_success_factors_basic() -> None:
    products = _sample_products()
    analyses = analyze_success_factors(
        products,
        success_field="was_successful",
        factors=["margin", "rating"],
    )

    # Debemos tener análisis para margin y rating
    factors = {fa.factor for fa in analyses}
    assert "margin" in factors
    assert "rating" in factors

    margin_analysis = next(fa for fa in analyses if fa.factor == "margin")
    rating_analysis = next(fa for fa in analyses if fa.factor == "rating")

    # margin debe ser claramente mayor en exitosos
    assert margin_analysis.avg_in_successful > margin_analysis.avg_in_failed
    assert margin_analysis.difference > 0
    assert margin_analysis.sample_size == len(products)
    assert margin_analysis.direction == "higher_is_better"
    assert margin_analysis.is_significant is True

    # rating casi igual: diferencia muy pequeña → no significativo
    assert abs(rating_analysis.difference) < 0.2
    assert rating_analysis.is_significant is False


def test_generate_insights_filters_by_significance() -> None:
    products = _sample_products()
    analyses = analyze_success_factors(
        products,
        success_field="was_successful",
        factors=["margin", "rating"],
    )

    insights = generate_insights(analyses)

    # Solo margin debería generar insight, rating no
    assert any("margin" in msg for msg in insights)
    assert not any("rating" in msg for msg in insights)

    # Mensaje legible y con metadata básica
    margin_msg = next(msg for msg in insights if "margin" in msg)
    assert "productos exitosos tienen" in margin_msg
    assert "[" in margin_msg and "n=" in margin_msg

from decimal import Decimal

from marketing.creative_tracker import CreativeSelector, CreativeStats


def test_creative_stats_initial_values() -> None:
    stats = CreativeStats(creative_id="c1")

    assert stats.creative_id == "c1"
    assert stats.impressions == 0
    assert stats.clicks == 0
    assert stats.conversions == 0
    assert stats.spend == Decimal("0")
    assert stats.revenue == Decimal("0")

    assert stats.alpha == 1
    assert stats.beta == 1
    assert stats.estimated_cvr == 0.0
    assert stats.estimated_ctr == 0.0
    assert stats.estimated_roas == 0.0


def test_creative_stats_updates_and_metrics() -> None:
    stats = CreativeStats(creative_id="c1")

    # Registramos eventos
    stats.impressions += 10
    stats.clicks += 4
    stats.conversions += 1
    stats.add_spend(Decimal("20"))
    stats.add_revenue(Decimal("50"))

    assert stats.impressions == 10
    assert stats.clicks == 4
    assert stats.conversions == 1
    assert stats.spend == Decimal("20")
    assert stats.revenue == Decimal("50")

    # alpha = conversions + 1
    assert stats.alpha == 2
    # beta = (clicks - conversions) + 1 = (4 - 1) + 1 = 4
    assert stats.beta == 4

    assert 0.0 < stats.estimated_cvr <= 1.0
    assert 0.0 < stats.estimated_ctr <= 1.0
    assert stats.estimated_roas == 2.5  # 50 / 20


def test_selector_round_robin_selection() -> None:
    selector = CreativeSelector(use_thompson=False)
    creatives = ["c1", "c2", "c3"]

    selected = [selector.select_creative(creatives) for _ in range(6)]
    # Round-robin determinista
    assert selected == ["c1", "c2", "c3", "c1", "c2", "c3"]


def test_selector_records_events() -> None:
    selector = CreativeSelector()
    creatives = ["c1", "c2"]

    # Impresiones
    selector.record_impression("c1")
    selector.record_impression("c1")
    selector.record_impression("c2")

    # Clicks
    selector.record_click("c1")
    selector.record_click("c2")
    selector.record_click("c2")

    # Conversiones y revenue
    selector.record_conversion("c2", revenue=Decimal("30"))
    selector.record_spend("c2", amount=Decimal("10"))

    c1 = selector.stats["c1"]
    c2 = selector.stats["c2"]

    assert c1.impressions == 2
    assert c1.clicks == 1
    assert c1.conversions == 0

    assert c2.impressions == 1
    assert c2.clicks == 2
    assert c2.conversions == 1
    assert c2.revenue == Decimal("30")
    assert c2.spend == Decimal("10")
    assert c2.estimated_roas == 3.0


def test_selector_empty_available_returns_none() -> None:
    selector = CreativeSelector()
    assert selector.select_creative([]) is None


def test_selector_thompson_returns_valid_creatives() -> None:
    """
    Validamos que el camino de Thompson Sampling:
    - No truene.
    - Siempre devuelva IDs que estén en la lista disponible.
    """
    selector = CreativeSelector(use_thompson=True)
    creatives = ["c1", "c2", "c3"]

    # Le damos algo de historia para que alpha/beta no sean todos 1,1
    for _ in range(10):
        selector.record_impression("c1")
    for _ in range(5):
        selector.record_click("c1")
    for _ in range(3):
        selector.record_conversion("c1", revenue=Decimal("10"))

    for _ in range(20):
        selector.record_impression("c2")
    for _ in range(10):
        selector.record_click("c2")
    for _ in range(6):
        selector.record_conversion("c2", revenue=Decimal("20"))

    # c3 se queda casi sin datos
    selector.record_impression("c3")

    # Simplemente verificamos que, en modo Thompson,
    # siempre regrese un creative_id válido.
    selections = [selector.select_creative(creatives) for _ in range(50)]
    assert all(s in creatives for s in selections)
    assert any(s == "c1" for s in selections) or any(s == "c2" for s in selections)

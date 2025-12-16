from core.data_quality_guard import DataQualityGuard


def test_blocks_invalid_rating():
    dq = DataQualityGuard()
    r = dq.evaluate({"price_usd": 10, "shipping_usd_to_mexico": 0, "rating": 7, "reviews": 10, "sold": 100})
    assert r.action == "BLOCK"


def test_flags_suspicious_ratio():
    dq = DataQualityGuard()
    r = dq.evaluate({"price_usd": 12, "shipping_usd_to_mexico": 0, "rating": 4.8, "reviews": 900, "sold": 1000})
    assert r.action in ("VERIFY", "BLOCK")
    assert "reviews_to_sold_suspicious" in r.flags
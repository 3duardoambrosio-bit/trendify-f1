import pytest
from core.evidence_schema_v1 import EvidenceV1


def test_requires_url():
    with pytest.raises(ValueError):
        EvidenceV1.from_dict("r004", {"price_usd": 10})


def test_parses_fields():
    e = EvidenceV1.from_dict("r003", {"supplier_url":"https://x", "price_usd": 28.6, "shipping_usd_to_mexico": 0, "rating": 4.9, "reviews": 850, "sold": 5000, "recommended_variant":"i-wok"})
    assert e.product_id == "r003"
    assert e.sold == 5000
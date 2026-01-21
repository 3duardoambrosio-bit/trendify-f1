import pytest

from synapse.meta import (
    build_utm_content,
    parse_utm_content,
    build_meta_campaign_payload,
    MetaPayloadError,
    UTMError,
)


def test_utm_roundtrip():
    s = build_utm_content("01", "dolor", "1")
    parts = parse_utm_content(s)
    assert parts["hook_id"] == "01"
    assert parts["angle"] == "dolor"
    assert parts["variant"] == "1"


def test_utm_invalid_raises():
    with pytest.raises(UTMError):
        parse_utm_content("NOPE")


def test_meta_payload_valid():
    p = build_meta_campaign_payload(
        product_id="34357",
        product_name="Audifonos",
        budget_usd=10,
    )
    assert p["platform"] == "meta"
    assert p["campaign"]["objective"] == "OUTCOME_SALES"


def test_meta_payload_invalid_objective():
    with pytest.raises(MetaPayloadError):
        build_meta_campaign_payload(
            product_id="1",
            product_name="X",
            objective="NOPE",
            budget_usd=10,
        )

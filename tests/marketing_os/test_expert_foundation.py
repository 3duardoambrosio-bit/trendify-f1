from decimal import Decimal

from synapse.marketing_os.expert_foundation import (
    MarketingExpertPack,
    build_marketing_expert_pack,
    pack_to_dict,
)


def _sample_product():
    return {
        "title": "Lampara LED para escritorio",
        "category": "electronics/home office",
        "pain": "trabajar de noche con poca luz y cansancio visual",
        "benefit": "mejorar la iluminacion del escritorio",
        "price_mxn": "749",
    }


def test_builds_complete_expert_pack_contract():
    pack = build_marketing_expert_pack(_sample_product(), daily_budget_mxn=Decimal("300"))

    assert isinstance(pack, MarketingExpertPack)
    assert pack.product_name == "Lampara LED para escritorio"
    assert pack.offer.promise
    assert pack.audience.segment
    assert len(pack.hooks) == 3
    assert pack.campaign.platform == "meta-dry-run"
    assert len(pack.campaign.adsets) == 1
    assert len(pack.campaign.adsets[0].ads) == 3
    assert pack.stop_rules.max_daily_spend_mxn == Decimal("300")


def test_pack_is_operator_in_control_and_never_live():
    pack = build_marketing_expert_pack(_sample_product())
    data = pack_to_dict(pack)

    assert "dry_run_only" in data["boundaries"]
    assert "operator_in_control" in data["boundaries"]
    assert "no_live_writes" in data["boundaries"]
    assert "no_automatic_spend" in data["boundaries"]

    joined_actions = " ".join(data["operator_actions"]).lower()
    assert "validar proveedor" in joined_actions
    assert "registrar gasto" in joined_actions


def test_campaign_structure_is_campaign_adset_ad():
    pack = build_marketing_expert_pack(_sample_product())
    data = pack_to_dict(pack)

    campaign = data["campaign"]
    assert campaign["campaign_name"]
    assert campaign["objective"] == "first-signal-validation"
    assert len(campaign["adsets"]) == 1

    adset = campaign["adsets"][0]
    assert adset["name"].startswith("ADSET-")
    assert len(adset["ads"]) == 3

    for ad in adset["ads"]:
        assert ad["name"].startswith("AD-")
        assert ad["primary_text"]
        assert ad["headline"]
        assert "sin claims absolutos" in ad["compliance_note"]


def test_hooks_are_not_generic_templates():
    pack = build_marketing_expert_pack(_sample_product())
    contents = [h.content for h in pack.hooks]
    angles = {h.angle for h in pack.hooks}
    mechanisms = {h.mechanism for h in pack.hooks}

    assert len(set(contents)) == 3
    assert len(angles) == 3
    assert len(mechanisms) >= 3

    forbidden = ("{", "}", "placeholder", "template")
    for content in contents:
        lower = content.lower()
        assert len(content) > 45
        assert not any(f in lower for f in forbidden)


def test_claim_warning_flags_absolute_language_from_input():
    product = {
        "title": "Crema milagro garantizada",
        "category": "beauty",
        "pain": "manchas",
        "benefit": "cura 100% garantizada",
        "price_mxn": "499",
    }

    pack = build_marketing_expert_pack(product)

    assert pack.warnings
    assert any(w.startswith("claims_risk:") for w in pack.warnings)


def test_serializer_is_json_friendly():
    pack = build_marketing_expert_pack(_sample_product())
    data = pack_to_dict(pack)

    assert isinstance(data["campaign"]["daily_budget_mxn"], str)
    assert isinstance(data["stop_rules"]["max_daily_spend_mxn"], str)
    assert isinstance(data["hooks"], list)
    assert isinstance(data["operator_actions"], list)
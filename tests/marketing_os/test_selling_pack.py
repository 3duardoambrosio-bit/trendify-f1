from decimal import Decimal

from synapse.marketing_os.selling_pack import (
    FirstSellingPack,
    build_first_selling_pack,
    build_first_selling_pack_dict,
    first_selling_pack_to_dict,
)


def _product():
    return {
        "product_id": "KC01_GOOD_MARGIN_SAFE_CLAIM",
        "title": "Masajeador Cervical Inteligente TENS",
        "category": "wellness/fitness",
        "target_audience": "Personas que trabajan de noche frente a monitor.",
        "pain": "tension cervical despues de trabajar muchas horas frente a pantalla",
        "benefit": "reducir friccion diaria con una rutina practica de relajacion",
        "price_mxn": "799",
    }


def _decision():
    return {
        "final_outcome": "GO",
        "final_decision": "APPROVE",
        "confidence": 0.87,
        "blocked_reasons": [],
        "reasons": ("margin_ok", "claims_safe", "operator_review_required"),
        "recommended_actions": ("build_brief", "review_claims", "dry_run_only"),
        "selling_price_mxn": "799",
    }


def test_build_first_selling_pack_consumes_brief_and_expert_foundation():
    pack = build_first_selling_pack(
        _product(),
        _decision(),
        daily_budget_mxn=Decimal("300"),
    )

    assert isinstance(pack, FirstSellingPack)
    assert pack.product_id == "KC01_GOOD_MARGIN_SAFE_CLAIM"
    assert "Masajeador Cervical" in pack.product_name

    assert pack.marketing_brief
    assert pack.expert_pack
    assert pack.expert_pack["campaign"]["platform"] == "meta-dry-run"
    assert pack.expert_pack["campaign"]["adsets"]
    assert pack.expert_pack["campaign"]["adsets"][0]["ads"]

    assert pack.ready_for_operator_review is True


def test_first_selling_pack_keeps_release_safety_boundaries():
    data = build_first_selling_pack_dict(_product(), _decision())

    assert "dry_run_only" in data["boundaries"]
    assert "operator_in_control" in data["boundaries"]
    assert "no_live_writes" in data["boundaries"]
    assert "no_automatic_spend" in data["boundaries"]
    assert "no_fulfillment_automation" in data["boundaries"]

    assert data["expert_pack"]["campaign"]["platform"] == "meta-dry-run"


def test_first_selling_pack_serialization_is_json_ready():
    pack = build_first_selling_pack(_product(), _decision())
    data = first_selling_pack_to_dict(pack)

    assert isinstance(data["marketing_brief"], dict)
    assert isinstance(data["expert_pack"], dict)
    assert isinstance(data["boundaries"], list)
    assert isinstance(data["warnings"], list)
    assert isinstance(data["ready_for_operator_review"], bool)


def test_first_selling_pack_surfaces_claim_warnings():
    product = dict(_product())
    product["title"] = "Crema milagro garantizada"
    product["benefit"] = "cura 100% garantizada"

    data = build_first_selling_pack_dict(product, _decision())

    assert data["warnings"]
    assert any(w.startswith("claims_risk:") for w in data["warnings"])
from decimal import Decimal

from synapse.marketing_os import (
    MarketingExpertPack,
    build_marketing_expert_pack,
    pack_to_dict,
)


def test_expert_foundation_is_available_from_marketing_os_surface():
    pack = build_marketing_expert_pack(
        {
            "title": "Lampara LED para escritorio",
            "category": "electronics/home office",
            "pain": "trabajar de noche con poca luz",
            "benefit": "mejorar la iluminacion del escritorio",
            "price_mxn": "749",
        },
        daily_budget_mxn=Decimal("300"),
    )

    assert isinstance(pack, MarketingExpertPack)

    data = pack_to_dict(pack)
    assert data["campaign"]["platform"] == "meta-dry-run"
    assert data["campaign"]["adsets"]
    assert data["campaign"]["adsets"][0]["ads"]
    assert "operator_in_control" in data["boundaries"]
    assert "no_live_writes" in data["boundaries"]
    assert "no_automatic_spend" in data["boundaries"]


def test_public_surface_does_not_authorize_live_execution():
    pack = build_marketing_expert_pack({"title": "Producto X"})
    data = pack_to_dict(pack)

    joined = " ".join(data["boundaries"]).lower()
    assert "dry_run_only" in joined
    assert "no_live_writes" in joined
    assert "no_automatic_spend" in joined

    actions = " ".join(data["operator_actions"]).lower()
    assert "validar proveedor" in actions
    assert "registrar gasto" in actions
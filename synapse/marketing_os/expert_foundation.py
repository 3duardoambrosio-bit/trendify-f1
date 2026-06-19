"""Marketing Expert Foundation V1.

Local-only expert planning contract for operator-in-control selling.

This module does not call external APIs, does not authorize spend, and does not
create live campaigns. It turns a product candidate and its evaluation context
into a deterministic expert marketing pack that an operator can review.

The contract is intentionally concrete:
angle -> offer -> audience -> hooks -> campaign/adset/ad structure -> stop rules
-> operator actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


DISALLOWED_ABSOLUTE_CLAIMS = (
    "garantizado",
    "garantizada",
    "cura",
    "cura ",
    "curar",
    "milagro",
    "100%",
    "sin riesgo",
    "resultados asegurados",
    "antes y despues",
    "antes y después",
)


@dataclass(frozen=True)
class ExpertAudience:
    """Concrete first-test audience definition."""

    segment: str
    awareness_level: str
    buying_trigger: str
    exclusion: str


@dataclass(frozen=True)
class ExpertOffer:
    """Operator-reviewable offer recommendation."""

    promise: str
    price_anchor: str
    risk_reversal: str
    urgency: str


@dataclass(frozen=True)
class ExpertHook:
    """Hook tied to an angle and mechanism, not just a line of copy."""

    angle: str
    mechanism: str
    content: str
    proof_need: str


@dataclass(frozen=True)
class ExpertAd:
    """Dry-run ad unit."""

    name: str
    hook: ExpertHook
    primary_text: str
    headline: str
    compliance_note: str


@dataclass(frozen=True)
class ExpertAdSet:
    """Dry-run ad set unit."""

    name: str
    audience: ExpertAudience
    budget_mxn: Decimal
    ads: tuple[ExpertAd, ...]


@dataclass(frozen=True)
class ExpertCampaignStructure:
    """Meta-style structure without live mutation."""

    platform: str
    campaign_name: str
    objective: str
    daily_budget_mxn: Decimal
    adsets: tuple[ExpertAdSet, ...]


@dataclass(frozen=True)
class ExpertStopRules:
    """First-test manual stop rules."""

    max_daily_spend_mxn: Decimal
    first_review_after_spend_mxn: Decimal
    kill_if_no_signal_after_mxn: Decimal
    pause_if_claims_risk: bool = True


@dataclass(frozen=True)
class MarketingExpertPack:
    """Complete local expert pack for operator-in-control execution."""

    product_name: str
    category: str
    positioning: str
    offer: ExpertOffer
    audience: ExpertAudience
    hooks: tuple[ExpertHook, ...]
    campaign: ExpertCampaignStructure
    stop_rules: ExpertStopRules
    operator_actions: tuple[str, ...]
    boundaries: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _money(value: Any, fallback: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(fallback)


def _first_present(data: Mapping[str, Any], keys: tuple[str, ...], fallback: str = "") -> str:
    for key in keys:
        if key in data and _text(data.get(key)):
            return _text(data.get(key))
    return fallback


def _detect_claim_warnings(*texts: str) -> tuple[str, ...]:
    joined = " ".join(t.lower() for t in texts if t)
    warnings = []
    for claim in DISALLOWED_ABSOLUTE_CLAIMS:
        if claim in joined:
            warnings.append(f"claims_risk:{claim}")
    return tuple(dict.fromkeys(warnings))


def _category_angle(category: str) -> tuple[str, str, str]:
    c = category.lower()

    if any(k in c for k in ("beauty", "belleza", "skin", "cuidado")):
        return (
            "rutina visible sin promesas absolutas",
            "mecanismo de uso diario y mejora percibida",
            "personas que ya compran cuidado personal pero dudan de productos milagro",
        )

    if any(k in c for k in ("pet", "mascota", "perro", "gato")):
        return (
            "tranquilidad del dueño",
            "mecanismo de cuidado preventivo y conveniencia",
            "dueños de mascota con ansiedad por bienestar y tiempo limitado",
        )

    if any(k in c for k in ("home", "hogar", "cocina", "organizador")):
        return (
            "orden y ahorro de fricción diaria",
            "mecanismo de simplificación en casa",
            "personas con casa/departamento que compran soluciones prácticas",
        )

    if any(k in c for k in ("fitness", "gym", "deporte", "salud")):
        return (
            "progreso medible sin atajos falsos",
            "mecanismo de constancia y soporte práctico",
            "personas que entrenan o quieren empezar sin comprar humo",
        )

    if any(k in c for k in ("electronics", "tech", "audio", "gadget", "electronica", "electrónica")):
        return (
            "mejora práctica inmediata",
            "mecanismo de conveniencia tecnológica",
            "compradores de gadgets que buscan utilidad real, no novedad vacía",
        )

    return (
        "problema cotidiano con solución concreta",
        "mecanismo de reducción de fricción",
        "compradores con dolor claro y baja tolerancia a promesas genéricas",
    )


def build_marketing_expert_pack(
    product: Mapping[str, Any],
    financials: Mapping[str, Any] | None = None,
    *,
    daily_budget_mxn: Decimal | str | int = Decimal("300"),
) -> MarketingExpertPack:
    """Build a deterministic expert marketing pack.

    Inputs are plain mappings to keep the contract easy to call from existing
    SYNAPSE flows without coupling this foundation to live connectors.
    """

    financials = financials or {}

    product_name = _first_present(product, ("title", "name", "product_name"), "Producto sin nombre")
    category = _first_present(product, ("category", "niche", "product_type"), "general")
    pain = _first_present(product, ("pain", "problem", "customer_pain"), "dolor cotidiano no especificado")
    benefit = _first_present(product, ("benefit", "main_benefit", "value_prop"), "beneficio práctico")
    price = _money(
        product.get("price_mxn")
        or product.get("price")
        or financials.get("price_mxn")
        or financials.get("selling_price_mxn"),
        "0",
    )
    budget = _money(daily_budget_mxn, "300")
    if budget <= 0:
        budget = Decimal("300")

    angle, mechanism, default_segment = _category_angle(category)

    audience = ExpertAudience(
        segment=default_segment,
        awareness_level="problem-aware",
        buying_trigger=f"nota el problema: {pain}",
        exclusion="excluir compradores que esperan resultados garantizados o promesas milagro",
    )

    offer = ExpertOffer(
        promise=f"{benefit} para resolver {pain} sin prometer resultados absolutos",
        price_anchor=(f"precio de prueba sugerido: ${price} MXN" if price > 0 else "precio pendiente de validar"),
        risk_reversal="compra revisada por operador: proveedor, stock, margen y claims antes de publicar",
        urgency="urgencia suave: resolver hoy una fricción que ya se repite cada semana",
    )

    hooks = (
        ExpertHook(
            angle=angle,
            mechanism=mechanism,
            content=f"Si {pain} ya te cuesta tiempo o dinero, {product_name} promete una solución práctica sin humo.",
            proof_need="mostrar uso real, tamaño, material, entrega y limitaciones",
        ),
        ExpertHook(
            angle="comparación contra seguir igual",
            mechanism="costo de inacción",
            content=f"Seguir tolerando {pain} también tiene costo. La pregunta es si {product_name} lo reduce de forma simple.",
            proof_need="comparar situación antes/después sin prometer transformación garantizada",
        ),
        ExpertHook(
            angle="objeción principal",
            mechanism="riesgo percibido",
            content=f"Antes de comprar {product_name}, revisa si realmente encaja contigo: uso, precio, entrega y expectativa.",
            proof_need="explicar para quién sí y para quién no",
        ),
    )

    ads = tuple(
        ExpertAd(
            name=f"AD-{idx:02d}-{hook.angle[:18].upper()}",
            hook=hook,
            primary_text=hook.content,
            headline=f"{product_name[:32]} | solución práctica",
            compliance_note="sin claims absolutos; operador debe revisar evidencia antes de publicar",
        )
        for idx, hook in enumerate(hooks, 1)
    )

    adset = ExpertAdSet(
        name="ADSET-01-problem-aware-first-test",
        audience=audience,
        budget_mxn=budget,
        ads=ads,
    )

    campaign = ExpertCampaignStructure(
        platform="meta-dry-run",
        campaign_name=f"R86-{product_name[:40]}-first-test",
        objective="first-signal-validation",
        daily_budget_mxn=budget,
        adsets=(adset,),
    )

    stop_rules = ExpertStopRules(
        max_daily_spend_mxn=budget,
        first_review_after_spend_mxn=max(Decimal("100"), budget / Decimal("3")),
        kill_if_no_signal_after_mxn=max(Decimal("150"), budget / Decimal("2")),
    )

    boundaries = (
        "dry_run_only",
        "operator_in_control",
        "no_live_writes",
        "no_automatic_spend",
        "no_fulfillment_automation",
        "claims_require_operator_review",
    )

    operator_actions = (
        "validar proveedor, stock, costo, tiempos y restricciones antes de publicar",
        "revisar que los hooks no prometan cura, garantía o resultado absoluto",
        "crear campaña manualmente solo si el operador aprueba el pack",
        "registrar gasto, CTR, CPC, conversiones y comentarios reales después de la prueba",
        "detener la prueba si se activa cualquier riesgo de claims o presupuesto",
    )

    warnings = _detect_claim_warnings(product_name, category, pain, benefit, *(h.content for h in hooks))

    return MarketingExpertPack(
        product_name=product_name,
        category=category,
        positioning=f"{angle}: {mechanism}",
        offer=offer,
        audience=audience,
        hooks=hooks,
        campaign=campaign,
        stop_rules=stop_rules,
        operator_actions=operator_actions,
        boundaries=boundaries,
        warnings=warnings,
    )


def pack_to_dict(pack: MarketingExpertPack) -> dict[str, Any]:
    """Serialize the expert pack into JSON-friendly primitives."""

    return {
        "product_name": pack.product_name,
        "category": pack.category,
        "positioning": pack.positioning,
        "offer": {
            "promise": pack.offer.promise,
            "price_anchor": pack.offer.price_anchor,
            "risk_reversal": pack.offer.risk_reversal,
            "urgency": pack.offer.urgency,
        },
        "audience": {
            "segment": pack.audience.segment,
            "awareness_level": pack.audience.awareness_level,
            "buying_trigger": pack.audience.buying_trigger,
            "exclusion": pack.audience.exclusion,
        },
        "hooks": [
            {
                "angle": h.angle,
                "mechanism": h.mechanism,
                "content": h.content,
                "proof_need": h.proof_need,
            }
            for h in pack.hooks
        ],
        "campaign": {
            "platform": pack.campaign.platform,
            "campaign_name": pack.campaign.campaign_name,
            "objective": pack.campaign.objective,
            "daily_budget_mxn": str(pack.campaign.daily_budget_mxn),
            "adsets": [
                {
                    "name": adset.name,
                    "budget_mxn": str(adset.budget_mxn),
                    "audience": {
                        "segment": adset.audience.segment,
                        "awareness_level": adset.audience.awareness_level,
                        "buying_trigger": adset.audience.buying_trigger,
                        "exclusion": adset.audience.exclusion,
                    },
                    "ads": [
                        {
                            "name": ad.name,
                            "primary_text": ad.primary_text,
                            "headline": ad.headline,
                            "hook_angle": ad.hook.angle,
                            "hook_mechanism": ad.hook.mechanism,
                            "compliance_note": ad.compliance_note,
                        }
                        for ad in adset.ads
                    ],
                }
                for adset in pack.campaign.adsets
            ],
        },
        "stop_rules": {
            "max_daily_spend_mxn": str(pack.stop_rules.max_daily_spend_mxn),
            "first_review_after_spend_mxn": str(pack.stop_rules.first_review_after_spend_mxn),
            "kill_if_no_signal_after_mxn": str(pack.stop_rules.kill_if_no_signal_after_mxn),
            "pause_if_claims_risk": pack.stop_rules.pause_if_claims_risk,
        },
        "operator_actions": list(pack.operator_actions),
        "boundaries": list(pack.boundaries),
        "warnings": list(pack.warnings),
    }
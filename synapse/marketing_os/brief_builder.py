# synapse/marketing_os/brief_builder.py
"""Deterministic structured brief builder for A8-R66.

Converts a product/evaluation record into a textual Marketing OS brief.

Scope boundaries:
- no external reads;
- no external writes;
- no spend;
- no image/video generation;
- no UI coupling;
- no mutation of the evaluation engine.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from synapse.cli._blacklist import GENERIC_BLACKLIST

from .brief_schema import (
    SCHEMA_VERSION,
    AntiNpcChecks,
    BriefItem,
    ClaimSafetyNotes,
    MarketingBrief,
    PermissionDecision,
    ScriptVariant,
)


_CLAIM_RISK_TERMS: tuple[str, ...] = (
    "cura",
    "curar",
    "tratamiento",
    "médico",
    "medico",
    "clínico",
    "clinico",
    "cofepris",
    "fda",
    "100%",
    "tens",
    "garantizado",
    "resultados",
    "doctor",
    "doctores",
    "legal",
    "accidente",
    "evidencia legal",
)

_HEALTH_HINTS: tuple[str, ...] = (
    "salud",
    "bienestar",
    "tens",
    "cuello",
    "cervical",
    "masaje",
    "masajeador",
    "uv",
    "biométrico",
    "biometrico",
    "recuperación",
    "recuperacion",
    "dolor",
)

_SECURITY_HINTS: tuple[str, ...] = (
    "seguridad",
    "dashcam",
    "casco",
    "moto",
    "accidente",
    "intercomunicador",
)

_BLOCK_TOKENS: tuple[str, ...] = (
    "block",
    "blocked",
    "deny",
    "denied",
    "fail",
    "failed",
    "rejected",
    "dangerous",
)

_HOLD_TOKENS: tuple[str, ...] = (
    "hold",
    "needs_review",
    "review",
    "paused",
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _norm(value: Any) -> str:
    return _strip_accents(str(value or "")).lower().strip()


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or fallback).strip()
    return re.sub(r"\s+", " ", text)


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _mapping_from_any(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        data = value.to_dict()
        if isinstance(data, Mapping):
            result = dict(data)
        else:
            result = {}
    else:
        result = {}

    for attr in (
        "product_id",
        "name",
        "category",
        "price",
        "cost",
        "description",
        "target_audience",
        "use_cases",
        "unique_features",
        "known_objections",
        "competitor_weaknesses",
    ):
        if hasattr(value, attr) and attr not in result:
            result[attr] = getattr(value, attr)

    return result


def _first(data: Mapping[str, Any], *keys: str, fallback: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return fallback


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(_clean_text(item) for item in value if _clean_text(item))
    return (_clean_text(value),) if _clean_text(value) else ()


def _money(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _margin_pct(price: float | None, cost: float | None) -> float | None:
    if price is None or cost is None or price <= 0:
        return None
    return round(((price - cost) / price) * 100, 1)


def _infer_audience(product: Mapping[str, Any]) -> str:
    explicit = _clean_text(_first(product, "target_audience", "audience", fallback=""))
    if explicit:
        return explicit

    category_blob = _norm(" ".join([
        _clean_text(_first(product, "category", fallback="")),
        _clean_text(_first(product, "name", "product_name", fallback="")),
        _clean_text(_first(product, "description", fallback="")),
    ]))

    if any(token in category_blob for token in ("mascota", "perro", "gato", "pet")):
        return "Dueños de mascotas en MX que quieren reducir fricción diaria de cuidado sin depender de recordatorios manuales."
    if any(token in category_blob for token in ("moto", "casco", "dashcam")):
        return "Motociclistas urbanos en MX que usan la moto como transporte real y valoran control, registro y comunicación en trayectos."
    if any(token in category_blob for token in ("monitor", "led", "setup", "periferico", "periférico")):
        return "Personas que trabajan o estudian muchas horas frente a pantalla y buscan mejorar su estación sin rehacer todo su setup."
    if any(token in category_blob for token in ("anillo", "biometrico", "biométrico", "wearable")):
        return "Personas que entrenan, trabajan o estudian con alta carga y quieren observar hábitos de recuperación sin usar un reloj grande."
    if any(token in category_blob for token in ("cuello", "cervical", "tens", "masaje")):
        return "Personas en MX con jornadas largas frente a pantalla que buscan pausas de bienestar no médico durante el día."

    return "Compradores digitales en MX que evalúan utilidad concreta, precio defendible y uso frecuente antes de comprar."


def _infer_enemy(product: Mapping[str, Any]) -> str:
    blob = _norm(" ".join([
        _clean_text(_first(product, "category", fallback="")),
        _clean_text(_first(product, "name", "product_name", fallback="")),
        _clean_text(_first(product, "description", fallback="")),
    ]))

    if any(token in blob for token in ("cuello", "cervical", "tens", "masaje")):
        return "tensión acumulada durante jornadas largas"
    if any(token in blob for token in ("moto", "casco", "dashcam")):
        return "viajes urbanos donde faltan registro y comunicación"
    if any(token in blob for token in ("mascota", "perro", "gato", "pet")):
        return "rutinas de hidratación que dependen de estar pendiente todo el día"
    if any(token in blob for token in ("monitor", "led", "setup")):
        return "fatiga visual y reflejos en sesiones largas"
    if any(token in blob for token in ("anillo", "wearable", "biometrico", "biométrico")):
        return "decidir a ciegas cuándo descansar o empujar más"

    return "fricción diaria que el producto puede reducir de forma práctica"


def _feature(product: Mapping[str, Any]) -> str:
    features = _as_tuple(_first(product, "unique_features", "features", fallback=()))
    if features:
        return features[0]

    description = _clean_text(_first(product, "description", fallback=""))
    if description:
        return description[:90]

    return "uso práctico en rutina diaria"


def _claim_safety(product: Mapping[str, Any], decision: Mapping[str, Any]) -> ClaimSafetyNotes:
    blob = _norm(" ".join([
        _clean_text(_first(product, "name", "product_name", fallback="")),
        _clean_text(_first(product, "category", fallback="")),
        _clean_text(_first(product, "description", fallback="")),
        _clean_text(_first(decision, "reason", "reasons", "final_outcome", "outcome", fallback="")),
    ]))

    detected = tuple(term for term in _CLAIM_RISK_TERMS if _norm(term) in blob)
    is_health = any(_norm(term) in blob for term in _HEALTH_HINTS)
    is_security = any(_norm(term) in blob for term in _SECURITY_HINTS)

    notes: list[str] = [
        "Mantener el brief como texto estratégico; no afirmar pruebas, certificaciones o resultados absolutos.",
        "Separar beneficios de uso observables de promesas de desempeño no verificadas.",
    ]

    posture = "standard_commerce_claims"

    if is_health:
        posture = "restricted_wellness_claims"
        notes.append("Para bienestar, hablar de rutina, comodidad y pausa; no presentar el producto como tratamiento.")
    if is_security:
        posture = "restricted_security_claims"
        notes.append("Para seguridad, hablar de registro, visibilidad y comunicación; no prometer protección total ni resultado legal.")

    if detected:
        notes.append("Hay términos sensibles en el input; el brief debe tratarlos como restricciones, no como claims de venta.")

    return ClaimSafetyNotes(
        posture=posture,
        notes=tuple(notes),
        detected_risk_terms=tuple(sorted(set(detected))),
    )


def _permission(decision: Mapping[str, Any]) -> tuple[PermissionDecision, tuple[str, ...]]:
    outcome = _clean_text(_first(decision, "final_outcome", "outcome", "permission_gate", "status", fallback="allowed"))
    outcome_norm = _norm(outcome)
    score = _money(_first(decision, "score", fallback=None))
    threshold = _money(_first(decision, "threshold", fallback=None))

    raw_reasons = _first(decision, "reasons", "reason", "blocked_reasoning", fallback=())
    reasons = _as_tuple(raw_reasons)

    if any(token in outcome_norm for token in _BLOCK_TOKENS):
        status = "blocked"
    elif any(token in outcome_norm for token in _HOLD_TOKENS):
        status = "review_required"
    else:
        status = "allowed"

    if status == "blocked" and not reasons:
        reasons = ("La decisión heredada bloquea activación; el brief se conserva sólo como análisis textual.",)
    if status == "review_required" and not reasons:
        reasons = ("La decisión heredada requiere revisión antes de cualquier activación externa.",)

    blocked_reasoning = reasons if status in {"blocked", "review_required"} else ()

    return (
        PermissionDecision(status=status, score=score, threshold=threshold, reasons=reasons),
        blocked_reasoning,
    )


def _content_for_anti_npc(
    hooks: tuple[BriefItem, ...],
    scripts: tuple[ScriptVariant, ...],
    ctas: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []

    for idx, hook in enumerate(hooks, start=1):
        rows.append((f"hooks[{idx}]", hook.text))

    for idx, script in enumerate(scripts, start=1):
        rows.append((f"scripts[{idx}]", " ".join(script.beats) + " " + script.cta))

    for idx, cta in enumerate(ctas, start=1):
        rows.append((f"ctas[{idx}]", cta))

    return tuple(rows)


def _anti_npc(
    hooks: tuple[BriefItem, ...],
    scripts: tuple[ScriptVariant, ...],
    ctas: tuple[str, ...],
) -> AntiNpcChecks:
    banned: set[str] = set()
    checked_sections: list[str] = []

    for section, text in _content_for_anti_npc(hooks, scripts, ctas):
        checked_sections.append(section)
        normalized_text = _norm(text)
        for phrase in GENERIC_BLACKLIST:
            if _norm(phrase) in normalized_text:
                banned.add(phrase)

    return AntiNpcChecks(
        passed=len(banned) == 0,
        checked_sections=tuple(checked_sections),
        banned_matches=tuple(sorted(banned)),
    )


def build_marketing_brief(
    product: Mapping[str, Any] | Any,
    decision: Mapping[str, Any] | Any | None = None,
    creative_pack: Mapping[str, Any] | None = None,
) -> MarketingBrief:
    """Build a deterministic structured marketing brief.

    The optional creative_pack is accepted for future integration but is not
    required. A8-R66 intentionally avoids mutating existing creative_factory.
    """

    product_data = _mapping_from_any(product)
    decision_data = _mapping_from_any(decision)
    _ = creative_pack

    product_id = _clean_text(_first(product_data, "product_id", "id", "sku", fallback="unknown_product"))
    product_name = _clean_text(_first(product_data, "name", "product_name", "title", fallback="Producto sin nombre"))
    category = _clean_text(_first(product_data, "category", "product_category", fallback="commerce"))
    price = _money(_first(product_data, "price", "sale_price", fallback=None))
    cost = _money(_first(product_data, "cost", "unit_cost", fallback=None))
    margin = _margin_pct(price, cost)

    audience = _infer_audience(product_data)
    enemy = _infer_enemy(product_data)
    feature = _feature(product_data)

    price_fragment = f" Precio MXN {price:.2f}." if price is not None else ""
    margin_fragment = f" Margen bruto estimado {margin:.1f}%." if margin is not None else ""

    product_summary = (
        f"{product_name} en categoría {category}."
        f"{price_fragment}{margin_fragment}"
        f" Rol del brief: convertir atributos del producto en narrativa de venta verificable y segura."
    ).strip()

    core_angle = (
        f"Posicionar {product_name} como una herramienta práctica para reducir {enemy}, "
        f"usando como prueba principal su capacidad de {feature}, sin prometer resultados absolutos."
    )

    pain_points = (
        BriefItem(
            text=f"La persona detecta {enemy}, pero normalmente lo normaliza hasta que afecta su rutina.",
            rationale="Abre una tensión concreta sin exagerar ni inventar urgencia artificial.",
        ),
        BriefItem(
            text=f"El comprador necesita entender en segundos por qué {product_name} merece espacio, dinero y atención.",
            rationale="Conecta el ángulo con decisión de compra real: utilidad visible antes que adjetivos.",
        ),
        BriefItem(
            text="La objeción principal no es sólo precio; es creer que será otro producto que se queda guardado.",
            rationale="Ataca riesgo de abandono post-compra, común en gadgets y accesorios.",
        ),
    )

    objections = (
        BriefItem(
            text="No sé si realmente lo voy a usar.",
            rationale=f"Responder con escenarios de uso repetibles: cuándo entra {product_name} en la rutina y qué fricción reduce.",
        ),
        BriefItem(
            text="Parece otro gadget más.",
            rationale=f"Separar la promesa de la evidencia: mostrar {feature} y uso cotidiano en vez de adornos.",
        ),
        BriefItem(
            text="No quiero comprar algo que prometa de más.",
            rationale="Usar lenguaje sobrio, límites claros y notas de seguridad de claims.",
        ),
        BriefItem(
            text="Necesito justificar el precio.",
            rationale="Defender precio con frecuencia de uso, problema específico y comparación contra alternativas menos prácticas.",
        ),
    )

    hooks = (
        BriefItem(
            text=f"{product_name}: la pausa práctica para cuando {enemy} empieza a robarte foco.",
            rationale="Hook específico de situación, sin claim médico ni promesa absoluta.",
            safety_note="No presentar como tratamiento.",
        ),
        BriefItem(
            text=f"Antes de comprar otro accesorio, revisa si {feature} sí entra en tu rutina diaria.",
            rationale="Hook de evaluación racional; baja resistencia de compradores escépticos.",
        ),
        BriefItem(
            text=f"El problema no es trabajar mucho; es dejar que {enemy} decida por ti.",
            rationale="Reencuadra el dolor como pérdida de control operativo.",
            safety_note="Evitar tono alarmista.",
        ),
        BriefItem(
            text=f"{product_name} no compite por verse bonito; compite por usarse seguido.",
            rationale="Diferenciación contra compra impulsiva y productos decorativos.",
        ),
        BriefItem(
            text=f"Si tu rutina ya tiene el problema, {product_name} necesita demostrar uso desde el primer vistazo.",
            rationale="Hook orientado a demo y claridad, no a hype.",
        ),
    )

    scripts = (
        ScriptVariant(
            duration="15s",
            format="problem_demo_decision",
            beats=(
                f"0-3s: Mostrar el momento exacto donde aparece {enemy}.",
                f"3-8s: Enseñar {product_name} y la función central: {feature}.",
                "8-12s: Mostrar cómo entra en una rutina real, sin prometer resultados absolutos.",
                "12-15s: Cerrar con criterio de compra: uso frecuente, precio y ajuste a rutina.",
            ),
            cta=f"Revisa si {product_name} encaja con tu rutina antes de decidir.",
        ),
        ScriptVariant(
            duration="30s",
            format="skeptic_to_specific_use",
            beats=(
                "0-5s: Abrir con comprador escéptico: no necesita otro objeto guardado.",
                f"5-12s: Nombrar la fricción concreta: {enemy}.",
                f"12-20s: Demostrar {feature} en una secuencia simple y repetible.",
                "20-26s: Resolver objeciones: uso, límite del beneficio y precio.",
                "26-30s: Cierre sobrio con decisión informada, sin presión artificial.",
            ),
            cta="Compara uso, precio y entrega; si te hace sentido, avanza.",
        ),
    )

    ctas = (
        f"Revisa si {product_name} encaja con tu rutina antes de decidir.",
        "Compara uso, precio y entrega; si te hace sentido, avanza.",
        "Guárdalo si necesitas evaluar el producto con más calma.",
    )

    claims = _claim_safety(product_data, decision_data)
    permission, blocked_reasoning = _permission(decision_data)
    anti_npc = _anti_npc(hooks=hooks, scripts=scripts, ctas=ctas)

    payload_for_id = {
        "schema_version": SCHEMA_VERSION,
        "product_id": product_id,
        "product_name": product_name,
        "category": category,
        "price": price,
        "cost": cost,
        "decision": decision_data,
    }

    brief = MarketingBrief(
        schema_version=SCHEMA_VERSION,
        brief_id=_stable_id("brief", payload_for_id),
        product_id=product_id,
        product_name=product_name,
        product_summary=product_summary,
        audience=audience,
        core_angle=core_angle,
        pain_points=pain_points,
        objections=objections,
        hooks=hooks,
        scripts=scripts,
        ctas=ctas,
        claims_safety_notes=claims,
        anti_npc_checks=anti_npc,
        permission=permission,
        blocked_reasoning=blocked_reasoning,
    )

    return brief


def build_marketing_brief_dict(
    product: Mapping[str, Any] | Any,
    decision: Mapping[str, Any] | Any | None = None,
    creative_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-ready deterministic brief dictionary."""

    return build_marketing_brief(product, decision, creative_pack).to_dict()


__all__ = [
    "build_marketing_brief",
    "build_marketing_brief_dict",
]
"""Deterministic synthetic discovery for SYNAPSE sandbox candidates.

This module does not read vendors, marketplaces, ad platforms, stores, or files.
It converts local in-memory synthetic inputs into audited DiscoveryCandidate objects.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from synapse.discovery.synthetic_schema import (
    DISCOVERY_SCHEMA_VERSION,
    DiscoveryCandidate,
    DiscoverySignal,
    calculate_margin_pct,
    candidate_to_marketing_product,
    stable_candidate_id,
    validate_candidate_contract,
)

DEFAULT_SYNTHETIC_DISCOVERY_INPUTS: tuple[dict[str, Any], ...] = (
    {
        "product_name": "Barra LED asimétrica para monitor",
        "category": "perifericos_productividad",
        "market": "MX",
        "price": 949,
        "cost": 310,
        "traffic": 900,
        "days": 3,
        "marketing_angle": "salud visual y estación de trabajo nocturna sin reflejos",
        "primary_hook": "Ilumina tu escritorio sin pegarle luz directa a la pantalla.",
        "target_audience": "estudiantes, operadores y emprendedores que trabajan de noche frente a monitor",
        "use_case": "mejorar iluminación del setup durante sesiones largas",
        "demand_signals": (
            {
                "name": "setup_visible_problem",
                "score": 0.82,
                "rationale": "El antes/después se demuestra visualmente en escritorio oscuro.",
                "kind": "demand",
            },
            {
                "name": "productivity_context",
                "score": 0.76,
                "rationale": "La compra se entiende por rutina, no por lujo abstracto.",
                "kind": "demand",
            },
        ),
        "risk_signals": (
            {
                "name": "commodity_risk",
                "score": 0.31,
                "rationale": "El producto puede compararse por precio si no se diferencia el ángulo.",
                "kind": "risk",
            },
        ),
        "differentiation_signals": (
            {
                "name": "non_screen_glare_angle",
                "score": 0.78,
                "rationale": "El beneficio se ancla en luz asimétrica y setup nocturno.",
                "kind": "differentiation",
            },
        ),
        "evidence_notes": (
            "Synthetic sandbox candidate derived from known SYNAPSE e-commerce categories.",
            "No vendor inventory, scraping, platform read, platform write, or spend is used.",
        ),
    },
    {
        "product_name": "Fuente de agua inteligente para mascotas con filtro",
        "category": "mascotas_smart_home",
        "market": "MX",
        "price": 1149,
        "cost": 420,
        "traffic": 850,
        "days": 3,
        "marketing_angle": "hidratación constante para mascotas cuando el dueño trabaja fuera",
        "primary_hook": "Tu mascota no debería depender de un plato de agua olvidado.",
        "target_audience": "dueños de perros o gatos con jornadas largas y compra online recurrente",
        "use_case": "mantener agua en movimiento y visible durante el día",
        "demand_signals": (
            {
                "name": "pet_owner_anxiety",
                "score": 0.80,
                "rationale": "El problema es cotidiano y emocional sin requerir promesas médicas.",
                "kind": "demand",
            },
        ),
        "risk_signals": (
            {
                "name": "claim_safety_boundary",
                "score": 0.36,
                "rationale": "Debe evitar claims médicos sobre riñón, cura o prevención garantizada.",
                "kind": "risk",
            },
        ),
        "differentiation_signals": (
            {
                "name": "routine_automation",
                "score": 0.74,
                "rationale": "La diferenciación se apoya en automatización diaria y demostración visual.",
                "kind": "differentiation",
            },
        ),
        "evidence_notes": (
            "Synthetic sandbox candidate built for future discovery to brief compatibility.",
            "Claim must remain observational and non-medical.",
        ),
    },
    {
        "product_name": "Intercomunicador con cámara para casco",
        "category": "moto_seguridad_visual",
        "market": "MX",
        "price": 1899,
        "cost": 680,
        "traffic": 780,
        "days": 3,
        "marketing_angle": "registro visual de trayectos urbanos sin prometer protección absoluta",
        "primary_hook": "Que tu trayecto no dependa sólo de tu palabra.",
        "target_audience": "motociclistas urbanos que hacen traslados diarios y valoran evidencia visual",
        "use_case": "grabar recorridos y comunicarse en trayectos de moto",
        "demand_signals": (
            {
                "name": "urban_commute_use_case",
                "score": 0.77,
                "rationale": "El caso de uso es concreto para trayectos diarios.",
                "kind": "demand",
            },
        ),
        "risk_signals": (
            {
                "name": "legal_claim_risk",
                "score": 0.42,
                "rationale": "Debe evitar prometer defensa legal, seguridad garantizada o prevención de accidentes.",
                "kind": "risk",
            },
        ),
        "differentiation_signals": (
            {
                "name": "pov_demo_strength",
                "score": 0.81,
                "rationale": "El formato POV permite mostrar uso real sin inventar resultados.",
                "kind": "differentiation",
            },
        ),
        "evidence_notes": (
            "Synthetic sandbox candidate for visual demonstration categories.",
            "No live marketplace data is consulted.",
        ),
    },
)


def _text(record: Mapping[str, Any], key: str, default: str = "") -> str:
    return " ".join(str(record.get(key, default) or "").strip().split())


def _int(record: Mapping[str, Any], key: str, default: int) -> int:
    value = record.get(key, default)
    return int(value)


def _signal_tuple(record: Mapping[str, Any], key: str, *, fallback_kind: str) -> tuple[DiscoverySignal, ...]:
    values = record.get(key, ())
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{key} must be a tuple or list")
    return tuple(
        DiscoverySignal(
            name=str(value.get("name", "")),
            score=float(value.get("score", 0.0)),
            rationale=str(value.get("rationale", "")),
            kind=str(value.get("kind", fallback_kind)),
        )
        for value in values
        if isinstance(value, Mapping)
    )


def _evidence_notes(record: Mapping[str, Any]) -> tuple[str, ...]:
    values = record.get("evidence_notes", ())
    if not isinstance(values, (tuple, list)):
        raise TypeError("evidence_notes must be a tuple or list")
    return tuple(" ".join(str(value or "").strip().split()) for value in values if str(value or "").strip())


def normalize_synthetic_candidate(record: Mapping[str, Any]) -> DiscoveryCandidate:
    product_name = _text(record, "product_name", _text(record, "name"))
    category = _text(record, "category", "sandbox")
    market = _text(record, "market", "MX").upper()
    price = _int(record, "price", _int(record, "proposed_price_mxn", 0))
    cost = _int(record, "cost", _int(record, "estimated_landed_cost_mxn", 0))

    identity_payload = {
        "category": category,
        "cost": cost,
        "market": market,
        "price": price,
        "product_name": product_name,
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "source_type": "synthetic",
        "target_audience": _text(record, "target_audience"),
        "use_case": _text(record, "use_case"),
    }

    candidate = DiscoveryCandidate(
        candidate_id=_text(record, "candidate_id", stable_candidate_id(identity_payload)),
        product_name=product_name,
        category=category,
        market=market,
        price=price,
        cost=cost,
        margin_pct=calculate_margin_pct(price, cost),
        source_type="synthetic",
        demand_signals=_signal_tuple(record, "demand_signals", fallback_kind="demand"),
        risk_signals=_signal_tuple(record, "risk_signals", fallback_kind="risk"),
        differentiation_signals=_signal_tuple(
            record,
            "differentiation_signals",
            fallback_kind="differentiation",
        ),
        evidence_notes=_evidence_notes(record),
        supplier_mode=_text(record, "supplier_mode", "sandbox_synthetic_supplier"),
        traffic=_int(record, "traffic", 800),
        days=_int(record, "days", 3),
        marketing_angle=_text(record, "marketing_angle"),
        primary_hook=_text(record, "primary_hook"),
        target_audience=_text(record, "target_audience"),
        use_case=_text(record, "use_case"),
    )

    errors = validate_candidate_contract(candidate)
    if errors:
        joined = ",".join(errors)
        raise ValueError(f"INVALID_SYNTHETIC_CANDIDATE::{joined}")

    return candidate


def generate_synthetic_candidates(
    seed: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[DiscoveryCandidate, ...]:
    records = DEFAULT_SYNTHETIC_DISCOVERY_INPUTS if seed is None else tuple(seed)
    candidates = tuple(normalize_synthetic_candidate(record) for record in records)
    return tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))


__all__ = [
    "DEFAULT_SYNTHETIC_DISCOVERY_INPUTS",
    "candidate_to_marketing_product",
    "generate_synthetic_candidates",
    "normalize_synthetic_candidate",
    "validate_candidate_contract",
]
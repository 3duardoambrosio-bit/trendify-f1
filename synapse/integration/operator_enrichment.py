"""A8-R111 operator enrichment -> sealed methodology -> R109 pack unlock.

Local-only, deterministic and fail-closed. This module never performs network
access, external writes, spend, publication, campaign creation or fulfillment.
It does not modify the sealed methodology engine or the R109 renderers.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.integration.local_catalog_to_methodology import (
    LocalCatalogMethodologyBridgeError,
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.ui.operator_workbench_renderer import scan_forbidden_tokens
from synapse.ui.operator_workbench_view_model import (
    INPUT_LOW,
    INPUT_PARTIAL,
    INPUT_RICH,
    classify_input_richness,
)

SCHEMA_VERSION = "a8-r111.operator_enrichment.v1"

STATUS_ABSENT = "ABSENT"
STATUS_INVALID = "INVALID_INPUT"
STATUS_PARTIAL = "PARTIAL"
STATUS_RICH = "RICH"
STATUS_ACCEPTED = "ACCEPTED"
STATUS_BLOCKED = "BLOCKED"
STATUS_FALLBACK = "FALLBACK"

_TEMPLATE_FIELDS: tuple[str, ...] = (
    "buyer_pain",
    "buyer_state",
    "target_audience",
    "objections",
    "proof_available",
    "product_facts",
    "claim_risk_hints",
    "channel",
    "margin_profile",
    "desires",
    "differentiators",
    "market_context",
    "customer_language",
    "notes",
)

_LIST_FIELDS = frozenset(
    (
        "objections",
        "proof_available",
        "product_facts",
        "desires",
        "differentiators",
        "customer_language",
    )
)

_ALLOWED_KEYS = frozenset(("schema_version", "fixture_id", *_TEMPLATE_FIELDS, "_help"))

_R109_MAPPING: tuple[tuple[str, str], ...] = (
    ("target_audience", "target_audience"),
    ("buyer_pain", "pain_points"),
    ("desires", "desires"),
    ("objections", "objections"),
    ("differentiators", "differentiators"),
    ("market_context", "market_context"),
    ("customer_language", "customer_language"),
    ("proof_available", "proof_elements"),
)

_METHODOLOGY_REQUIRED: tuple[str, ...] = (
    "product_facts",
    "buyer_state",
    "claim_risk_hints",
    "channel",
    "margin_profile",
)

_COPY_RISK_SURFACES: tuple[str, ...] = (
    "hooks",
    "headlines",
    "primary_texts",
    "short_ads",
    "long_ads",
)

_PRIMARY_REASON_RE = re.compile(
    r"Primary reason:\s*(.*?)\s*Evidence checked:",
    re.IGNORECASE | re.DOTALL,
)
_OPERATOR_ACTION_RE = re.compile(
    r"(Operator action:\s*.*?)\s*Operator review required\.",
    re.IGNORECASE | re.DOTALL,
)


class OperatorEnrichmentError(ValueError):
    """Raised when an enrichment file cannot be trusted."""


@dataclass(frozen=True)
class EnrichmentApplication:
    fixture: dict[str, Any]
    status: str
    richness: str
    missing_fields: tuple[str, ...]
    errors: tuple[str, ...]
    methodology_status: str = ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_enrichment_template(fixture_id: str) -> dict[str, Any]:
    fixture_id = _text(fixture_id)
    if not fixture_id:
        raise OperatorEnrichmentError("fixture_id must be a non-empty string")

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "buyer_pain": "",
        "buyer_state": "",
        "target_audience": "",
        "objections": [],
        "proof_available": [],
        "product_facts": [],
        "claim_risk_hints": "",
        "channel": "Meta",
        "margin_profile": "",
        "desires": [],
        "differentiators": [],
        "market_context": "",
        "customer_language": [],
        "notes": "",
        "_help": {
            "buyer_pain": "Problema concreto que el comprador quiere resolver. No inventar.",
            "buyer_state": "Estado real del comprador, por ejemplo problem-aware o solution-aware.",
            "target_audience": "Segmento especÃ­fico que comprarÃ­a este producto.",
            "objections": "Lista de objeciones reales que el operador conoce.",
            "proof_available": "Lista de pruebas disponibles hoy. Dejar vacÃ­a si no existe prueba.",
            "product_facts": "Lista de hechos verificables del producto; no usar promesas.",
            "claim_risk_hints": "Riesgo para el motor: low, high, medical, safety o unclear.",
            "channel": "Canal previsto. Meta es el valor local por defecto.",
            "margin_profile": "Perfil explÃ­cito: tight, acceptable o healthy.",
            "desires": "Resultados deseados expresados por el comprador, sin garantÃ­as.",
            "differentiators": "Diferencias verificables frente a alternativas.",
            "market_context": "Contexto de mercado aportado por el operador.",
            "customer_language": "Frases reales del comprador, sin datos personales.",
            "notes": "Notas internas del operador; no se convierten automÃ¡ticamente en claims.",
        },
    }


def write_enrichment_template(
    path: str | Path,
    fixture_id: str,
    *,
    overwrite: bool = False,
) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise OperatorEnrichmentError(f"enrichment_template_exists={target.as_posix()}")

    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_enrichment_template(fixture_id)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return target


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise OperatorEnrichmentError(f"{field} must be a list of non-empty strings")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise OperatorEnrichmentError(
                f"{field}[{index}] must be a non-empty string"
            )
        normalized.append(item.strip())
    return normalized


def validate_enrichment(
    payload: Mapping[str, Any],
    *,
    expected_fixture_id: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise OperatorEnrichmentError("enrichment must be a JSON object")

    if any(not isinstance(key, str) for key in payload):
        raise OperatorEnrichmentError("enrichment keys must be strings")

    unexpected = sorted(set(payload) - _ALLOWED_KEYS)
    if unexpected:
        raise OperatorEnrichmentError(
            "unexpected_enrichment_fields=" + ",".join(unexpected)
        )

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise OperatorEnrichmentError(
            f"schema_version must equal {SCHEMA_VERSION}"
        )

    fixture_id = _text(payload.get("fixture_id"))
    if fixture_id != expected_fixture_id:
        raise OperatorEnrichmentError(
            "enrichment.fixture_id must exactly match candidate fixture_id"
        )

    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
    }

    for field in _TEMPLATE_FIELDS:
        value = payload.get(field, [] if field in _LIST_FIELDS else "")
        if field in _LIST_FIELDS:
            normalized[field] = _validate_string_list(value, field)
        else:
            if not isinstance(value, str):
                raise OperatorEnrichmentError(f"{field} must be a string")
            normalized[field] = value.strip()

    forbidden_fields: list[str] = []
    for field in _TEMPLATE_FIELDS:
        value = normalized[field]
        values = value if isinstance(value, list) else [value]
        for item in values:
            if scan_forbidden_tokens(item):
                forbidden_fields.append(field)

    if forbidden_fields:
        raise OperatorEnrichmentError(
            "forbidden_tokens_in_fields="
            + ",".join(sorted(set(forbidden_fields)))
        )

    return normalized


def load_enrichment(
    path: str | Path,
    *,
    expected_fixture_id: str,
) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise OperatorEnrichmentError(f"enrichment_not_found={source.as_posix()}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperatorEnrichmentError("invalid_enrichment_json") from exc

    return validate_enrichment(payload, expected_fixture_id=expected_fixture_id)


def map_enrichment_to_operator_input(
    enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    operator_input: dict[str, Any] = {}
    for source_field, target_field in _R109_MAPPING:
        value = enrichment.get(source_field)
        if isinstance(value, list):
            normalized: Any = _texts(value)
        else:
            normalized = _text(value)
            if source_field == "buyer_pain" and normalized:
                normalized = [normalized]
        if normalized:
            operator_input[target_field] = normalized
    return operator_input


def _methodology_missing_fields(
    fixture: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> list[str]:
    missing = [
        field
        for field in _METHODOLOGY_REQUIRED
        if not enrichment.get(field)
    ]
    product = _mapping(fixture.get("product"))
    if not _text(product.get("product_id")):
        missing.append("fixture.product.product_id")
    if not _text(product.get("category")):
        missing.append("fixture.product.category")
    return missing


def build_methodology_context(
    fixture: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    product = _mapping(fixture.get("product"))
    return {
        "product_facts": list(enrichment.get("product_facts") or []),
        "product_id": _text(product.get("product_id")),
        "buyer_state": _text(enrichment.get("buyer_state")),
        "proof_available": list(enrichment.get("proof_available") or []),
        "claim_risk": _text(enrichment.get("claim_risk_hints")),
        "channel": _text(enrichment.get("channel")),
        "margin_profile": _text(enrichment.get("margin_profile")),
        "category": _text(product.get("category")),
        "candidate_output": "",
    }


def _append_evidence_note(fixture: dict[str, Any], note: str) -> None:
    evidence = _mapping(fixture.get("evidence"))
    notes = _texts(evidence.get("notes"))
    notes.append(note)
    evidence["notes"] = _unique(notes)
    fixture["evidence"] = evidence


def _append_reason_code(decision: dict[str, Any], code: str) -> None:
    reason_codes = _texts(decision.get("reason_codes"))
    reason_codes.append(code)
    decision["reason_codes"] = _unique(reason_codes)


def _append_caveat(decision: dict[str, Any], caveat: str) -> None:
    caveats = _texts(decision.get("caveats"))
    caveats.append(caveat)
    decision["caveats"] = _unique(caveats)


def _base_annotated_fixture(
    fixture: Mapping[str, Any],
    *,
    enrichment_status: str,
    missing_fields: Sequence[str],
    errors: Sequence[str],
) -> dict[str, Any]:
    enriched = copy.deepcopy(dict(fixture))
    enriched["enrichment"] = {
        "schema_version": SCHEMA_VERSION,
        "status": enrichment_status,
        "missing_fields": list(missing_fields),
        "errors": list(errors),
        "deterministic": True,
        "operator_in_control": True,
        "no_network": True,
        "no_live_writes": True,
        "no_spend": True,
    }
    return enriched


def _invalid_application(
    fixture: Mapping[str, Any],
    error: str,
) -> EnrichmentApplication:
    operator_input = _mapping(fixture.get("operator_input"))
    richness = classify_input_richness(operator_input)
    enriched = _base_annotated_fixture(
        fixture,
        enrichment_status=STATUS_INVALID,
        missing_fields=richness["missing_fields"],
        errors=(error,),
    )
    decision = _mapping(enriched.get("decision"))
    decision["outcome"] = "INVALID_INPUT"
    decision["reason"] = f"Operator enrichment rejected: {error}"
    _append_reason_code(decision, "OPERATOR_ENRICHMENT_INVALID")
    _append_caveat(decision, "Fix the enrichment file and rebuild the workspace.")
    enriched["decision"] = decision
    enriched["operator_actions"] = [
        {
            "action_id": "repair_operator_enrichment",
            "label": "Corregir el archivo de enrichment y reconstruir el workspace.",
            "kind": "enrich_input",
            "target": "candidates_input",
            "notes": error,
        }
    ]
    enriched.pop("marketing", None)
    enriched.pop("shopify", None)
    _append_evidence_note(enriched, f"Operator enrichment invalid: {error}")
    return EnrichmentApplication(
        fixture=enriched,
        status=STATUS_INVALID,
        richness=str(richness["classification"]),
        missing_fields=tuple(richness["missing_fields"]),
        errors=(error,),
    )


def _extract_blocked_details(safe_output: str) -> tuple[str, str]:
    reason_match = _PRIMARY_REASON_RE.search(safe_output)
    action_match = _OPERATOR_ACTION_RE.search(safe_output)
    reason = reason_match.group(1).strip() if reason_match else safe_output.strip()
    action = action_match.group(1).strip() if action_match else ""
    return reason, action


def _build_claim_guard(
    enrichment: Mapping[str, Any],
    methodology: Mapping[str, Any],
) -> dict[str, Any]:
    safe_output = _text(methodology.get("safe_output"))
    status = _text(methodology.get("status"))
    risk = _text(enrichment.get("claim_risk_hints"))
    prohibited = [risk] if status == "blocked" and risk else []
    return {
        "allowed_claims": [],
        "risky_claims": [risk] if risk else [],
        "prohibited_claims": prohibited,
        "safe_wording": [safe_output] if safe_output else [],
        "claim_guard_summary": (
            f"Sealed methodology status={status}; "
            f"operator_review_required={bool(methodology.get('operator_review_required'))}."
        ),
    }


def _build_marketing_seed(
    fixture: Mapping[str, Any],
    enrichment: Mapping[str, Any],
    methodology: Mapping[str, Any],
) -> dict[str, Any]:
    safe_output = _text(methodology.get("safe_output"))
    framework = _text(methodology.get("selected_framework"))
    operator_input = map_enrichment_to_operator_input(enrichment)
    audience = _text(enrichment.get("target_audience"))
    proof = list(enrichment.get("proof_available") or [])
    risk = _text(enrichment.get("claim_risk_hints"))
    channel = _text(enrichment.get("channel"))
    pain = _texts(operator_input.get("pain_points"))
    desires = _texts(operator_input.get("desires"))
    objections = _texts(operator_input.get("objections"))

    risk_entries = [
        {
            "copy_key": surface,
            "risk_level": "review",
            "risky_terms": [risk] if risk else [],
            "prohibited_terms": [],
            "safe_rewrite": safe_output,
            "reason": "sealed_methodology_safe_output",
        }
        for surface in _COPY_RISK_SURFACES
    ]

    return {
        "strategy_summary": safe_output,
        "core_angle": framework,
        "why_this_angle": safe_output,
        "buyer_profile": audience,
        "audience": [audience] if audience else [],
        "hooks": [safe_output],
        "headlines": [safe_output],
        "primary_texts": [safe_output],
        "short_ads": [safe_output],
        "long_ads": [safe_output],
        "captions": [safe_output],
        "ugc_scripts": [],
        "video_scripts": [],
        "image_ad_concepts": [],
        "channel_packs": [
            {
                "channel": channel,
                "objective": "operator_review_before_use",
                "notes": safe_output,
            }
        ],
        "testing_plan": {
            "phase_1": "Local preparation only.",
            "budget_note": "No spend in Phase 1.",
        },
        "angle_matrix": [
            {
                "angle_id": _text(methodology.get("selected_rule_id")),
                "angle_name": framework,
                "promise_type": "sealed_methodology_output",
                "target_segment": audience,
                "pain_addressed": pain[0] if pain else "",
                "desire_addressed": desires[0] if desires else "",
                "objection_addressed": objections[0] if objections else "",
                "proof_needed": proof[0] if proof else "",
                "claim_risk": risk or "unclear",
                "safe_wording": safe_output,
                "why_it_might_work": safe_output,
                "why_it_might_fail": risk,
            }
        ],
        "creative_hypotheses": [],
        "claim_risk_by_copy": risk_entries,
        "testing_plan_v2": {
            "first_test_budget_boundary_dry_run_only": (
                "No spend in Phase 1; operator review before any future test."
            ),
            "success_signals": [],
            "warning_signals": [],
            "stop_signals": [],
            "continue_if": [],
            "review_if": [],
            "kill_if": [],
            "what_not_to_conclude": [
                "Do not conclude product-market fit from local preparation."
            ],
        },
    }


def _build_shopify_seed(
    fixture: Mapping[str, Any],
    enrichment: Mapping[str, Any],
    methodology: Mapping[str, Any],
) -> dict[str, Any]:
    product = _mapping(fixture.get("product"))
    product_name = _text(product.get("name"))
    category = _text(product.get("category"))
    safe_output = _text(methodology.get("safe_output"))
    framework = _text(methodology.get("selected_framework"))
    proof = list(enrichment.get("proof_available") or [])
    facts = list(enrichment.get("product_facts") or [])
    desires = list(enrichment.get("desires") or [])
    risk = _text(enrichment.get("claim_risk_hints"))

    return {
        "title": product_name,
        "subtitle": framework,
        "short_description": safe_output,
        "long_description": safe_output,
        "bullets": proof,
        "benefits": desires,
        "specifications": [
            {"name": f"Operator fact {index}", "value": fact}
            for index, fact in enumerate(facts, start=1)
        ],
        "faq": [],
        "seo_title": product_name,
        "seo_meta_description": safe_output,
        "handle": "",
        "tags": [category] if category else [],
        "category": category,
        "shipping_note": "",
        "refund_claim_note": "",
        "claim_safe_disclaimer": risk,
        "image_checklist": proof,
        "publish_checklist": [
            "Operator review required before publication."
        ],
        "missing_inputs": [],
    }


def _apply_valid_enrichment(
    fixture: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> EnrichmentApplication:
    operator_input = map_enrichment_to_operator_input(enrichment)
    richness = classify_input_richness(operator_input)
    missing = list(richness["missing_fields"])
    methodology_missing = _methodology_missing_fields(fixture, enrichment)

    enriched = _base_annotated_fixture(
        fixture,
        enrichment_status=(
            STATUS_RICH
            if richness["classification"] == INPUT_RICH
            else STATUS_PARTIAL
        ),
        missing_fields=missing + methodology_missing,
        errors=(),
    )
    enriched["operator_input"] = operator_input
    _append_evidence_note(
        enriched,
        "Operator enrichment loaded from local JSON; no network and no live writes.",
    )

    if methodology_missing:
        decision = _mapping(enriched.get("decision"))
        _append_reason_code(decision, "OPERATOR_ENRICHMENT_PARTIAL")
        _append_caveat(
            decision,
            "Missing methodology context: " + ", ".join(methodology_missing) + ".",
        )
        enriched["decision"] = decision
        enriched.pop("marketing", None)
        enriched.pop("shopify", None)
        return EnrichmentApplication(
            fixture=enriched,
            status=STATUS_PARTIAL,
            richness=str(richness["classification"]),
            missing_fields=tuple(missing + methodology_missing),
            errors=(),
        )

    try:
        enriched = enrich_local_catalog_fixture_with_methodology(
            enriched,
            build_methodology_context(enriched, enrichment),
        )
    except LocalCatalogMethodologyBridgeError as exc:
        return _invalid_application(fixture, str(exc))

    methodology = _mapping(_mapping(enriched.get("decision")).get("methodology"))
    methodology_status = _text(methodology.get("status"))
    enriched["claim_guard"] = _build_claim_guard(enrichment, methodology)

    if methodology_status == "blocked":
        safe_output = _text(methodology.get("safe_output"))
        primary_reason, operator_action = _extract_blocked_details(safe_output)
        selected_rule_id = _text(methodology.get("selected_rule_id"))
        action = {
            "action_id": f"methodology_{selected_rule_id}_review",
            "label": operator_action or safe_output,
            "kind": "review_blocked",
            "target": "decision.methodology.safe_output",
            "notes": safe_output,
        }
        product_name = _text(_mapping(enriched.get("product")).get("name"))
        enriched["blocked"] = [
            {
                "product_name": product_name,
                "reason": primary_reason,
                "reason_codes": ["METHODOLOGY_BLOCKED", selected_rule_id],
                "severity": "high",
                "can_recover": True,
                "operator_actions": [action],
            }
        ]
        enriched["operator_actions"] = [action]
        decision = _mapping(enriched.get("decision"))
        decision["outcome"] = "BLOCKED"
        decision["reason"] = primary_reason
        _append_reason_code(decision, "METHODOLOGY_BLOCKED")
        _append_caveat(decision, safe_output)
        enriched["decision"] = decision
        enriched.pop("marketing", None)
        enriched.pop("shopify", None)
        enriched["enrichment"]["status"] = STATUS_BLOCKED
        return EnrichmentApplication(
            fixture=enriched,
            status=STATUS_BLOCKED,
            richness=str(richness["classification"]),
            missing_fields=tuple(missing),
            errors=(),
            methodology_status=methodology_status,
        )

    if (
        methodology_status == "accepted"
        and richness["classification"] == INPUT_RICH
    ):
        enriched["marketing"] = _build_marketing_seed(
            enriched, enrichment, methodology
        )
        enriched["shopify"] = _build_shopify_seed(
            enriched, enrichment, methodology
        )
        decision = _mapping(enriched.get("decision"))
        _append_reason_code(decision, "METHODOLOGY_ACCEPTED")
        _append_caveat(
            decision,
            "Methodology accepted for local preparation; permission gate remains REVIEW.",
        )
        enriched["decision"] = decision
        enriched["enrichment"]["status"] = STATUS_ACCEPTED
        return EnrichmentApplication(
            fixture=enriched,
            status=STATUS_ACCEPTED,
            richness=str(richness["classification"]),
            missing_fields=tuple(missing),
            errors=(),
            methodology_status=methodology_status,
        )

    decision = _mapping(enriched.get("decision"))
    _append_reason_code(decision, "METHODOLOGY_NOT_ACCEPTED_FOR_FULL_PACK")
    _append_caveat(
        decision,
        "Full pack remains disabled until methodology is accepted and input richness is INPUT_RICH.",
    )
    enriched["decision"] = decision
    enriched.pop("marketing", None)
    enriched.pop("shopify", None)
    status = STATUS_FALLBACK if methodology_status == "fallback" else STATUS_PARTIAL
    enriched["enrichment"]["status"] = status
    return EnrichmentApplication(
        fixture=enriched,
        status=status,
        richness=str(richness["classification"]),
        missing_fields=tuple(missing),
        errors=(),
        methodology_status=methodology_status,
    )


def apply_enrichment_file(
    fixture: Mapping[str, Any],
    enrichment_path: str | Path | None,
) -> EnrichmentApplication:
    fixture_id = _text(fixture.get("fixture_id"))
    if not fixture_id:
        return _invalid_application(fixture, "fixture.fixture_id is missing")

    if enrichment_path is None or not Path(enrichment_path).is_file():
        richness = classify_input_richness(_mapping(fixture.get("operator_input")))
        enriched = _base_annotated_fixture(
            fixture,
            enrichment_status=STATUS_ABSENT,
            missing_fields=richness["missing_fields"],
            errors=(),
        )
        _append_evidence_note(
            enriched,
            "No operator enrichment file found; candidate remains honest and locked.",
        )
        return EnrichmentApplication(
            fixture=enriched,
            status=STATUS_ABSENT,
            richness=str(richness["classification"]),
            missing_fields=tuple(richness["missing_fields"]),
            errors=(),
        )

    try:
        enrichment = load_enrichment(
            enrichment_path,
            expected_fixture_id=fixture_id,
        )
    except OperatorEnrichmentError as exc:
        return _invalid_application(fixture, str(exc))

    return _apply_valid_enrichment(fixture, enrichment)


__all__ = [
    "SCHEMA_VERSION",
    "STATUS_ABSENT",
    "STATUS_INVALID",
    "STATUS_PARTIAL",
    "STATUS_RICH",
    "STATUS_ACCEPTED",
    "STATUS_BLOCKED",
    "STATUS_FALLBACK",
    "OperatorEnrichmentError",
    "EnrichmentApplication",
    "build_enrichment_template",
    "write_enrichment_template",
    "validate_enrichment",
    "load_enrichment",
    "map_enrichment_to_operator_input",
    "build_methodology_context",
    "apply_enrichment_file",
]

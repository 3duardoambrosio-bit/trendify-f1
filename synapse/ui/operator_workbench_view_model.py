"""A8-R109A Operator Workbench ViewModel — deterministic data contract.

Scope (R109A, mechanical foundation only):
- Pure functions + dataclasses that turn frozen local JSON fixtures into a
  deterministic ViewModel for the future Operator Workbench (R109B styles it).
- No server, no Streamlit, no network clients, no credentials.
- No runtime clock: same fixture in, byte-identical ViewModel out.
- Fase 1 boundary: no Shopify/Dropi/Meta live writes, no spend, no fulfillment.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "a8-r109a.workbench_view_model.v3"
RENDER_MODE = "offline_static_html"
SOURCE_KIND_DEFAULT = "frozen_local_fixture"
GENERATED_AT_POLICY = "deterministic_no_runtime_clock"

BASE_HEAD = "c189cb09f963417596f2b6a02bfbd9e9ae2459a2"
ISLAND = "A8-R109A"
FASE_1_STATUS = "sealed_candidate_after_a8_r106"

INPUT_RICH = "INPUT_RICH"
INPUT_PARTIAL = "INPUT_PARTIAL"
INPUT_LOW = "INPUT_LOW"

LOW_INPUT_WARNING = (
    "Input richness is low; enrich operator input before trusting marketing copy."
)

RICHNESS_POLICY = "r105_3_operator_input_quality"

RICHNESS_FIELDS: tuple[str, ...] = (
    "target_audience",
    "pain_points",
    "desires",
    "objections",
    "differentiators",
    "tone_of_voice",
    "market_context",
    "customer_language",
    "proof_elements",
    "competitor_notes",
)

RICH_MIN_FILLED = 8
PARTIAL_MIN_FILLED = 4

MAX_ENRICH_ACTIONS = 5

NO_PRODUCT_DISABLED_REASON = "no_recommended_product_in_shortlist"

# Marketing Pack V2 depth contract (A8-R109A-I2).

REQUIRED_COPY_RISK_SURFACES: tuple[str, ...] = (
    "hooks",
    "headlines",
    "primary_texts",
    "short_ads",
    "long_ads",
)

CONFIDENCE_SECTIONS: tuple[str, ...] = (
    "strategy_confidence",
    "hook_confidence",
    "ad_copy_confidence",
    "channel_pack_confidence",
    "claim_safety_confidence",
    "testing_plan_confidence",
)

MIN_HOOKS_FOR_DEPTH = 5

# Which fixture fields can legitimately support each marketing output.
_SUPPORT_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "strategy_summary",
        (
            "marketing.strategy_summary",
            "operator_input.market_context",
            "operator_input.target_audience",
        ),
    ),
    ("core_angle", ("marketing.core_angle", "operator_input.pain_points")),
    (
        "hooks",
        (
            "marketing.hooks",
            "operator_input.pain_points",
            "operator_input.customer_language",
        ),
    ),
    ("headlines", ("marketing.headlines", "operator_input.desires")),
    (
        "primary_texts",
        (
            "marketing.primary_texts",
            "operator_input.differentiators",
            "operator_input.proof_elements",
        ),
    ),
    ("short_ads", ("marketing.short_ads", "operator_input.pain_points")),
    (
        "long_ads",
        (
            "marketing.long_ads",
            "operator_input.proof_elements",
            "operator_input.objections",
        ),
    ),
    (
        "angle_matrix",
        (
            "marketing.angle_matrix",
            "operator_input.pain_points",
            "operator_input.desires",
        ),
    ),
    (
        "creative_hypotheses",
        ("marketing.creative_hypotheses", "marketing.angle_matrix"),
    ),
)

_MARKETING_SEED_KEYS: tuple[str, ...] = (
    "strategy_summary",
    "core_angle",
    "hooks",
    "headlines",
    "primary_texts",
    "short_ads",
    "long_ads",
    "angle_matrix",
    "creative_hypotheses",
    "channel_packs",
)

SAFETY_BOUNDARY: dict[str, bool] = {
    "fase_1_read_only": True,
    "dry_run": True,
    "no_live_writes": True,
    "no_spend": True,
    "no_fulfillment": True,
    "no_shopify_live": True,
    "no_dropi_live": True,
    "no_meta_live": True,
    "no_credentials_required": True,
    "no_external_network": True,
    "operator_in_control": True,
    "future_gate_required_for_live": True,
}

BLOCKED_ITEM_SAFETY_BOUNDARY: dict[str, bool] = {
    "no_live_writes": True,
    "no_spend": True,
    "operator_decision_required": True,
}

# --- A8-R109A.1 system surface contract (consumed by R109B) -------------------

MODULE_STATUS_PASS = "pass"
MODULE_STATUS_WARNING = "warning"
MODULE_STATUS_BLOCKED = "blocked"
MODULE_STATUS_EMPTY = "empty"
MODULE_STATUS_FUTURE = "future"
MODULE_STATUS_AUDIT = "audit"

WORKBENCH_MODULE_IDS: tuple[str, ...] = (
    "command_center",
    "decision_center",
    "product_lab",
    "economics",
    "shopify_studio",
    "marketing_engine",
    "safety_claim_guard",
    "evidence",
    "learning_feedback",
    "blocked_queue",
)

MODULE_LABELS: dict[str, str] = {
    "command_center": "Command Center",
    "decision_center": "Decision Center",
    "product_lab": "Product Lab",
    "economics": "Economics",
    "shopify_studio": "Shopify Studio",
    "marketing_engine": "Marketing Engine",
    "safety_claim_guard": "Safety / Claim Guard",
    "evidence": "Evidence",
    "learning_feedback": "Learning / Feedback",
    "blocked_queue": "Blocked Queue",
}

OUTCOME_RECOMMENDED = "RECOMMENDED_FOR_PREPARE"
OUTCOME_BLOCKED = "BLOCKED"
OUTCOME_REVIEW = "REVIEW_REQUIRED"

PIPELINE_SOURCE_FIXTURE = "fixture_scenario"
PIPELINE_CONFIDENCE_LIMITED = "limited_fixture_only"
PIPELINE_NOTE_FIXTURE_ONLY = (
    "Conteos derivados del escenario del fixture congelado; sin discovery en vivo."
)

# Maps operator action kinds to the workbench module that owns them.
ACTION_KIND_TO_MODULE: dict[str, str] = {
    "verify_supplier": "shopify_studio",
    "collect_assets": "shopify_studio",
    "enrich_input": "product_lab",
    "review_blocked": "blocked_queue",
    "repair_claims": "safety_claim_guard",
    "repair_economics": "economics",
    "reject_product": "blocked_queue",
    "build_shortlist": "command_center",
}
ACTION_DEFAULT_MODULE = "command_center"

# What the workbench may claim today vs never. Static and deterministic on
# purpose: the UI must not infer capability from data shape.
CAPABILITY_SURFACE_MAP: dict[str, tuple[str, ...]] = {
    "real_now": (
        "deterministic_view_model_from_frozen_fixture",
        "input_richness_classification_r105_3",
        "claim_guard_adjacent_to_copy_surfaces",
        "copy_payload_registry_byte_exact",
        "blocked_queue_with_reason_codes_and_repair_paths",
        "offline_static_html_render_no_network",
    ),
    "fixture_only": (
        "candidate_pipeline_counts",
        "economics_unit_numbers",
        "opportunity_scores",
        "shopify_pack_content",
        "marketing_pack_content",
    ),
    "future_or_not_connected": (
        "live_discovery_pipeline",
        "real_market_cpm_ctr_cpa",
        "learning_feedback_live_observations",
        "shopify_publish_flow",
        "meta_campaign_execution",
    ),
    "forbidden_to_claim": (
        "product_market_fit",
        "guaranteed_sales_or_performance",
        "live_analytics_connected",
        "autonomous_spend",
    ),
}


# --- basic coercion helpers -------------------------------------------------

def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    single = _text(value)
    return [single] if single else []


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return True


def _money(value: Any, currency: str = "MXN") -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    return f"{currency} {amount:.2f}"


def _lines(items: Sequence[str], bullet: str = "- ") -> str:
    return "\n".join(f"{bullet}{item}" for item in items)


# --- dataclasses ------------------------------------------------------------

@dataclass(frozen=True)
class CopyPayload:
    """One canonical, byte-exact copy payload for operator copy/paste."""

    key: str
    label: str
    section: str
    text: str
    claim_guard_ref: str
    source_fields: tuple[str, ...]


@dataclass(frozen=True)
class WorkbenchViewModel:
    """Deterministic ViewModel contract consumed by the R109A renderer."""

    schema_version: str
    fixture_id: str
    render_mode: str
    source_kind: str
    generated_at_policy: str
    product: dict[str, Any]
    decision: dict[str, Any]
    economics: dict[str, Any]
    scores: dict[str, Any]
    input_richness: dict[str, Any]
    claim_guard: dict[str, Any]
    shopify_pack: dict[str, Any]
    marketing_pack: dict[str, Any]
    learning_plan: dict[str, Any]
    blocked_queue: tuple[dict[str, Any], ...]
    operator_actions: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    safety_boundary: dict[str, bool]
    evidence: dict[str, Any]
    copy_payloads: dict[str, Any]
    # A8-R109A.1 system surfaces (contract for R109B)
    module_status_summary: tuple[dict[str, Any], ...]
    candidate_pipeline: dict[str, Any]
    blocked_queue_summary: dict[str, Any]
    action_queue: tuple[dict[str, Any], ...]
    system_health_board: dict[str, Any]
    capability_surface_map: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON-ready dict (tuples become lists, key order stable)."""
        return json.loads(self.to_json())

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


# --- section builders -------------------------------------------------------

def classify_input_richness(operator_input: Mapping[str, Any]) -> dict[str, Any]:
    """Classify operator input quality (R105.3 operationalized).

    rich operator input -> stronger expert output
    poor operator input -> generic/low-confidence output
    """
    data = _mapping(operator_input)
    filled = [name for name in RICHNESS_FIELDS if _is_filled(data.get(name))]
    missing = [name for name in RICHNESS_FIELDS if name not in filled]

    if len(filled) >= RICH_MIN_FILLED:
        classification = INPUT_RICH
    elif len(filled) >= PARTIAL_MIN_FILLED:
        classification = INPUT_PARTIAL
    else:
        classification = INPUT_LOW

    return {
        "classification": classification,
        "policy": RICHNESS_POLICY,
        "filled_count": len(filled),
        "total_fields": len(RICHNESS_FIELDS),
        "filled_fields": filled,
        "missing_fields": missing,
        "warning": LOW_INPUT_WARNING if classification == INPUT_LOW else "",
    }


def build_claim_guard(fixture: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(fixture.get("claim_guard"))
    return {
        "allowed_claims": _texts(raw.get("allowed_claims")),
        "risky_claims": _texts(raw.get("risky_claims")),
        "prohibited_claims": _texts(raw.get("prohibited_claims")),
        "safe_wording": _texts(raw.get("safe_wording")),
        "claim_guard_summary": _text(raw.get("claim_guard_summary"), "Sin resumen de claim guard."),
    }


def _claim_guard_notes(claim_guard: Mapping[str, Any], surface: str) -> dict[str, Any]:
    """Claim guard notes shaped for adjacency next to a copy surface."""
    return {
        "adjacent_to": surface,
        "summary": claim_guard["claim_guard_summary"],
        "allowed_claims": list(claim_guard["allowed_claims"]),
        "risky_claims": list(claim_guard["risky_claims"]),
        "prohibited_claims": list(claim_guard["prohibited_claims"]),
        "safe_wording": list(claim_guard["safe_wording"]),
    }


_SHOPIFY_EMPTY_FIELDS: dict[str, Any] = {
    "title": "",
    "subtitle": "",
    "short_description": "",
    "long_description": "",
    "bullets": [],
    "benefits": [],
    "specifications": [],
    "faq": [],
    "seo_title": "",
    "seo_meta_description": "",
    "handle": "",
    "tags": [],
    "category": "",
    "price": "",
    "compare_at_price": "",
    "shipping_note": "",
    "refund_claim_note": "",
    "claim_safe_disclaimer": "",
    "image_checklist": [],
    "publish_checklist": [],
    "missing_inputs": [],
}


def build_shopify_pack(
    fixture: Mapping[str, Any],
    claim_guard: Mapping[str, Any],
    has_product: bool,
) -> dict[str, Any]:
    if not has_product or not isinstance(fixture.get("shopify"), Mapping):
        pack = dict(_SHOPIFY_EMPTY_FIELDS)
        pack["enabled"] = False
        pack["disabled_reason"] = NO_PRODUCT_DISABLED_REASON
        pack["claim_guard_notes"] = _claim_guard_notes(claim_guard, "shopify_pack")
        return pack

    raw = _mapping(fixture.get("shopify"))
    econ = _mapping(fixture.get("economics"))
    currency = _text(econ.get("currency"), "MXN")

    specifications = [
        {"name": _text(item.get("name")), "value": _text(item.get("value"))}
        for item in raw.get("specifications") or []
        if isinstance(item, Mapping)
    ]
    faq = [
        {"q": _text(item.get("q")), "a": _text(item.get("a"))}
        for item in raw.get("faq") or []
        if isinstance(item, Mapping)
    ]

    return {
        "enabled": True,
        "disabled_reason": "",
        "title": _text(raw.get("title")),
        "subtitle": _text(raw.get("subtitle")),
        "short_description": _text(raw.get("short_description")),
        "long_description": _text(raw.get("long_description")),
        "bullets": _texts(raw.get("bullets")),
        "benefits": _texts(raw.get("benefits")),
        "specifications": specifications,
        "faq": faq,
        "seo_title": _text(raw.get("seo_title")),
        "seo_meta_description": _text(raw.get("seo_meta_description")),
        "handle": _text(raw.get("handle")),
        "tags": _texts(raw.get("tags")),
        "category": _text(raw.get("category")),
        "price": _money(econ.get("price_mxn"), currency),
        "compare_at_price": _money(econ.get("compare_at_price_mxn"), currency),
        "shipping_note": _text(raw.get("shipping_note")),
        "refund_claim_note": _text(raw.get("refund_claim_note")),
        "claim_safe_disclaimer": _text(raw.get("claim_safe_disclaimer")),
        "image_checklist": _texts(raw.get("image_checklist")),
        "publish_checklist": _texts(raw.get("publish_checklist")),
        "missing_inputs": _texts(raw.get("missing_inputs")),
        "claim_guard_notes": _claim_guard_notes(claim_guard, "shopify_pack"),
    }


def _marketing_confidence(classification: str) -> dict[str, Any]:
    if classification == INPUT_LOW:
        return {
            "level": "low",
            "label": "generic_low_confidence",
            "expert_method_applied": False,
            "market_validated": False,
            "note": (
                "Copy generico por brief pobre del operador; "
                "no representa calidad experta."
            ),
        }
    if classification == INPUT_PARTIAL:
        return {
            "level": "medium",
            "label": "structured_partial_input",
            "expert_method_applied": True,
            "market_validated": False,
            "note": "Brief parcial; falta contexto para confianza alta.",
        }
    return {
        "level": "medium_high",
        "label": "structured_rich_input_no_market_validation",
        "expert_method_applied": True,
        "market_validated": False,
        "note": "Brief rico; la validacion final requiere datos reales de mercado (Fase 2).",
    }


_MARKETING_EMPTY_FIELDS: dict[str, Any] = {
    "strategy_summary": "",
    "core_angle": "",
    "why_this_angle": "",
    "buyer_profile": "",
    "audience": [],
    "pain_points": [],
    "desire": [],
    "objections": [],
    "hooks": [],
    "headlines": [],
    "primary_texts": [],
    "short_ads": [],
    "long_ads": [],
    "captions": [],
    "ugc_scripts": [],
    "video_scripts": [],
    "image_ad_concepts": [],
    "channel_packs": [],
    "testing_plan": {},
    "angle_matrix": [],
    "creative_hypotheses": [],
    "claim_risk_by_copy": [],
    "input_support_map": [],
    "missing_marketing_inputs": [],
}


# --- Marketing Pack V2 depth builders (A8-R109A-I2) ---------------------------

def build_angle_matrix(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _mapping(fixture.get("marketing")).get("angle_matrix") or []
    matrix: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        matrix.append(
            {
                "angle_id": _text(item.get("angle_id")),
                "angle_name": _text(item.get("angle_name")),
                "promise_type": _text(item.get("promise_type")),
                "target_segment": _text(item.get("target_segment")),
                "pain_addressed": _text(item.get("pain_addressed")),
                "desire_addressed": _text(item.get("desire_addressed")),
                "objection_addressed": _text(item.get("objection_addressed")),
                "proof_needed": _text(item.get("proof_needed")),
                "claim_risk": _text(item.get("claim_risk"), "unknown"),
                "safe_wording": _text(item.get("safe_wording")),
                "why_it_might_work": _text(item.get("why_it_might_work")),
                "why_it_might_fail": _text(item.get("why_it_might_fail")),
            }
        )
    return matrix


def build_creative_hypotheses(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _mapping(fixture.get("marketing")).get("creative_hypotheses") or []
    hypotheses: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        hypotheses.append(
            {
                "hypothesis_id": _text(item.get("hypothesis_id")),
                "hypothesis": _text(item.get("hypothesis")),
                "variable_tested": _text(item.get("variable_tested")),
                "expected_signal": _text(item.get("expected_signal")),
                "failure_signal": _text(item.get("failure_signal")),
                "minimum_evidence_needed": _text(item.get("minimum_evidence_needed")),
                "channel": _text(item.get("channel")),
                "linked_angle_id": _text(item.get("linked_angle_id")),
            }
        )
    return hypotheses


def _normalize_copy_risk(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "copy_key": _text(item.get("copy_key")),
        "risk_level": _text(item.get("risk_level"), "unknown"),
        "risky_terms": _texts(item.get("risky_terms")),
        "prohibited_terms": _texts(item.get("prohibited_terms")),
        "safe_rewrite": _text(item.get("safe_rewrite")),
        "reason": _text(item.get("reason")),
    }


def build_claim_risk_by_copy(
    fixture: Mapping[str, Any], claim_guard: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """One risk entry per major copy surface; conservative default when absent."""
    provided: dict[str, dict[str, Any]] = {}
    for item in _mapping(fixture.get("marketing")).get("claim_risk_by_copy") or []:
        if isinstance(item, Mapping) and _text(item.get("copy_key")):
            provided[_text(item.get("copy_key"))] = _normalize_copy_risk(item)

    entries: list[dict[str, Any]] = []
    for copy_key in REQUIRED_COPY_RISK_SURFACES:
        if copy_key in provided:
            entries.append(provided.pop(copy_key))
            continue
        entries.append(
            {
                "copy_key": copy_key,
                "risk_level": "review",
                "risky_terms": [],
                "prohibited_terms": list(claim_guard.get("prohibited_claims") or []),
                "safe_rewrite": "Mantener redaccion descriptiva conservadora.",
                "reason": (
                    "Sin analisis especifico en el fixture; aplica el resumen del "
                    f"claim guard: {claim_guard.get('claim_guard_summary', '')}"
                ),
            }
        )
    entries.extend(provided.values())
    return entries


def _fixture_field_value(fixture: Mapping[str, Any], path: str) -> Any:
    section, _, field_name = path.partition(".")
    return _mapping(fixture.get(section)).get(field_name)


def build_input_support_map(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map each marketing output to the fixture fields that actually support it.

    Outputs with no filled supporting field are flagged as generic fallback so
    they can never be read as supported claims.
    """
    entries: list[dict[str, Any]] = []
    for output_key, candidates in _SUPPORT_CANDIDATES:
        support_fields = [
            path for path in candidates if _is_filled(_fixture_field_value(fixture, path))
        ]
        supported = bool(support_fields)
        entries.append(
            {
                "output_key": output_key,
                "supported": supported,
                "support_fields": support_fields,
                "notes": (
                    ""
                    if supported
                    else "Fallback generico: sin soporte en el brief; no usar como claim."
                ),
            }
        )
    return entries


def build_missing_marketing_inputs(
    fixture: Mapping[str, Any], input_richness: Mapping[str, Any]
) -> list[str]:
    missing = [
        f"operator_input.{name}" for name in input_richness.get("missing_fields") or []
    ]
    marketing_raw = _mapping(fixture.get("marketing"))
    for key in _MARKETING_SEED_KEYS:
        if not _is_filled(marketing_raw.get(key)):
            missing.append(f"marketing.{key}")
    return missing


def build_confidence_by_section(
    fixture: Mapping[str, Any],
    classification: str,
    angle_matrix: Sequence[Mapping[str, Any]],
    claim_risk_by_copy: Sequence[Mapping[str, Any]],
    enabled: bool,
) -> dict[str, dict[str, str]]:
    if not enabled:
        return {
            section: {"level": "none", "basis": "no_product_no_copy"}
            for section in CONFIDENCE_SECTIONS
        }

    marketing_raw = _mapping(fixture.get("marketing"))
    claim_guard_raw = _mapping(fixture.get("claim_guard"))
    outcome = _text(_mapping(fixture.get("decision")).get("outcome"))

    def graded(has_depth: bool, basis: str) -> dict[str, str]:
        if classification == INPUT_LOW:
            level = "low"
        elif classification == INPUT_PARTIAL:
            level = "medium" if has_depth else "low"
        else:
            level = "medium_high" if has_depth else "medium"
        return {"level": level, "basis": basis}

    prohibited_copy = any(
        entry.get("risk_level") == "prohibited" for entry in claim_risk_by_copy
    )
    if outcome == "BLOCKED" or prohibited_copy:
        claim_safety = {
            "level": "blocked",
            "basis": "claims prohibidos activos en el copy o producto bloqueado",
        }
    elif _texts(claim_guard_raw.get("risky_claims")):
        claim_safety = {
            "level": "medium",
            "basis": "claims riesgosos senalados por el claim guard",
        }
    else:
        claim_safety = {"level": "medium_high", "basis": "sin claims riesgosos senalados"}

    testing_v2 = _mapping(marketing_raw.get("testing_plan_v2"))
    return {
        "strategy_confidence": graded(
            _is_filled(marketing_raw.get("strategy_summary")) and bool(angle_matrix),
            "resumen de estrategia + matriz de angulos",
        ),
        "hook_confidence": graded(
            len(_texts(marketing_raw.get("hooks"))) >= MIN_HOOKS_FOR_DEPTH,
            "numero y variedad de hooks",
        ),
        "ad_copy_confidence": graded(
            _is_filled(marketing_raw.get("primary_texts"))
            and _is_filled(marketing_raw.get("short_ads"))
            and _is_filled(marketing_raw.get("long_ads")),
            "cobertura de formatos de anuncio",
        ),
        "channel_pack_confidence": graded(
            _is_filled(marketing_raw.get("channel_packs")), "channel packs definidos"
        ),
        "claim_safety_confidence": claim_safety,
        "testing_plan_confidence": graded(
            _is_filled(testing_v2.get("success_signals"))
            and _is_filled(testing_v2.get("stop_signals")),
            "umbrales de exito y alto definidos",
        ),
    }


def build_testing_plan_with_thresholds(
    fixture: Mapping[str, Any], enabled: bool
) -> dict[str, Any]:
    if not enabled:
        return {
            "first_test_budget_boundary_dry_run_only": "No aplica: sin producto en shortlist.",
            "success_signals": [],
            "warning_signals": [],
            "stop_signals": [],
            "continue_if": [],
            "review_if": [],
            "kill_if": [],
            "what_not_to_conclude": [],
            "no_pmf_claim": True,
            "no_analytics_fetch": True,
        }

    raw = _mapping(_mapping(fixture.get("marketing")).get("testing_plan_v2"))
    learning_raw = _mapping(fixture.get("learning"))
    return {
        "first_test_budget_boundary_dry_run_only": _text(
            raw.get("first_test_budget_boundary_dry_run_only"),
            "Boundary teorico solamente; Fase 1 es dry-run, sin gasto real.",
        ),
        "success_signals": _texts(raw.get("success_signals")),
        "warning_signals": _texts(raw.get("warning_signals")),
        "stop_signals": _texts(raw.get("stop_signals")),
        "continue_if": _texts(raw.get("continue_if")) or _texts(learning_raw.get("continue_if")),
        "review_if": _texts(raw.get("review_if")) or _texts(learning_raw.get("review_if")),
        "kill_if": _texts(raw.get("kill_if")) or _texts(learning_raw.get("kill_if")),
        "what_not_to_conclude": _texts(raw.get("what_not_to_conclude"))
        or ["No concluir product-market fit desde pruebas locales."],
        "no_pmf_claim": True,
        "no_analytics_fetch": True,
    }


def _generic_marketing_fallbacks(product_name: str) -> dict[str, Any]:
    """Deterministic conservative fallbacks used when the brief is too poor.

    Intentionally generic: this copy must read as low-confidence placeholder,
    never as expert output.
    """
    generic_note = (
        "Copy generico de baja confianza; enriquecer el brief del operador "
        "para obtener copy experto."
    )
    return {
        "strategy_summary": (
            f"Estrategia generica para {product_name}: brief pobre; "
            "solo copy descriptivo conservador. " + generic_note
        ),
        "core_angle": f"Presentacion descriptiva de {product_name} sin angulo diferenciado.",
        "why_this_angle": (
            "No hay brief suficiente para elegir un angulo; se usa descripcion "
            "conservadora del producto."
        ),
        "buyer_profile": "Perfil no definido: falta audiencia en el brief del operador.",
        "hooks": [
            f"Conoce {product_name}.",
            f"{product_name}, disponible para Mexico.",
        ],
        "headlines": [f"{product_name}"],
        "primary_texts": [f"{product_name}. {generic_note}"],
        "short_ads": [f"{product_name}. {generic_note}"],
        "long_ads": [f"{product_name}. {generic_note}"],
        "captions": [f"{product_name}."],
        "ugc_scripts": [],
        "video_scripts": [],
        "image_ad_concepts": [f"Foto simple de {product_name} sobre fondo neutro."],
        "channel_packs": [],
        "testing_plan": {
            "phase_1": "Enriquecer el brief del operador antes de disenar pruebas.",
            "budget_note": "Sin gasto en Fase 1.",
        },
    }


def build_marketing_pack(
    fixture: Mapping[str, Any],
    claim_guard: Mapping[str, Any],
    input_richness: Mapping[str, Any],
    has_product: bool,
) -> dict[str, Any]:
    if not has_product or not isinstance(fixture.get("marketing"), Mapping):
        pack = dict(_MARKETING_EMPTY_FIELDS)
        pack["enabled"] = False
        pack["disabled_reason"] = NO_PRODUCT_DISABLED_REASON
        pack["claim_guard"] = _claim_guard_notes(claim_guard, "marketing_pack")
        pack["confidence"] = {
            "level": "none",
            "label": "no_product_no_copy",
            "expert_method_applied": False,
            "market_validated": False,
            "note": "Sin producto en shortlist: no se genera copy.",
        }
        pack["input_richness_warning"] = ""
        pack["confidence_by_section"] = build_confidence_by_section(
            fixture, INPUT_LOW, [], [], enabled=False
        )
        pack["testing_plan_with_thresholds"] = build_testing_plan_with_thresholds(
            fixture, enabled=False
        )
        return pack

    raw = _mapping(fixture.get("marketing"))
    operator_input = _mapping(fixture.get("operator_input"))
    product = _mapping(fixture.get("product"))
    product_name = _text(product.get("name"), "Producto sin nombre")
    classification = _text(input_richness.get("classification"), INPUT_LOW)

    fallbacks = _generic_marketing_fallbacks(product_name)

    def pick_text(key: str) -> str:
        value = _text(raw.get(key))
        if value:
            return value
        return _text(fallbacks.get(key))

    def pick_list(key: str) -> list[str]:
        values = _texts(raw.get(key))
        if values:
            return values
        fallback = fallbacks.get(key)
        return _texts(fallback)

    channel_packs = [
        {
            "channel": _text(item.get("channel")),
            "objective": _text(item.get("objective")),
            "notes": _text(item.get("notes")),
        }
        for item in raw.get("channel_packs") or []
        if isinstance(item, Mapping)
    ]

    audience = _texts(raw.get("audience"))
    if not audience and _text(operator_input.get("target_audience")):
        audience = [_text(operator_input.get("target_audience"))]

    testing_plan = _mapping(raw.get("testing_plan")) or _mapping(fallbacks.get("testing_plan"))

    angle_matrix = build_angle_matrix(fixture)
    creative_hypotheses = build_creative_hypotheses(fixture)
    claim_risk_by_copy = build_claim_risk_by_copy(fixture, claim_guard)

    return {
        "enabled": True,
        "disabled_reason": "",
        "strategy_summary": pick_text("strategy_summary"),
        "core_angle": pick_text("core_angle"),
        "why_this_angle": pick_text("why_this_angle"),
        "buyer_profile": pick_text("buyer_profile"),
        "audience": audience,
        "pain_points": _texts(operator_input.get("pain_points")),
        "desire": _texts(operator_input.get("desires")),
        "objections": _texts(operator_input.get("objections")),
        "hooks": pick_list("hooks"),
        "headlines": pick_list("headlines"),
        "primary_texts": pick_list("primary_texts"),
        "short_ads": pick_list("short_ads"),
        "long_ads": pick_list("long_ads"),
        "captions": pick_list("captions"),
        "ugc_scripts": _texts(raw.get("ugc_scripts")),
        "video_scripts": _texts(raw.get("video_scripts")),
        "image_ad_concepts": pick_list("image_ad_concepts"),
        "channel_packs": channel_packs,
        "testing_plan": testing_plan,
        "angle_matrix": angle_matrix,
        "creative_hypotheses": creative_hypotheses,
        "claim_risk_by_copy": claim_risk_by_copy,
        "input_support_map": build_input_support_map(fixture),
        "missing_marketing_inputs": build_missing_marketing_inputs(fixture, input_richness),
        "confidence_by_section": build_confidence_by_section(
            fixture, classification, angle_matrix, claim_risk_by_copy, enabled=True
        ),
        "testing_plan_with_thresholds": build_testing_plan_with_thresholds(
            fixture, enabled=True
        ),
        "claim_guard": _claim_guard_notes(claim_guard, "marketing_pack"),
        "confidence": _marketing_confidence(classification),
        "input_richness_warning": _text(input_richness.get("warning")),
    }


def build_learning_plan(fixture: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(fixture.get("learning"))
    schema = _mapping(raw.get("operator_observations_schema"))
    return {
        "hypotheses": _texts(raw.get("hypotheses")),
        "evidence_needed": _texts(raw.get("evidence_needed")),
        "first_sale_signals": _texts(raw.get("first_sale_signals")),
        "risk_signals": _texts(raw.get("risk_signals")),
        "continue_if": _texts(raw.get("continue_if")),
        "review_if": _texts(raw.get("review_if")),
        "kill_if": _texts(raw.get("kill_if")),
        "operator_observations_schema": {"fields": _texts(schema.get("fields"))},
        "no_pmf_claim": True,
        "no_analytics_fetch": True,
        "operator_in_control": True,
    }


def _normalize_action(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_id": _text(item.get("action_id")),
        "label": _text(item.get("label")),
        "kind": _text(item.get("kind")),
        "target": _text(item.get("target")),
        "notes": _text(item.get("notes")),
    }


def build_blocked_queue(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for item in fixture.get("blocked") or []:
        if not isinstance(item, Mapping):
            continue
        queue.append(
            {
                "product_name": _text(item.get("product_name")),
                "reason": _text(item.get("reason")),
                "reason_codes": _texts(item.get("reason_codes")),
                "severity": _text(item.get("severity"), "unknown"),
                "can_recover": bool(item.get("can_recover", False)),
                "operator_actions": [
                    _normalize_action(action)
                    for action in item.get("operator_actions") or []
                    if isinstance(action, Mapping)
                ],
                "safety_boundary": dict(BLOCKED_ITEM_SAFETY_BOUNDARY),
            }
        )
    return queue


def build_operator_actions(
    fixture: Mapping[str, Any],
    input_richness: Mapping[str, Any],
    has_product: bool,
) -> list[dict[str, Any]]:
    actions = [
        _normalize_action(item)
        for item in fixture.get("operator_actions") or []
        if isinstance(item, Mapping)
    ]

    if has_product and input_richness.get("classification") == INPUT_LOW:
        missing = list(input_richness.get("missing_fields") or [])[:MAX_ENRICH_ACTIONS]
        for field_name in missing:
            actions.append(
                {
                    "action_id": f"enrich_input_{field_name}",
                    "label": f"Enriquecer brief del operador: completar '{field_name}'.",
                    "kind": "enrich_input",
                    "target": f"operator_input.{field_name}",
                    "notes": (
                        "R105.3: brief rico produce copy experto; "
                        "brief pobre produce copy generico."
                    ),
                }
            )
    return actions


def build_provenance(
    fixture: Mapping[str, Any],
    source_fixture: str,
    copy_payload_count: int,
) -> dict[str, Any]:
    evidence = _mapping(fixture.get("evidence"))
    return {
        "source_fixture": source_fixture,
        "source_kind": _text(fixture.get("source_kind"), SOURCE_KIND_DEFAULT),
        "adapter_status": "frozen_fixture_adapter",
        "base_head": BASE_HEAD,
        "fase_1_status": FASE_1_STATUS,
        "island": ISLAND,
        "deterministic_renderer": True,
        "no_runtime_network": True,
        "no_runtime_clock": True,
        "copy_payload_count": copy_payload_count,
        "evidence_notes": _texts(evidence.get("notes")),
    }


# --- copy payload assembly ---------------------------------------------------

def _claim_guard_block(claim_guard: Mapping[str, Any], surface_label: str) -> str:
    parts = [f"CLAIM GUARD ({surface_label}):", f"Resumen: {claim_guard['claim_guard_summary']}"]
    for title, key in (
        ("Permitidos", "allowed_claims"),
        ("Riesgosos", "risky_claims"),
        ("Prohibidos", "prohibited_claims"),
        ("Redaccion segura", "safe_wording"),
    ):
        items = list(claim_guard.get(key) or [])
        parts.append(f"{title}:")
        parts.append(_lines(items) if items else "- (ninguno)")
    return "\n".join(parts)


def _spec_lines(specifications: Sequence[Mapping[str, Any]]) -> str:
    rows = [f"- {item['name']}: {item['value']}" for item in specifications]
    return "\n".join(rows) if rows else "- (sin especificaciones)"


def _faq_lines(faq: Sequence[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    for item in faq:
        rows.append(f"P: {item['q']}")
        rows.append(f"R: {item['a']}")
    return "\n".join(rows) if rows else "(sin FAQ)"


def _shopify_full_pack_text(shopify_pack: Mapping[str, Any], claim_guard: Mapping[str, Any]) -> str:
    pack = shopify_pack
    parts = [
        "SHOPIFY PACK",
        "============",
        f"Producto: {pack['title']}",
        f"Subtitulo: {pack['subtitle']}",
        f"Handle: {pack['handle']}",
        f"Categoria: {pack['category']}",
        "Tags: " + ", ".join(pack["tags"]),
        f"Precio: {pack['price']}",
        f"Precio de comparacion: {pack['compare_at_price']}",
        "",
        "Descripcion corta:",
        pack["short_description"],
        "",
        "Descripcion larga:",
        pack["long_description"],
        "",
        "Bullets:",
        _lines(pack["bullets"]) or "- (sin bullets)",
        "",
        "Beneficios:",
        _lines(pack["benefits"]) or "- (sin beneficios)",
        "",
        "Especificaciones:",
        _spec_lines(pack["specifications"]),
        "",
        "FAQ:",
        _faq_lines(pack["faq"]),
        "",
        f"SEO titulo: {pack['seo_title']}",
        f"SEO meta descripcion: {pack['seo_meta_description']}",
        "",
        f"Nota de envio: {pack['shipping_note']}",
        f"Nota de devoluciones: {pack['refund_claim_note']}",
        f"Disclaimer claim-safe: {pack['claim_safe_disclaimer']}",
        "",
        "Inputs faltantes:",
        _lines(pack["missing_inputs"]) or "- (ninguno)",
        "",
        _claim_guard_block(claim_guard, "Shopify"),
    ]
    return "\n".join(parts)


def _marketing_full_pack_text(
    marketing_pack: Mapping[str, Any], claim_guard: Mapping[str, Any]
) -> str:
    pack = marketing_pack
    confidence = _mapping(pack.get("confidence"))
    parts = [
        "MARKETING PACK",
        "==============",
        f"Resumen de estrategia: {pack['strategy_summary']}",
        f"Angulo central: {pack['core_angle']}",
        f"Por que este angulo: {pack['why_this_angle']}",
        f"Perfil del comprador: {pack['buyer_profile']}",
        "",
        "Audiencias:",
        _lines(pack["audience"]) or "- (sin audiencias)",
        "",
        "Dolores:",
        _lines(pack["pain_points"]) or "- (sin dolores)",
        "",
        "Deseos:",
        _lines(pack["desire"]) or "- (sin deseos)",
        "",
        "Objeciones:",
        _lines(pack["objections"]) or "- (sin objeciones)",
        "",
        "Hooks:",
        _lines(pack["hooks"]) or "- (sin hooks)",
        "",
        "Headlines:",
        _lines(pack["headlines"]) or "- (sin headlines)",
        "",
        "Textos primarios:",
        _lines(pack["primary_texts"]) or "- (sin textos primarios)",
        "",
        "Anuncios cortos:",
        _lines(pack["short_ads"]) or "- (sin anuncios cortos)",
        "",
        "Anuncios largos:",
        _lines(pack["long_ads"]) or "- (sin anuncios largos)",
        "",
        "Captions:",
        _lines(pack["captions"]) or "- (sin captions)",
        "",
        "Guiones UGC:",
        _lines(pack["ugc_scripts"]) or "- (sin guiones UGC)",
        "",
        "Guiones de video:",
        _lines(pack["video_scripts"]) or "- (sin guiones de video)",
        "",
        "Conceptos de imagen:",
        _lines(pack["image_ad_concepts"]) or "- (sin conceptos de imagen)",
        "",
        f"Confianza: {confidence.get('level', '')} ({confidence.get('label', '')})",
        f"Nota de confianza: {confidence.get('note', '')}",
    ]
    warning = _text(pack.get("input_richness_warning"))
    if warning:
        parts.append(f"ADVERTENCIA: {warning}")
    parts.extend(["", _claim_guard_block(claim_guard, "Marketing")])
    return "\n".join(parts)


def _marketing_full_pack_v2_text(
    marketing_pack: Mapping[str, Any], claim_guard: Mapping[str, Any]
) -> str:
    pack = marketing_pack
    parts = [
        "MARKETING PACK V2",
        "=================",
        f"Angulo central: {pack['core_angle']}",
        f"Resumen de estrategia: {pack['strategy_summary']}",
        "",
        "CONFIANZA POR SECCION:",
    ]
    confidence_by_section = _mapping(pack.get("confidence_by_section"))
    for section in CONFIDENCE_SECTIONS:
        entry = _mapping(confidence_by_section.get(section))
        parts.append(
            f"- {section}: {entry.get('level', 'unknown')} ({entry.get('basis', '')})"
        )

    parts.extend(["", "MATRIZ DE ANGULOS:"])
    angles = pack.get("angle_matrix") or []
    if not angles:
        parts.append("(sin angulos definidos)")
    for angle in angles:
        parts.append(f"[{angle['angle_id']}] {angle['angle_name']}")
        for label, key in (
            ("promise_type", "promise_type"),
            ("target_segment", "target_segment"),
            ("pain_addressed", "pain_addressed"),
            ("desire_addressed", "desire_addressed"),
            ("objection_addressed", "objection_addressed"),
            ("proof_needed", "proof_needed"),
            ("claim_risk", "claim_risk"),
            ("safe_wording", "safe_wording"),
            ("por_que_puede_funcionar", "why_it_might_work"),
            ("por_que_puede_fallar", "why_it_might_fail"),
        ):
            parts.append(f"- {label}: {angle[key]}")
        parts.append("")

    parts.append("HIPOTESIS CREATIVAS:")
    hypotheses = pack.get("creative_hypotheses") or []
    if not hypotheses:
        parts.append("(sin hipotesis definidas)")
    for hypothesis in hypotheses:
        parts.append(f"[{hypothesis['hypothesis_id']}] {hypothesis['hypothesis']}")
        for key in (
            "variable_tested",
            "expected_signal",
            "failure_signal",
            "minimum_evidence_needed",
            "channel",
            "linked_angle_id",
        ):
            parts.append(f"- {key}: {hypothesis[key]}")
        parts.append("")

    parts.append("RIESGO DE CLAIMS POR COPY:")
    for entry in pack.get("claim_risk_by_copy") or []:
        risky = ", ".join(entry["risky_terms"]) or "(ninguno)"
        prohibited = ", ".join(entry["prohibited_terms"]) or "(ninguno)"
        parts.append(
            f"- {entry['copy_key']} | riesgo: {entry['risk_level']} | "
            f"terminos riesgosos: {risky} | terminos prohibidos: {prohibited}"
        )
        parts.append(f"  rewrite seguro: {entry['safe_rewrite']}")
        parts.append(f"  razon: {entry['reason']}")

    parts.extend(["", "MAPA DE SOPORTE DE INPUTS:"])
    for entry in pack.get("input_support_map") or []:
        support = ", ".join(entry["support_fields"]) or "(sin soporte)"
        status = "soportado" if entry["supported"] else "NO SOPORTADO: fallback generico"
        parts.append(f"- {entry['output_key']} <- {support} [{status}]")

    plan = _mapping(pack.get("testing_plan_with_thresholds"))
    parts.extend(
        [
            "",
            "PLAN DE PRUEBAS CON UMBRALES:",
            f"Boundary de presupuesto (solo dry-run): "
            f"{plan.get('first_test_budget_boundary_dry_run_only', '')}",
        ]
    )
    for title, key in (
        ("Senales de exito", "success_signals"),
        ("Senales de advertencia", "warning_signals"),
        ("Senales de alto", "stop_signals"),
        ("Continuar si", "continue_if"),
        ("Revisar si", "review_if"),
        ("Matar si", "kill_if"),
        ("No concluir", "what_not_to_conclude"),
    ):
        items = _texts(plan.get(key))
        parts.append(f"{title}:")
        parts.append(_lines(items) if items else "- (sin criterio)")
    parts.append("Sin claim de PMF: si. Sin fetch de analytics: si.")

    parts.extend(["", _claim_guard_block(claim_guard, "Marketing V2")])
    return "\n".join(parts)


def _learning_snapshot_text(learning_plan: Mapping[str, Any]) -> str:
    parts = [
        "LEARNING PLAN",
        "=============",
        "Hipotesis:",
        _lines(learning_plan["hypotheses"]) or "- (sin hipotesis)",
        "Evidencia necesaria:",
        _lines(learning_plan["evidence_needed"]) or "- (sin evidencia definida)",
        "Senales de primera venta:",
        _lines(learning_plan["first_sale_signals"]) or "- (sin senales definidas)",
        "Senales de riesgo:",
        _lines(learning_plan["risk_signals"]) or "- (sin senales definidas)",
        "Continuar si:",
        _lines(learning_plan["continue_if"]) or "- (sin criterio)",
        "Revisar si:",
        _lines(learning_plan["review_if"]) or "- (sin criterio)",
        "Matar si:",
        _lines(learning_plan["kill_if"]) or "- (sin criterio)",
        "Sin claim de PMF: si. Sin fetch de analytics: si. Operador en control: si.",
    ]
    return "\n".join(parts)


def _safety_summary_text() -> str:
    parts = ["SAFETY BOUNDARY (Fase 1)", "========================"]
    for key, value in SAFETY_BOUNDARY.items():
        parts.append(f"- {key}: {'si' if value else 'no'}")
    return "\n".join(parts)


def build_copy_payloads(
    has_product: bool,
    shopify_pack: Mapping[str, Any],
    marketing_pack: Mapping[str, Any],
    learning_plan: Mapping[str, Any],
    claim_guard: Mapping[str, Any],
) -> dict[str, Any]:
    if not has_product:
        return {
            "enabled": False,
            "disabled_reason": NO_PRODUCT_DISABLED_REASON,
            "count": 0,
            "items": [],
        }

    items = [
        CopyPayload(
            key="shopify_title",
            label="Titulo Shopify",
            section="shopify_pack",
            text=_text(shopify_pack["title"]),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack.title",),
        ),
        CopyPayload(
            key="shopify_price",
            label="Precio Shopify",
            section="shopify_pack",
            text=_text(shopify_pack["price"]),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack.price",),
        ),
        CopyPayload(
            key="shopify_short_description",
            label="Descripcion corta Shopify",
            section="shopify_pack",
            text=_text(shopify_pack["short_description"]),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack.short_description",),
        ),
        CopyPayload(
            key="shopify_long_description",
            label="Descripcion larga Shopify",
            section="shopify_pack",
            text=_text(shopify_pack["long_description"]),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack.long_description",),
        ),
        CopyPayload(
            key="shopify_bullets",
            label="Bullets Shopify",
            section="shopify_pack",
            text=_lines(shopify_pack["bullets"]),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack.bullets",),
        ),
        CopyPayload(
            key="shopify_full_pack",
            label="Shopify pack completo",
            section="shopify_pack",
            text=_shopify_full_pack_text(shopify_pack, claim_guard),
            claim_guard_ref="claim_guard.shopify",
            source_fields=("shopify_pack", "economics", "claim_guard"),
        ),
        CopyPayload(
            key="marketing_hooks",
            label="Hooks de marketing",
            section="marketing_pack",
            text=_lines(marketing_pack["hooks"]),
            claim_guard_ref="claim_guard.marketing",
            source_fields=("marketing_pack.hooks",),
        ),
        CopyPayload(
            key="marketing_short_ads",
            label="Anuncios cortos",
            section="marketing_pack",
            text=_lines(marketing_pack["short_ads"]),
            claim_guard_ref="claim_guard.marketing",
            source_fields=("marketing_pack.short_ads",),
        ),
        CopyPayload(
            key="marketing_long_ads",
            label="Anuncios largos",
            section="marketing_pack",
            text=_lines(marketing_pack["long_ads"]),
            claim_guard_ref="claim_guard.marketing",
            source_fields=("marketing_pack.long_ads",),
        ),
        CopyPayload(
            key="marketing_full_pack",
            label="Marketing pack completo",
            section="marketing_pack",
            text=_marketing_full_pack_text(marketing_pack, claim_guard),
            claim_guard_ref="claim_guard.marketing",
            source_fields=("marketing_pack", "operator_input", "claim_guard"),
        ),
        CopyPayload(
            key="marketing_full_pack_v2",
            label="Marketing pack completo V2 (profundidad)",
            section="marketing_pack",
            text=_marketing_full_pack_v2_text(marketing_pack, claim_guard),
            claim_guard_ref="claim_guard.marketing",
            source_fields=(
                "marketing_pack.angle_matrix",
                "marketing_pack.creative_hypotheses",
                "marketing_pack.claim_risk_by_copy",
                "marketing_pack.input_support_map",
                "marketing_pack.confidence_by_section",
                "marketing_pack.testing_plan_with_thresholds",
            ),
        ),
        CopyPayload(
            key="learning_snapshot",
            label="Snapshot del learning plan",
            section="learning_plan",
            text=_learning_snapshot_text(learning_plan),
            claim_guard_ref="claim_guard.none",
            source_fields=("learning_plan",),
        ),
        CopyPayload(
            key="safety_summary",
            label="Resumen de safety boundary",
            section="safety_boundary",
            text=_safety_summary_text(),
            claim_guard_ref="claim_guard.none",
            source_fields=("safety_boundary",),
        ),
    ]

    return {
        "enabled": True,
        "disabled_reason": "",
        "count": len(items),
        "items": [asdict(item) for item in items],
    }


# --- A8-R109A.1 system surface builders ---------------------------------------

def _decision_outcome(fixture: Mapping[str, Any]) -> str:
    return _text(_mapping(fixture.get("decision")).get("outcome"))


def _has_prohibited_copy(marketing_pack: Mapping[str, Any]) -> bool:
    return any(
        _text(entry.get("risk_level")) == "prohibited"
        for entry in marketing_pack.get("claim_risk_by_copy") or []
    )


def _medium_rewrite_count(marketing_pack: Mapping[str, Any]) -> int:
    return sum(
        1
        for entry in marketing_pack.get("claim_risk_by_copy") or []
        if _text(entry.get("risk_level")) == "medium"
    )


def build_module_status_summary(
    fixture: Mapping[str, Any],
    claim_guard: Mapping[str, Any],
    input_richness: Mapping[str, Any],
    shopify_pack: Mapping[str, Any],
    marketing_pack: Mapping[str, Any],
    blocked_queue: Sequence[Mapping[str, Any]],
    operator_actions: Sequence[Mapping[str, Any]],
    has_product: bool,
) -> list[dict[str, Any]]:
    """Per-module health so R109B renders real status instead of inferring it."""
    decision = _mapping(fixture.get("decision"))
    outcome = _text(decision.get("outcome"))
    reason = _text(decision.get("reason"))
    reason_codes = _texts(decision.get("reason_codes"))
    economics = _mapping(fixture.get("economics"))
    classification = _text(input_richness.get("classification"))
    filled = int(input_richness.get("filled_count") or 0)
    total = int(input_richness.get("total_fields") or 0)
    missing_fields = _texts(input_richness.get("missing_fields"))

    prohibited_copy = _has_prohibited_copy(marketing_pack)
    rewrites = _medium_rewrite_count(marketing_pack)
    primary_action = _text(operator_actions[0].get("label")) if operator_actions else ""

    def outcome_status() -> str:
        if not has_product:
            return MODULE_STATUS_EMPTY
        if outcome == OUTCOME_BLOCKED:
            return MODULE_STATUS_BLOCKED
        if outcome == OUTCOME_RECOMMENDED:
            return MODULE_STATUS_PASS
        return MODULE_STATUS_WARNING

    entries: list[dict[str, Any]] = []

    def add(
        module_id: str,
        status: str,
        badge_text: str,
        summary: str,
        operator_action: str,
        source_fields: Sequence[str],
        *,
        is_real_now: bool = True,
        is_future_placeholder: bool = False,
    ) -> None:
        entries.append(
            {
                "module_id": module_id,
                "label": MODULE_LABELS[module_id],
                "status": status,
                "badge_text": badge_text,
                "summary": summary,
                "operator_action": operator_action,
                "source_fields": list(source_fields),
                "is_real_now": is_real_now,
                "is_future_placeholder": is_future_placeholder,
            }
        )

    command_badges = {
        MODULE_STATUS_PASS: "GO",
        MODULE_STATUS_BLOCKED: "BLOQUEADO",
        MODULE_STATUS_WARNING: "REVISION",
        MODULE_STATUS_EMPTY: "SIN CANDIDATO",
    }
    command_status = outcome_status()
    add(
        "command_center",
        command_status,
        command_badges[command_status],
        reason,
        primary_action,
        ("decision.outcome", "decision.reason", "operator_actions"),
    )

    add(
        "decision_center",
        outcome_status(),
        outcome or "N/A",
        ", ".join(reason_codes),
        "Leer caveats antes de invertir tiempo en el candidato.",
        ("decision", "scores"),
    )

    if not has_product:
        add(
            "product_lab",
            MODULE_STATUS_EMPTY,
            "SIN BRIEF",
            "Sin producto en shortlist: no hay brief que trabajar.",
            "",
            ("input_richness",),
        )
    else:
        lab_status = MODULE_STATUS_PASS if classification == INPUT_RICH else MODULE_STATUS_WARNING
        lab_action = (
            "Completar campos faltantes del brief: " + ", ".join(missing_fields[:MAX_ENRICH_ACTIONS])
            if missing_fields
            else ""
        )
        add(
            "product_lab",
            lab_status,
            f"{filled}/{total}",
            f"Brief clasificado {classification} ({filled}/{total} campos).",
            lab_action,
            ("input_richness",),
        )

    margin_percent = economics.get("contribution_margin_percent")
    if not has_product:
        add(
            "economics",
            MODULE_STATUS_EMPTY,
            "SIN ECONOMIA",
            "Sin producto seleccionado: no hay economia que evaluar.",
            "",
            ("economics",),
        )
    elif "MARGIN_BELOW_FLOOR" in reason_codes:
        add(
            "economics",
            MODULE_STATUS_BLOCKED,
            f"{margin_percent}%",
            "Margen debajo del piso economico definido en la evaluacion local.",
            "Renegociar costo o envio antes de reconsiderar el producto.",
            ("economics", "decision.reason_codes"),
        )
    else:
        add(
            "economics",
            MODULE_STATUS_PASS,
            f"{margin_percent}%",
            "Margen de contribucion sobre el piso; numeros locales del fixture.",
            "Memorizar el CPA breakeven antes de planear pruebas.",
            ("economics",),
        )

    if not shopify_pack.get("enabled"):
        add(
            "shopify_studio",
            MODULE_STATUS_EMPTY,
            "DESHABILITADO",
            f"Pack deshabilitado: {_text(shopify_pack.get('disabled_reason'))}.",
            "",
            ("shopify_pack.enabled", "shopify_pack.disabled_reason"),
        )
    elif outcome == OUTCOME_BLOCKED:
        add(
            "shopify_studio",
            MODULE_STATUS_BLOCKED,
            "NO PUBLICAR",
            "Producto bloqueado: el pack existe solo como registro; no publicar.",
            "Resolver el bloqueo antes de cualquier checklist de publicacion.",
            ("shopify_pack", "decision.outcome"),
        )
    else:
        missing_inputs = _texts(shopify_pack.get("missing_inputs"))
        if missing_inputs:
            add(
                "shopify_studio",
                MODULE_STATUS_WARNING,
                f"{len(missing_inputs)} FALTAN",
                "Pack copy-ready con inputs pendientes: " + ", ".join(missing_inputs) + ".",
                _texts(shopify_pack.get("publish_checklist"))[0]
                if shopify_pack.get("publish_checklist")
                else "",
                ("shopify_pack.missing_inputs", "shopify_pack.publish_checklist"),
            )
        else:
            add(
                "shopify_studio",
                MODULE_STATUS_PASS,
                "LISTO",
                "Pack copy-ready sin inputs pendientes.",
                "Revisar claim guard antes de publicar.",
                ("shopify_pack",),
            )

    if not marketing_pack.get("enabled"):
        add(
            "marketing_engine",
            MODULE_STATUS_EMPTY,
            "DESHABILITADO",
            f"Pack deshabilitado: {_text(marketing_pack.get('disabled_reason'))}.",
            "",
            ("marketing_pack.enabled", "marketing_pack.disabled_reason"),
        )
    elif prohibited_copy:
        add(
            "marketing_engine",
            MODULE_STATUS_BLOCKED,
            "CLAIMS PROHIBIDOS",
            "Todo el copy depende de claims prohibidos; no hay angulo utilizable.",
            "Reposicionar el producto sin claims prohibidos antes de crear copy.",
            ("marketing_pack.claim_risk_by_copy",),
        )
    elif classification == INPUT_LOW:
        add(
            "marketing_engine",
            MODULE_STATUS_WARNING,
            "COPY GENERICO",
            "Brief pobre: el copy es generico y de baja confianza (R105.3).",
            "Enriquecer el brief del operador para obtener copy experto.",
            ("marketing_pack.confidence", "input_richness.classification"),
        )
    elif rewrites:
        add(
            "marketing_engine",
            MODULE_STATUS_WARNING,
            f"{rewrites} REWRITES",
            f"Copy listo con {rewrites} superficies en riesgo medio pendientes de rewrite.",
            "Aplicar los rewrites seguros antes de publicar.",
            ("marketing_pack.claim_risk_by_copy", "marketing_pack.confidence_by_section"),
        )
    else:
        add(
            "marketing_engine",
            MODULE_STATUS_PASS,
            "LISTO",
            "Copy listo sin superficies en riesgo medio o superior.",
            "Elegir angulo y preparar la primera tanda de creativos.",
            ("marketing_pack.claim_risk_by_copy", "marketing_pack.confidence_by_section"),
        )

    if outcome == OUTCOME_BLOCKED or prohibited_copy:
        add(
            "safety_claim_guard",
            MODULE_STATUS_BLOCKED,
            "RIESGO CRITICO",
            _text(claim_guard.get("claim_guard_summary")),
            "No preparar venta mientras el claim central sea prohibido.",
            ("claim_guard", "decision.outcome"),
        )
    elif not has_product:
        add(
            "safety_claim_guard",
            MODULE_STATUS_PASS,
            "BOUNDARY OK",
            "Sin copy activo; boundary de Fase 1 intacto.",
            "",
            ("claim_guard", "safety_boundary"),
        )
    else:
        add(
            "safety_claim_guard",
            MODULE_STATUS_PASS,
            "RIESGO BAJO",
            _text(claim_guard.get("claim_guard_summary")),
            "Aplicar la redaccion segura en todas las superficies de copy.",
            ("claim_guard",),
        )

    evidence_notes = _texts(_mapping(fixture.get("evidence")).get("notes"))
    add(
        "evidence",
        MODULE_STATUS_AUDIT,
        "AUDIT",
        evidence_notes[0] if evidence_notes else "Procedencia del fixture congelado.",
        "Abrir solo para auditar procedencia.",
        ("evidence", "provenance"),
    )

    add(
        "learning_feedback",
        MODULE_STATUS_FUTURE,
        "FASE 2",
        "Esquema de observaciones definido; datos en vivo no conectados.",
        "Registrar observaciones manualmente cuando existan datos reales.",
        ("learning_plan",),
        is_real_now=False,
        is_future_placeholder=True,
    )

    blocked_count = len(blocked_queue)
    add(
        "blocked_queue",
        MODULE_STATUS_BLOCKED if blocked_count else MODULE_STATUS_EMPTY,
        f"{blocked_count} EN COLA",
        (
            "Hay productos bloqueados esperando decision del operador."
            if blocked_count
            else "Cola de bloqueados vacia."
        ),
        "Decidir reparar o rechazar cada item bloqueado." if blocked_count else "",
        ("blocked_queue",),
    )

    return entries


def build_candidate_pipeline(
    fixture: Mapping[str, Any],
    input_richness: Mapping[str, Any],
    blocked_queue: Sequence[Mapping[str, Any]],
    has_product: bool,
) -> dict[str, Any]:
    """Fixture-honest pipeline summary: never claims live discovery counts."""
    raw = _mapping(fixture.get("pipeline"))
    outcome = _decision_outcome(fixture)
    classification = _text(input_richness.get("classification"))
    product_id = _text(_mapping(fixture.get("product")).get("product_id"))

    if outcome == OUTCOME_RECOMMENDED:
        stage = "prepare_for_sale"
    elif outcome == OUTCOME_BLOCKED:
        stage = "blocked_review"
    elif outcome == OUTCOME_REVIEW:
        stage = "enrich_brief"
    else:
        stage = "await_shortlist"

    try:
        total_candidates = int(raw.get("total_candidates"))
    except (TypeError, ValueError):
        total_candidates = 1 if has_product else 0
    try:
        current_rank = int(raw.get("current_candidate_rank"))
    except (TypeError, ValueError):
        current_rank = 1 if has_product else 0

    return {
        "source": _text(raw.get("source"), PIPELINE_SOURCE_FIXTURE),
        "confidence": PIPELINE_CONFIDENCE_LIMITED,
        "live_discovery_connected": False,
        "total_candidates": total_candidates,
        "recommended_count": 1 if outcome == OUTCOME_RECOMMENDED else 0,
        "blocked_count": len(blocked_queue),
        "low_input_count": 1 if has_product and classification == INPUT_LOW else 0,
        "empty_count": 0 if has_product else 1,
        "current_candidate_id": product_id,
        "current_candidate_rank": current_rank,
        "pipeline_stage": stage,
        "pipeline_note": PIPELINE_NOTE_FIXTURE_ONLY,
        "source_fields": [
            "decision.outcome",
            "product.product_id",
            "blocked",
            "input_richness.classification",
        ],
    }


def build_blocked_queue_summary(
    fixture: Mapping[str, Any],
    blocked_queue: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    outcome = _decision_outcome(fixture)
    reason_codes: list[str] = []
    required_actions: list[str] = []
    items: list[dict[str, Any]] = []
    for item in blocked_queue:
        items.append(
            {
                "product_name": _text(item.get("product_name")),
                "reason": _text(item.get("reason")),
                "reason_codes": _texts(item.get("reason_codes")),
                "severity": _text(item.get("severity"), "unknown"),
                "can_recover": bool(item.get("can_recover", False)),
            }
        )
        reason_codes.extend(_texts(item.get("reason_codes")))
        required_actions.extend(
            _text(action.get("label"))
            for action in item.get("operator_actions") or []
            if _text(action.get("label"))
        )
    return {
        "blocked_count": len(blocked_queue),
        "blocked_items": items,
        "reason_codes": sorted(set(reason_codes)),
        "required_operator_actions": required_actions,
        "can_prepare": outcome == OUTCOME_RECOMMENDED,
        "source_fields": ["blocked", "decision.outcome"],
    }


def build_action_queue(
    operator_actions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Ordered operator actions with one explicit primary (no UI inference)."""
    queue: list[dict[str, Any]] = []
    for index, action in enumerate(operator_actions):
        queue.append(
            {
                "action_id": _text(action.get("action_id")),
                "label": _text(action.get("label")),
                "reason": _text(action.get("notes")),
                "target_module": ACTION_KIND_TO_MODULE.get(
                    _text(action.get("kind")), ACTION_DEFAULT_MODULE
                ),
                "priority": index + 1,
                "source_fields": [f"operator_actions[{index}]"],
                "is_primary": index == 0,
            }
        )
    return queue


def build_system_health_board(
    fixture: Mapping[str, Any],
    claim_guard: Mapping[str, Any],
    input_richness: Mapping[str, Any],
    shopify_pack: Mapping[str, Any],
    marketing_pack: Mapping[str, Any],
    has_product: bool,
) -> dict[str, Any]:
    outcome = _decision_outcome(fixture)
    prohibited_copy = _has_prohibited_copy(marketing_pack)
    classification = _text(input_richness.get("classification"))

    if outcome == OUTCOME_BLOCKED or prohibited_copy:
        claim_guard_status = "blocked"
    elif _texts(claim_guard.get("risky_claims")):
        claim_guard_status = "risky_claims_flagged"
    else:
        claim_guard_status = "clear"

    if not shopify_pack.get("enabled"):
        shopify_status = "disabled"
    elif outcome == OUTCOME_BLOCKED:
        shopify_status = "blocked_do_not_publish"
    elif _texts(shopify_pack.get("missing_inputs")):
        shopify_status = "ready_with_missing_inputs"
    else:
        shopify_status = "ready"

    if not marketing_pack.get("enabled"):
        marketing_status = "disabled"
    elif prohibited_copy:
        marketing_status = "blocked_by_claims"
    elif classification == INPUT_LOW:
        marketing_status = "generic_low_confidence"
    elif _medium_rewrite_count(marketing_pack):
        marketing_status = "ready_with_pending_rewrites"
    else:
        marketing_status = "ready"

    return {
        "offline_mode": SAFETY_BOUNDARY["no_external_network"],
        "no_live_writes": SAFETY_BOUNDARY["no_live_writes"],
        "no_spend": SAFETY_BOUNDARY["no_spend"],
        "no_fulfillment": SAFETY_BOUNDARY["no_fulfillment"],
        "no_credentials": SAFETY_BOUNDARY["no_credentials_required"],
        "claim_guard_status": claim_guard_status,
        "input_richness_status": classification if has_product else "NO_PRODUCT",
        "shopify_pack_status": shopify_status,
        "marketing_pack_status": marketing_status,
        "evidence_status": "frozen_fixture_audit_trail",
        "source_fields": [
            "safety_boundary",
            "claim_guard",
            "input_richness",
            "shopify_pack",
            "marketing_pack",
        ],
    }


def build_capability_surface_map() -> dict[str, list[str]]:
    """What the UI may claim today vs never; static so it cannot drift."""
    return {tier: list(items) for tier, items in CAPABILITY_SURFACE_MAP.items()}


# --- top-level assembly -------------------------------------------------------

def load_fixture(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Fixture must be a JSON object: {path}")
    return data


def build_view_model(
    fixture: Mapping[str, Any],
    source_fixture: str = "",
) -> WorkbenchViewModel:
    """Build the deterministic R109A ViewModel from a frozen fixture mapping."""
    product = _mapping(fixture.get("product"))
    has_product = bool(product)

    input_richness = classify_input_richness(_mapping(fixture.get("operator_input")))
    claim_guard = build_claim_guard(fixture)
    shopify_pack = build_shopify_pack(fixture, claim_guard, has_product)
    marketing_pack = build_marketing_pack(fixture, claim_guard, input_richness, has_product)
    learning_plan = build_learning_plan(fixture)
    blocked_queue = build_blocked_queue(fixture)
    operator_actions = build_operator_actions(fixture, input_richness, has_product)
    copy_payloads = build_copy_payloads(
        has_product, shopify_pack, marketing_pack, learning_plan, claim_guard
    )
    evidence = {
        "notes": _texts(_mapping(fixture.get("evidence")).get("notes")),
        "artifacts": _texts(_mapping(fixture.get("evidence")).get("artifacts")),
        "source_kind": _text(fixture.get("source_kind"), SOURCE_KIND_DEFAULT),
    }
    provenance = build_provenance(fixture, source_fixture, int(copy_payloads["count"]))

    module_status_summary = build_module_status_summary(
        fixture,
        claim_guard,
        input_richness,
        shopify_pack,
        marketing_pack,
        blocked_queue,
        operator_actions,
        has_product,
    )
    candidate_pipeline = build_candidate_pipeline(
        fixture, input_richness, blocked_queue, has_product
    )
    blocked_queue_summary = build_blocked_queue_summary(fixture, blocked_queue)
    action_queue = build_action_queue(operator_actions)
    system_health_board = build_system_health_board(
        fixture, claim_guard, input_richness, shopify_pack, marketing_pack, has_product
    )

    return WorkbenchViewModel(
        schema_version=SCHEMA_VERSION,
        fixture_id=_text(fixture.get("fixture_id"), "unknown_fixture"),
        render_mode=RENDER_MODE,
        source_kind=_text(fixture.get("source_kind"), SOURCE_KIND_DEFAULT),
        generated_at_policy=GENERATED_AT_POLICY,
        product=product,
        decision=_mapping(fixture.get("decision")),
        economics=_mapping(fixture.get("economics")),
        scores=_mapping(fixture.get("scores")),
        input_richness=input_richness,
        claim_guard=claim_guard,
        shopify_pack=shopify_pack,
        marketing_pack=marketing_pack,
        learning_plan=learning_plan,
        blocked_queue=tuple(blocked_queue),
        operator_actions=tuple(operator_actions),
        provenance=provenance,
        safety_boundary=dict(SAFETY_BOUNDARY),
        evidence=evidence,
        copy_payloads=copy_payloads,
        module_status_summary=tuple(module_status_summary),
        candidate_pipeline=candidate_pipeline,
        blocked_queue_summary=blocked_queue_summary,
        action_queue=tuple(action_queue),
        system_health_board=system_health_board,
        capability_surface_map=build_capability_surface_map(),
    )


def build_view_model_from_path(path: str | Path) -> WorkbenchViewModel:
    fixture_path = Path(path)
    return build_view_model(load_fixture(fixture_path), source_fixture=fixture_path.as_posix())

"""A8-R111 I1: local catalog fixture -> sealed methodology decision.

The bridge accepts only an already validated A8-R110 local-catalog fixture plus
explicit operator methodology context. It never derives buyer state, claim
risk, channel, margin profile, proof, or product facts.

It performs no network access, external writes, spend, publication, campaign
creation, Shopify mutation, Meta mutation, or fulfillment.
"""

from __future__ import annotations

import copy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.marketing_os.methodology_decision_engine import (
    DEFAULT_SPEC_PATH,
    MethodologyDecisionEngineError,
    MethodologyDecisionInput,
    decide_marketing_methodology,
    decision_input_from_fixture_context,
)
from synapse.marketing_os.methodology_rule_loader import (
    MethodologyRuleLoaderError,
    load_methodology_contract,
)

LOCAL_CATALOG_SOURCE_KIND = "operator_local_catalog_import"

_REQUIRED_CONTEXT_FIELDS: tuple[str, ...] = (
    "product_facts",
    "buyer_state",
    "proof_available",
    "claim_risk",
    "channel",
    "margin_profile",
    "category",
)

_ALLOWED_CONTEXT_FIELDS = frozenset(
    (*_REQUIRED_CONTEXT_FIELDS, "candidate_output")
)


class LocalCatalogMethodologyBridgeError(ValueError):
    """Raised when the R110 -> methodology bridge must fail closed."""


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalCatalogMethodologyBridgeError(
            f"{path} must be a mapping"
        )
    return value


def _require_nonempty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalCatalogMethodologyBridgeError(
            f"{path} must be a non-empty string"
        )
    return value.strip()


def _require_optional_text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise LocalCatalogMethodologyBridgeError(
            f"{path} must be a string"
        )
    return value


def _require_string_sequence(
    value: Any,
    path: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise LocalCatalogMethodologyBridgeError(
            f"{path} must be a sequence of strings"
        )

    materialized: list[str] = []

    for index, item in enumerate(value):
        materialized.append(
            _require_nonempty_text(item, f"{path}[{index}]")
        )

    if not allow_empty and not materialized:
        raise LocalCatalogMethodologyBridgeError(
            f"{path} must contain at least one value"
        )

    return tuple(materialized)


def _validate_fixture_contract(
    fixture: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    source_kind = _require_nonempty_text(
        fixture.get("source_kind"),
        "fixture.source_kind",
    )

    if source_kind != LOCAL_CATALOG_SOURCE_KIND:
        raise LocalCatalogMethodologyBridgeError(
            "fixture.source_kind must be operator_local_catalog_import"
        )

    product = _require_mapping(
        fixture.get("product"),
        "fixture.product",
    )

    fixture_category = _require_nonempty_text(
        product.get("category"),
        "fixture.product.category",
    )

    decision = _require_mapping(
        fixture.get("decision"),
        "fixture.decision",
    )

    if decision.get("permission_gate") != "REVIEW":
        raise LocalCatalogMethodologyBridgeError(
            "fixture.decision.permission_gate must remain REVIEW"
        )

    if "methodology" in decision:
        raise LocalCatalogMethodologyBridgeError(
            "fixture.decision.methodology already exists"
        )

    return fixture_category, decision


def build_methodology_input(
    fixture: Mapping[str, Any],
    methodology_context: Mapping[str, Any],
) -> MethodologyDecisionInput:
    """Validate exact operator context and map it to the sealed engine input."""

    fixture = _require_mapping(fixture, "fixture")
    fixture_category, _decision = _validate_fixture_contract(fixture)

    context = _require_mapping(
        methodology_context,
        "methodology_context",
    )

    if any(not isinstance(key, str) for key in context):
        raise LocalCatalogMethodologyBridgeError(
            "methodology_context keys must be strings"
        )

    context_keys = set(context)

    missing = [
        field
        for field in _REQUIRED_CONTEXT_FIELDS
        if field not in context_keys
    ]

    if missing:
        raise LocalCatalogMethodologyBridgeError(
            "missing_context_fields=" + ",".join(missing)
        )

    unexpected = sorted(context_keys - _ALLOWED_CONTEXT_FIELDS)

    if unexpected:
        raise LocalCatalogMethodologyBridgeError(
            "unexpected_context_fields=" + ",".join(unexpected)
        )

    product_facts = _require_string_sequence(
        context.get("product_facts"),
        "methodology_context.product_facts",
        allow_empty=False,
    )

    proof_available = _require_string_sequence(
        context.get("proof_available"),
        "methodology_context.proof_available",
        allow_empty=True,
    )

    buyer_state = _require_nonempty_text(
        context.get("buyer_state"),
        "methodology_context.buyer_state",
    )

    claim_risk = _require_nonempty_text(
        context.get("claim_risk"),
        "methodology_context.claim_risk",
    )

    channel = _require_nonempty_text(
        context.get("channel"),
        "methodology_context.channel",
    )

    margin_profile = _require_nonempty_text(
        context.get("margin_profile"),
        "methodology_context.margin_profile",
    )

    context_category = _require_nonempty_text(
        context.get("category"),
        "methodology_context.category",
    )

    if context_category != fixture_category:
        raise LocalCatalogMethodologyBridgeError(
            "methodology_context.category must exactly match "
            "fixture.product.category"
        )

    candidate_output = _require_optional_text(
        context.get("candidate_output", ""),
        "methodology_context.candidate_output",
    )

    normalized_context: dict[str, Any] = {
        "product_facts": product_facts,
        "buyer_state": buyer_state,
        "proof_available": proof_available,
        "claim_risk": claim_risk,
        "channel": channel,
        "margin_profile": margin_profile,
        "candidate_output": candidate_output,
        "category": context_category,
    }

    return decision_input_from_fixture_context(normalized_context)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]

    return value


def _serialize_methodology_decision(decision: Any) -> dict[str, Any]:
    safe_output = str(decision.safe_output)

    if not safe_output.strip():
        raise LocalCatalogMethodologyBridgeError(
            "sealed methodology engine returned empty safe_output"
        )

    return {
        str(key): _json_ready(value)
        for key, value in asdict(decision).items()
    }

def enrich_local_catalog_fixture_with_methodology(
    fixture: Mapping[str, Any],
    methodology_context: Mapping[str, Any],
    *,
    spec_path: str | Path = DEFAULT_SPEC_PATH,
) -> dict[str, Any]:
    """Return a non-mutating fixture copy carrying one sealed engine decision."""

    fixture = _require_mapping(fixture, "fixture")
    decision_input = build_methodology_input(
        fixture,
        methodology_context,
    )

    try:
        loaded = load_methodology_contract(spec_path)
        engine_decision = decide_marketing_methodology(
            loaded.contract,
            decision_input,
        )
    except (
        MethodologyRuleLoaderError,
        MethodologyDecisionEngineError,
    ) as exc:
        raise LocalCatalogMethodologyBridgeError(
            "methodology_engine_failed"
        ) from exc

    enriched = copy.deepcopy(dict(fixture))

    enriched_decision = copy.deepcopy(
        dict(
            _require_mapping(
                enriched.get("decision"),
                "fixture.decision",
            )
        )
    )

    if enriched_decision.get("permission_gate") != "REVIEW":
        raise LocalCatalogMethodologyBridgeError(
            "fixture.decision.permission_gate changed during bridge"
        )

    enriched_decision["methodology"] = (
        _serialize_methodology_decision(engine_decision)
    )

    enriched["decision"] = enriched_decision
    return enriched


__all__ = [
    "LOCAL_CATALOG_SOURCE_KIND",
    "LocalCatalogMethodologyBridgeError",
    "build_methodology_input",
    "enrich_local_catalog_fixture_with_methodology",
]

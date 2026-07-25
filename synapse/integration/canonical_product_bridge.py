"""A8-R113 canonical product identity and custody primitives.

Local-only boundary:
- no network;
- no external writes;
- no publication;
- no spend;
- no fulfillment.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING, Any

from synapse.discovery.synthetic_schema import DiscoveryCandidate


if TYPE_CHECKING:
    from synapse.integration.a8_r70_smoke import (
        SmokeIntegrationResult,
    )


SCHEMA_VERSION = "a8-r113.canonical_product_bridge.v1"
SOURCE_KIND = "operator_approved_discovery_promotion"
APPROVAL_STATUS = "APPROVED_FOR_LOCAL_PROMOTION"
APPROVAL_SCOPE = "LOCAL_PREVIEW_PIPELINE_ONLY"
CUSTODY_SCHEMA_VERSION = "a8-r113.promoted_fixture_custody.v2"


class CanonicalProductBridgeError(ValueError):
    """Raised when canonical product custody must fail closed."""


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in value.items()
        }

    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]

    return value


def canonicalize_discovery_candidate(
    candidate: DiscoveryCandidate,
) -> dict[str, Any]:
    """Return the exact JSON-ready candidate used for custody."""
    if not isinstance(candidate, DiscoveryCandidate):
        raise CanonicalProductBridgeError(
            "candidate must be a DiscoveryCandidate"
        )

    payload = _json_ready(candidate.to_dict())

    candidate_id = payload.get("candidate_id")
    product_id = payload.get("product_id")

    if not isinstance(candidate_id, str) or not candidate_id:
        raise CanonicalProductBridgeError(
            "candidate.candidate_id must be non-empty"
        )

    if product_id != candidate_id:
        raise CanonicalProductBridgeError(
            "candidate product_id must equal candidate_id"
        )

    return payload


def serialize_discovery_candidate(
    candidate: DiscoveryCandidate,
) -> str:
    """Serialize canonical candidate bytes deterministically."""
    return (
        json.dumps(
            canonicalize_discovery_candidate(candidate),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def discovery_candidate_sha256(
    candidate: DiscoveryCandidate,
) -> str:
    """Return SHA-256 for the complete canonical candidate."""
    serialized = serialize_discovery_candidate(candidate)

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


_REQUIRED_APPROVAL_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "scope",
        "operator_id",
        "approval_record_id",
        "candidate_id",
        "candidate_sha256",
        "decision_run_id",
        "financial_decision",
        "final_decision",
        "publication_authorized",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_promotion_approval(
    approval: Mapping[str, Any],
    *,
    candidate: DiscoveryCandidate,
    decision_run_id: str,
    financial_decision: str,
    final_decision: str,
) -> dict[str, Any]:
    """Validate exact operator approval bound to one candidate and decision."""
    if not isinstance(approval, Mapping):
        raise CanonicalProductBridgeError(
            "promotion_approval must be a mapping"
        )

    if any(not isinstance(key, str) for key in approval):
        raise CanonicalProductBridgeError(
            "promotion_approval keys must be strings"
        )

    keys = set(approval)
    missing = sorted(_REQUIRED_APPROVAL_FIELDS - keys)
    unexpected = sorted(keys - _REQUIRED_APPROVAL_FIELDS)

    if missing:
        raise CanonicalProductBridgeError(
            "promotion_approval.missing_fields=" + ",".join(missing)
        )

    if unexpected:
        raise CanonicalProductBridgeError(
            "promotion_approval.unexpected_fields=" + ",".join(unexpected)
        )

    normalized = {
        "schema_version": _require_text(
            approval.get("schema_version"),
            "promotion_approval.schema_version",
        ),
        "status": _require_text(
            approval.get("status"),
            "promotion_approval.status",
        ),
        "scope": _require_text(
            approval.get("scope"),
            "promotion_approval.scope",
        ),
        "operator_id": _require_text(
            approval.get("operator_id"),
            "promotion_approval.operator_id",
        ),
        "approval_record_id": _require_text(
            approval.get("approval_record_id"),
            "promotion_approval.approval_record_id",
        ),
        "candidate_id": _require_text(
            approval.get("candidate_id"),
            "promotion_approval.candidate_id",
        ),
        "candidate_sha256": _require_text(
            approval.get("candidate_sha256"),
            "promotion_approval.candidate_sha256",
        ),
        "decision_run_id": _require_text(
            approval.get("decision_run_id"),
            "promotion_approval.decision_run_id",
        ),
        "financial_decision": _require_text(
            approval.get("financial_decision"),
            "promotion_approval.financial_decision",
        ),
        "final_decision": _require_text(
            approval.get("final_decision"),
            "promotion_approval.final_decision",
        ),
        "publication_authorized": approval.get(
            "publication_authorized"
        ),
        "external_writes_authorized": approval.get(
            "external_writes_authorized"
        ),
        "spend_authorized": approval.get("spend_authorized"),
        "fulfillment_authorized": approval.get(
            "fulfillment_authorized"
        ),
    }

    expected_text = {
        "schema_version": SCHEMA_VERSION,
        "status": APPROVAL_STATUS,
        "scope": APPROVAL_SCOPE,
        "candidate_id": candidate.candidate_id,
        "decision_run_id": decision_run_id,
        "financial_decision": financial_decision,
        "final_decision": final_decision,
    }

    for field, expected in expected_text.items():
        if normalized[field] != expected:
            raise CanonicalProductBridgeError(
                f"promotion_approval.{field} must exactly match"
            )

    for field in (
        "publication_authorized",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
    ):
        if normalized[field] is not False:
            raise CanonicalProductBridgeError(
                f"promotion_approval.{field} must be false"
            )

    supplied_digest = normalized["candidate_sha256"]

    if not _SHA256_RE.fullmatch(supplied_digest):
        raise CanonicalProductBridgeError(
            "promotion_approval.candidate_sha256 must be "
            "64 lowercase hexadecimal characters"
        )

    expected_digest = discovery_candidate_sha256(candidate)

    if not hmac.compare_digest(
        supplied_digest,
        expected_digest,
    ):
        raise CanonicalProductBridgeError(
            "promotion_approval.candidate_sha256 mismatch"
        )

    return normalized


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise CanonicalProductBridgeError(
            f"{path} must be a string"
        )

    text = value.strip()

    if not text:
        raise CanonicalProductBridgeError(
            f"{path} must be non-empty"
        )

    if len(text) > 200:
        raise CanonicalProductBridgeError(
            f"{path} exceeds maximum length 200"
        )

    return text


_ALLOWED_FINAL_DECISIONS = frozenset(
    {
        "READY_FOR_SANDBOX_BRIEF",
        "WATCH_SANDBOX_BRIEF_ONLY",
    }
)

_FINAL_TO_FINANCIAL_DECISION = {
    "READY_FOR_SANDBOX_BRIEF": "PASS",
    "WATCH_SANDBOX_BRIEF_ONLY": "WATCH",
}


def promote_smoke_result_to_local_fixture(
    result: "SmokeIntegrationResult",
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote one approved smoke result into a REVIEW-gated local fixture."""
    from synapse.financial.evaluation import ScenarioName
    from synapse.integration.a8_r70_smoke import (
        SmokeIntegrationResult,
    )

    if not isinstance(result, SmokeIntegrationResult):
        raise CanonicalProductBridgeError(
            "result must be a SmokeIntegrationResult"
        )

    candidate = result.candidate
    candidate_id = candidate.candidate_id

    identity_values = {
        "financial_input.product_id": result.financial_input.product_id,
        "financial_result.product_id": result.financial_result.product_id,
        "decision_record.candidate_id": result.decision_record.candidate_id,
    }

    for path, value in identity_values.items():
        if value != candidate_id:
            raise CanonicalProductBridgeError(
                f"{path} must exactly match candidate_id"
            )

    if result.financial_input.name != candidate.product_name:
        raise CanonicalProductBridgeError(
            "financial_input.name must match candidate product_name"
        )

    if result.financial_result.name != candidate.product_name:
        raise CanonicalProductBridgeError(
            "financial_result.name must match candidate product_name"
        )

    final_decision = result.decision_record.final_decision

    if final_decision.value not in _ALLOWED_FINAL_DECISIONS:
        raise CanonicalProductBridgeError(
            "smoke result is not eligible for local promotion"
        )

    if result.decision_record.brief_built is not True:
        raise CanonicalProductBridgeError(
            "smoke result must contain a built marketing brief"
        )

    if result.marketing_brief is None:
        raise CanonicalProductBridgeError(
            "marketing_brief is required"
        )

    if result.marketing_brief.get("product_id") != candidate_id:
        raise CanonicalProductBridgeError(
            "marketing_brief.product_id must match candidate_id"
        )

    if result.guard_trail.safe_to_continue is not True:
        raise CanonicalProductBridgeError(
            "guard trail must be safe to continue"
        )

    if result.guard_trail.spend_probe.blocked is not True:
        raise CanonicalProductBridgeError(
            "spend probe must remain blocked"
        )

    if result.guard_trail.mutation_probe.blocked is not True:
        raise CanonicalProductBridgeError(
            "mutation probe must remain blocked"
        )

    validated = validate_promotion_approval(
        approval,
        candidate=candidate,
        decision_run_id=result.decision_record.run_id,
        financial_decision=result.financial_result.decision.value,
        final_decision=final_decision.value,
    )

    base = result.financial_result.scenarios[ScenarioName.BASE]

    return {
        "fixture_id": f"a8_r113_{candidate_id}",
        "source_kind": SOURCE_KIND,
        "scenario": "operator_approved_discovery_promotion",
        "canonical_bridge": {
            "schema_version": CUSTODY_SCHEMA_VERSION,
            "source_kind": SOURCE_KIND,
            "candidate_id": candidate_id,
            "candidate_sha256": validated["candidate_sha256"],
            "candidate_snapshot": canonicalize_discovery_candidate(
                candidate
            ),
            "approval_sha256": _canonical_mapping_sha256(validated),
            "approval": {
                "status": validated["status"],
                "scope": validated["scope"],
                "operator_id": validated["operator_id"],
                "approval_record_id": validated[
                    "approval_record_id"
                ],
                "decision_run_id": validated["decision_run_id"],
                "financial_decision": validated[
                    "financial_decision"
                ],
                "final_decision": validated["final_decision"],
                "publication_authorized": False,
                "external_writes_authorized": False,
                "spend_authorized": False,
                "fulfillment_authorized": False,
            },
        },
        "product": {
            "product_id": candidate_id,
            "name": candidate.product_name,
            "category": candidate.category,
            "supplier": candidate.supplier_mode,
            "market": candidate.market,
            "status": "candidate",
        },
        "decision": {
            "outcome": final_decision.value,
            "permission_gate": "REVIEW",
            "reason": (
                "Candidato promovido explícitamente por el operador "
                "para procesamiento local."
            ),
            "reason_codes": list(
                result.decision_record.reason_codes
            ),
            "caveats": [
                "La fuente continúa siendo sintética.",
                "No constituye evidencia de mercado o inventario.",
                "Publicación, gasto y writes permanecen bloqueados.",
            ],
        },
        "operator_input": {},
        "evidence": {
            "notes": [
                (
                    "Candidate SHA-256: "
                    f"{validated['candidate_sha256']}"
                ),
                (
                    "Decision run: "
                    f"{validated['decision_run_id']}"
                ),
                (
                    "Operator approval record: "
                    f"{validated['approval_record_id']}"
                ),
            ],
            "artifacts": [],
        },
        "economics": {
            "currency": "MXN",
            "price_mxn": candidate.price,
            "landed_cost_mxn": candidate.cost,
            "estimated_cac_mxn": format(
                base.estimated_cac,
                ".2f",
            ),
            "contribution_margin_mxn": format(
                base.contribution_margin,
                ".2f",
            ),
            "notes": (
                "Economía sandbox determinista; "
                "no son datos live de mercado."
            ),
        },
    }


_CUSTODY_FIELDS = frozenset(
    {
        "schema_version",
        "source_kind",
        "candidate_id",
        "candidate_sha256",
        "candidate_snapshot",
        "approval_sha256",
        "approval",
    }
)

_CUSTODY_APPROVAL_FIELDS = frozenset(
    {
        "status",
        "scope",
        "operator_id",
        "approval_record_id",
        "decision_run_id",
        "financial_decision",
        "final_decision",
        "publication_authorized",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
    }
)


def _require_decimal_match(
    actual: Any,
    expected: Any,
    *,
    actual_path: str,
    expected_path: str,
) -> None:
    """Require finite decimal equivalence across custody surfaces."""
    try:
        actual_decimal = Decimal(str(actual))
        expected_decimal = Decimal(str(expected))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CanonicalProductBridgeError(
            f"{actual_path} must be a finite decimal"
        ) from exc

    if (
        not actual_decimal.is_finite()
        or not expected_decimal.is_finite()
        or actual_decimal != expected_decimal
    ):
        raise CanonicalProductBridgeError(
            f"{actual_path} must match {expected_path}"
        )

def validate_promoted_fixture_custody(
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify promoted fixture provenance without trusting source_kind alone."""
    fixture_value = _require_mapping(
        fixture,
        "fixture",
    )

    if fixture_value.get("source_kind") != SOURCE_KIND:
        raise CanonicalProductBridgeError(
            f"fixture.source_kind must be {SOURCE_KIND}"
        )

    product = _require_mapping(
        fixture_value.get("product"),
        "fixture.product",
    )
    decision = _require_mapping(
        fixture_value.get("decision"),
        "fixture.decision",
    )
    economics = _require_mapping(
        fixture_value.get("economics"),
        "fixture.economics",
    )
    custody = _require_mapping(
        fixture_value.get("canonical_bridge"),
        "fixture.canonical_bridge",
    )

    _require_exact_keys(
        custody,
        _CUSTODY_FIELDS,
        "fixture.canonical_bridge",
    )

    if custody.get("schema_version") != CUSTODY_SCHEMA_VERSION:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.schema_version mismatch"
        )

    if custody.get("source_kind") != SOURCE_KIND:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.source_kind mismatch"
        )

    candidate_id = _require_text(
        custody.get("candidate_id"),
        "fixture.canonical_bridge.candidate_id",
    )
    product_id = _require_text(
        product.get("product_id"),
        "fixture.product.product_id",
    )

    if candidate_id != product_id:
        raise CanonicalProductBridgeError(
            "fixture canonical product identity mismatch"
        )

    digest = _require_text(
        custody.get("candidate_sha256"),
        "fixture.canonical_bridge.candidate_sha256",
    )

    if not _SHA256_RE.fullmatch(digest):
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.candidate_sha256 must be "
            "64 lowercase hexadecimal characters"
        )

    snapshot = _require_mapping(
        custody.get("candidate_snapshot"),
        "fixture.canonical_bridge.candidate_snapshot",
    )
    expected_digest = _canonical_mapping_sha256(snapshot)

    if not hmac.compare_digest(digest, expected_digest):
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.candidate_sha256 mismatch"
        )

    identity_bindings = {
        "candidate_snapshot.candidate_id": snapshot.get(
            "candidate_id"
        ),
        "candidate_snapshot.product_id": snapshot.get(
            "product_id"
        ),
    }

    for path, value in identity_bindings.items():
        if value != candidate_id:
            raise CanonicalProductBridgeError(
                f"fixture.canonical_bridge.{path} mismatch"
            )

    product_bindings = {
        "name": "product_name",
        "category": "category",
        "market": "market",
        "supplier": "supplier_mode",
    }

    for product_field, snapshot_field in product_bindings.items():
        if product.get(product_field) != snapshot.get(snapshot_field):
            raise CanonicalProductBridgeError(
                "fixture product does not match canonical snapshot: "
                f"{product_field}"
            )

    if economics.get("currency") != "MXN":
        raise CanonicalProductBridgeError(
            "fixture.economics.currency must remain MXN"
        )

    _require_decimal_match(
        economics.get("price_mxn"),
        snapshot.get("price"),
        actual_path="fixture.economics.price_mxn",
        expected_path=(
            "fixture.canonical_bridge."
            "candidate_snapshot.price"
        ),
    )
    _require_decimal_match(
        economics.get("landed_cost_mxn"),
        snapshot.get("cost"),
        actual_path="fixture.economics.landed_cost_mxn",
        expected_path=(
            "fixture.canonical_bridge."
            "candidate_snapshot.cost"
        ),
    )

    approval = _require_mapping(
        custody.get("approval"),
        "fixture.canonical_bridge.approval",
    )

    _require_exact_keys(
        approval,
        _CUSTODY_APPROVAL_FIELDS,
        "fixture.canonical_bridge.approval",
    )

    if approval.get("status") != APPROVAL_STATUS:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval.status mismatch"
        )

    if approval.get("scope") != APPROVAL_SCOPE:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval.scope mismatch"
        )

    for field in (
        "operator_id",
        "approval_record_id",
        "decision_run_id",
        "financial_decision",
        "final_decision",
    ):
        _require_text(
            approval.get(field),
            f"fixture.canonical_bridge.approval.{field}",
        )

    for field in (
        "publication_authorized",
        "external_writes_authorized",
        "spend_authorized",
        "fulfillment_authorized",
    ):
        if approval.get(field) is not False:
            raise CanonicalProductBridgeError(
                "fixture.canonical_bridge.approval."
                f"{field} must be false"
            )

    approval_digest = _require_text(
        custody.get("approval_sha256"),
        "fixture.canonical_bridge.approval_sha256",
    )

    if not _SHA256_RE.fullmatch(approval_digest):
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval_sha256 must be "
            "64 lowercase hexadecimal characters"
        )

    expected_approval_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": approval["status"],
        "scope": approval["scope"],
        "operator_id": approval["operator_id"],
        "approval_record_id": approval["approval_record_id"],
        "candidate_id": candidate_id,
        "candidate_sha256": digest,
        "decision_run_id": approval["decision_run_id"],
        "financial_decision": approval["financial_decision"],
        "final_decision": approval["final_decision"],
        "publication_authorized": False,
        "external_writes_authorized": False,
        "spend_authorized": False,
        "fulfillment_authorized": False,
    }
    expected_approval_digest = _canonical_mapping_sha256(
        expected_approval_payload
    )

    if not hmac.compare_digest(
        approval_digest,
        expected_approval_digest,
    ):
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval_sha256 mismatch"
        )

    final_decision = approval["final_decision"]
    expected_financial_decision = (
        _FINAL_TO_FINANCIAL_DECISION.get(final_decision)
    )

    if expected_financial_decision is None:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval.final_decision "
            "is not eligible for local promotion"
        )

    if approval["financial_decision"] != expected_financial_decision:
        raise CanonicalProductBridgeError(
            "fixture.canonical_bridge.approval.financial_decision "
            "does not match final_decision"
        )

    if decision.get("permission_gate") != "REVIEW":
        raise CanonicalProductBridgeError(
            "fixture.decision.permission_gate must remain REVIEW"
        )

    if decision.get("outcome") != approval.get("final_decision"):
        raise CanonicalProductBridgeError(
            "fixture decision outcome does not match approval"
        )

    return {
        "candidate_id": candidate_id,
        "candidate_sha256": digest,
        "approval_sha256": approval_digest,
        "approval_record_id": approval["approval_record_id"],
    }


def _canonical_mapping_sha256(
    value: Mapping[str, Any],
) -> str:
    serialized = (
        json.dumps(
            _json_ready(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def _require_mapping(
    value: Any,
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalProductBridgeError(
            f"{path} must be a mapping"
        )

    if any(not isinstance(key, str) for key in value):
        raise CanonicalProductBridgeError(
            f"{path} keys must be strings"
        )

    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: frozenset[str],
    path: str,
) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unexpected = sorted(keys - expected)

    if missing:
        raise CanonicalProductBridgeError(
            f"{path}.missing_fields=" + ",".join(missing)
        )

    if unexpected:
        raise CanonicalProductBridgeError(
            f"{path}.unexpected_fields=" + ",".join(unexpected)
        )


__all__ = [
    "APPROVAL_SCOPE",
    "APPROVAL_STATUS",
    "SCHEMA_VERSION",
    "SOURCE_KIND",
    "CUSTODY_SCHEMA_VERSION",
    "CanonicalProductBridgeError",
    "canonicalize_discovery_candidate",
    "discovery_candidate_sha256",
    "promote_smoke_result_to_local_fixture",
    "serialize_discovery_candidate",
    "validate_promoted_fixture_custody",
    "validate_promotion_approval",
]
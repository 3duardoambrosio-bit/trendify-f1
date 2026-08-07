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
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any

from synapse.discovery.synthetic_schema import DiscoveryCandidate
from synapse.financial.evaluation import (
    Decision as FinancialDecision,
    FinancialAssumptions,
    FinancialInput,
    FinancialResult,
    ScenarioName,
    evaluate_financials,
)


if TYPE_CHECKING:
    from synapse.integration.a8_r70_smoke import (
        SmokeIntegrationResult,
    )


SCHEMA_VERSION = "a8-r113.canonical_product_bridge.v1"
SOURCE_KIND = "operator_approved_discovery_promotion"
LOCAL_CATALOG_SOURCE_KIND = "operator_local_catalog_import"
LOCAL_PRODUCT_PROMOTION_SOURCE_KIND = (
    "operator_approved_local_product_promotion"
)
APPROVAL_STATUS = "APPROVED_FOR_LOCAL_PROMOTION"
APPROVAL_SCOPE = "LOCAL_PREVIEW_PIPELINE_ONLY"
CUSTODY_SCHEMA_VERSION = "a8-r113.promoted_fixture_custody.v2"
LOCAL_PRODUCT_FINAL_DECISION = "READY_FOR_REVIEW"


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


_LOCAL_SNAPSHOT_FIELDS = frozenset(
    {
        "candidate_id",
        "product_id",
        "product_name",
        "category",
        "supplier_mode",
        "market",
        "price",
        "cost",
        "estimated_cac",
        "expected_units",
        "local_provenance",
        "catalog_economics",
        "product_status",
        "methodology",
        "reason_codes",
        "operator_input",
        "evidence",
    }
)
_LOCAL_PROVENANCE_FIELDS = frozenset(
    {
        "source_kind",
        "fixture_id",
        "scenario",
        "source_fixture_sha256",
    }
)
_LOCAL_CATALOG_ECONOMICS_FIELDS = frozenset(
    {
        "currency",
        "price_mxn",
        "product_cost_mxn",
        "shipping_cost_mxn",
        "payment_fee_mxn",
    }
)


def canonicalize_local_product_candidate(
    catalog_fixture: Mapping[str, Any],
    financial_input: FinancialInput,
) -> dict[str, Any]:
    """Bind one validated local-catalog fixture to canonical financial input."""
    fixture = _require_mapping(catalog_fixture, "catalog_fixture")

    if fixture.get("source_kind") != LOCAL_CATALOG_SOURCE_KIND:
        raise CanonicalProductBridgeError(
            "catalog_fixture.source_kind must be "
            f"{LOCAL_CATALOG_SOURCE_KIND}"
        )

    fixture_id = _require_text(
        fixture.get("fixture_id"),
        "catalog_fixture.fixture_id",
    )
    scenario = _require_text(
        fixture.get("scenario"),
        "catalog_fixture.scenario",
    )
    product = _require_mapping(
        fixture.get("product"),
        "catalog_fixture.product",
    )
    decision = _require_mapping(
        fixture.get("decision"),
        "catalog_fixture.decision",
    )
    operator_input = _require_mapping(
        fixture.get("operator_input", {}),
        "catalog_fixture.operator_input",
    )
    evidence = _require_mapping(
        fixture.get("evidence", {}),
        "catalog_fixture.evidence",
    )
    economics = _require_mapping(
        fixture.get("economics"),
        "catalog_fixture.economics",
    )

    if decision.get("permission_gate") != "REVIEW":
        raise CanonicalProductBridgeError(
            "catalog_fixture.decision.permission_gate must remain REVIEW"
        )

    product_id = _require_text(
        product.get("product_id"),
        "catalog_fixture.product.product_id",
    )
    product_name = _require_text(
        product.get("name"),
        "catalog_fixture.product.name",
    )
    category = _require_text(
        product.get("category"),
        "catalog_fixture.product.category",
    )
    supplier = _require_text(
        product.get("supplier"),
        "catalog_fixture.product.supplier",
    )
    market = _require_text(
        product.get("market"),
        "catalog_fixture.product.market",
    )

    if market != "MX":
        raise CanonicalProductBridgeError(
            "catalog_fixture.product.market must be MX"
        )
    if economics.get("currency") != "MXN":
        raise CanonicalProductBridgeError(
            "catalog_fixture.economics.currency must be MXN"
        )

    catalog_price = _require_finite_decimal(
        economics.get("price_mxn"),
        "catalog_fixture.economics.price_mxn",
        minimum=Decimal("0.01"),
    )
    product_cost = _require_finite_decimal(
        economics.get("product_cost_mxn"),
        "catalog_fixture.economics.product_cost_mxn",
        minimum=Decimal("0"),
    )
    shipping_cost = _require_finite_decimal(
        economics.get("shipping_cost_mxn"),
        "catalog_fixture.economics.shipping_cost_mxn",
        minimum=Decimal("0"),
    )
    payment_fee = _require_finite_decimal(
        economics.get("payment_fee_mxn"),
        "catalog_fixture.economics.payment_fee_mxn",
        minimum=Decimal("0"),
    )

    if not isinstance(financial_input, FinancialInput):
        raise CanonicalProductBridgeError(
            "financial_input must be a FinancialInput"
        )
    if financial_input.product_id != product_id:
        raise CanonicalProductBridgeError(
            "financial_input.product_id must match catalog product"
        )
    if financial_input.name != product_name:
        raise CanonicalProductBridgeError(
            "financial_input.name must match catalog product"
        )
    if financial_input.expected_units <= 0:
        raise CanonicalProductBridgeError(
            "financial_input.expected_units must be positive"
        )

    _require_decimal_match(
        financial_input.price,
        catalog_price,
        actual_path="financial_input.price",
        expected_path="catalog_fixture.economics.price_mxn",
    )
    _require_decimal_match(
        financial_input.landed_cost,
        product_cost + shipping_cost,
        actual_path="financial_input.landed_cost",
        expected_path=(
            "catalog_fixture.economics.product_cost_mxn + "
            "shipping_cost_mxn"
        ),
    )
    estimated_cac = _require_finite_decimal(
        financial_input.estimated_cac,
        "financial_input.estimated_cac",
        minimum=Decimal("0"),
    )
    price = _require_finite_decimal(
        financial_input.price,
        "financial_input.price",
        minimum=Decimal("0.01"),
    )
    landed_cost = _require_finite_decimal(
        financial_input.landed_cost,
        "financial_input.landed_cost",
        minimum=Decimal("0.01"),
    )
    product_status = _require_text(
        product.get("status", "candidate"),
        "catalog_fixture.product.status",
    )
    methodology: dict[str, Any] | None = None
    if "methodology" in decision:
        methodology = _json_ready(
            _require_mapping(
                decision.get("methodology"),
                "catalog_fixture.decision.methodology",
            )
        )
    try:
        expected_financial_result = evaluate_financials(
            financial_input,
            assumptions=FinancialAssumptions(
                payment_fee_pct=Decimal("0"),
                payment_fixed_fee=payment_fee,
            ),
        )
    except ValueError as exc:
        raise CanonicalProductBridgeError(
            "financial_input cannot be evaluated canonically"
        ) from exc
    reason_codes = sorted(set(expected_financial_result.reason_codes))

    return {
        "candidate_id": product_id,
        "product_id": product_id,
        "product_name": product_name,
        "category": category,
        "supplier_mode": supplier,
        "market": market,
        "price": format(price, ".2f"),
        "cost": format(landed_cost, ".2f"),
        "estimated_cac": format(estimated_cac, ".2f"),
        "expected_units": financial_input.expected_units,
        "local_provenance": {
            "source_kind": LOCAL_CATALOG_SOURCE_KIND,
            "fixture_id": fixture_id,
            "scenario": scenario,
            "source_fixture_sha256": _canonical_mapping_sha256(
                fixture
            ),
        },
        "catalog_economics": {
            "currency": "MXN",
            "price_mxn": format(catalog_price, ".2f"),
            "product_cost_mxn": format(product_cost, ".2f"),
            "shipping_cost_mxn": format(shipping_cost, ".2f"),
            "payment_fee_mxn": format(payment_fee, ".2f"),
        },
        "product_status": product_status,
        "methodology": methodology,
        "reason_codes": reason_codes,
        "operator_input": _json_ready(operator_input),
        "evidence": _json_ready(evidence),
    }


def serialize_local_product_candidate(
    catalog_fixture: Mapping[str, Any],
    financial_input: FinancialInput,
) -> str:
    """Serialize local-product custody input deterministically."""
    return (
        json.dumps(
            canonicalize_local_product_candidate(
                catalog_fixture,
                financial_input,
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def local_product_candidate_sha256(
    catalog_fixture: Mapping[str, Any],
    financial_input: FinancialInput,
) -> str:
    """Return SHA-256 for one canonical local-product candidate."""
    return hashlib.sha256(
        serialize_local_product_candidate(
            catalog_fixture,
            financial_input,
        ).encode("utf-8")
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
    candidate_snapshot = canonicalize_discovery_candidate(candidate)
    return _validate_promotion_approval_values(
        approval,
        candidate_id=str(candidate_snapshot["candidate_id"]),
        candidate_sha256=discovery_candidate_sha256(candidate),
        decision_run_id=decision_run_id,
        financial_decision=financial_decision,
        final_decision=final_decision,
    )


def _validate_promotion_approval_values(
    approval: Mapping[str, Any],
    *,
    candidate_id: str,
    candidate_sha256: str,
    decision_run_id: str,
    financial_decision: str,
    final_decision: str,
) -> dict[str, Any]:
    """Shared exact approval validation for either canonical candidate kind."""
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
        "candidate_id": candidate_id,
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

    if not hmac.compare_digest(
        supplied_digest,
        candidate_sha256,
    ):
        raise CanonicalProductBridgeError(
            "promotion_approval.candidate_sha256 mismatch"
        )

    return normalized


def validate_local_product_promotion_approval(
    approval: Mapping[str, Any],
    *,
    candidate_snapshot: Mapping[str, Any],
    decision_run_id: str,
    financial_decision: str,
    final_decision: str,
) -> dict[str, Any]:
    """Validate approval bound to one canonical local-product snapshot."""
    if financial_decision != FinancialDecision.PASS.value:
        raise CanonicalProductBridgeError(
            "local product financial_decision must be PASS"
        )
    if final_decision != LOCAL_PRODUCT_FINAL_DECISION:
        raise CanonicalProductBridgeError(
            "local product final_decision must be "
            f"{LOCAL_PRODUCT_FINAL_DECISION}"
        )
    snapshot = _require_mapping(
        candidate_snapshot,
        "candidate_snapshot",
    )
    _require_exact_keys(
        snapshot,
        _LOCAL_SNAPSHOT_FIELDS,
        "candidate_snapshot",
    )
    candidate_id = _require_text(
        snapshot.get("candidate_id"),
        "candidate_snapshot.candidate_id",
    )
    if snapshot.get("product_id") != candidate_id:
        raise CanonicalProductBridgeError(
            "candidate_snapshot.product_id must match candidate_id"
        )
    return _validate_promotion_approval_values(
        approval,
        candidate_id=candidate_id,
        candidate_sha256=_canonical_mapping_sha256(snapshot),
        decision_run_id=decision_run_id,
        financial_decision=financial_decision,
        final_decision=final_decision,
    )


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
_LOCAL_FINAL_TO_FINANCIAL_DECISION = {
    LOCAL_PRODUCT_FINAL_DECISION: FinancialDecision.PASS.value,
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


def promote_local_product_to_canonical_fixture(
    catalog_fixture: Mapping[str, Any],
    financial_input: FinancialInput,
    financial_result: FinancialResult,
    decision_record: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote one financially approved local product into canonical custody."""
    snapshot = canonicalize_local_product_candidate(
        catalog_fixture,
        financial_input,
    )
    candidate_id = str(snapshot["candidate_id"])
    product_name = str(snapshot["product_name"])

    if not isinstance(financial_result, FinancialResult):
        raise CanonicalProductBridgeError(
            "financial_result must be a FinancialResult"
        )
    if financial_result.product_id != candidate_id:
        raise CanonicalProductBridgeError(
            "financial_result.product_id must match canonical candidate"
        )
    if financial_result.name != product_name:
        raise CanonicalProductBridgeError(
            "financial_result.name must match canonical candidate"
        )
    snapshot_economics = _require_mapping(
        snapshot.get("catalog_economics"),
        "candidate_snapshot.catalog_economics",
    )
    expected_assumptions = FinancialAssumptions(
        payment_fee_pct=Decimal("0"),
        payment_fixed_fee=_require_finite_decimal(
            snapshot_economics.get("payment_fee_mxn"),
            "candidate_snapshot.catalog_economics.payment_fee_mxn",
            minimum=Decimal("0"),
        ),
    )
    expected_financial_result = evaluate_financials(
        financial_input,
        assumptions=expected_assumptions,
    )
    if financial_result != expected_financial_result:
        raise CanonicalProductBridgeError(
            "financial_result must exactly match canonical evaluation"
        )
    if financial_result.decision is not FinancialDecision.PASS:
        raise CanonicalProductBridgeError(
            "local product financial decision must be PASS"
        )

    decision = _require_mapping(
        decision_record,
        "decision_record",
    )
    if decision.get("product_id") != candidate_id:
        raise CanonicalProductBridgeError(
            "decision_record.product_id must match canonical candidate"
        )
    if decision.get("financial_decision") != FinancialDecision.PASS.value:
        raise CanonicalProductBridgeError(
            "decision_record.financial_decision must be PASS"
        )
    final_decision = decision.get("final_decision")
    if final_decision != LOCAL_PRODUCT_FINAL_DECISION:
        raise CanonicalProductBridgeError(
            "decision_record.final_decision must be "
            f"{LOCAL_PRODUCT_FINAL_DECISION}"
        )

    run_id = _require_text(
        decision.get("run_id"),
        "decision_record.run_id",
    )
    normalized_reason_codes = _require_text_sequence(
        decision.get("reason_codes"),
        "decision_record.reason_codes",
    )
    expected_reason_codes = tuple(
        sorted(set(financial_result.reason_codes))
    )
    if normalized_reason_codes != expected_reason_codes:
        raise CanonicalProductBridgeError(
            "decision_record.reason_codes must match financial_result"
        )
    snapshot_reason_codes = _require_text_sequence(
        snapshot.get("reason_codes"),
        "candidate_snapshot.reason_codes",
    )
    if (
        list(snapshot_reason_codes) != snapshot.get("reason_codes")
        or snapshot_reason_codes != normalized_reason_codes
    ):
        raise CanonicalProductBridgeError(
            "candidate_snapshot.reason_codes must match decision_record"
        )
    if decision.get("promotion_eligible") is not True:
        raise CanonicalProductBridgeError(
            "decision_record.promotion_eligible must be true"
        )
    base = financial_result.scenarios.get(ScenarioName.BASE)
    if base is None:
        raise CanonicalProductBridgeError(
            "financial_result base scenario is required"
        )

    for financial_path, actual, expected in (
        (
            "financial_result.base.price",
            base.price,
            financial_input.price,
        ),
        (
            "financial_result.base.landed_cost",
            base.landed_cost,
            financial_input.landed_cost,
        ),
        (
            "financial_result.base.estimated_cac",
            base.estimated_cac,
            financial_input.estimated_cac,
        ),
    ):
        _require_decimal_match(
            actual,
            expected,
            actual_path=financial_path,
            expected_path=financial_path.replace(
                "financial_result.base",
                "financial_input",
            ),
        )

    validated = validate_local_product_promotion_approval(
        approval,
        candidate_snapshot=snapshot,
        decision_run_id=run_id,
        financial_decision=FinancialDecision.PASS.value,
        final_decision=final_decision,
    )
    source_fixture = _require_mapping(
        catalog_fixture,
        "catalog_fixture",
    )
    snapshot_evidence = _require_mapping(
        snapshot.get("evidence"),
        "candidate_snapshot.evidence",
    )
    snapshot_operator_input = _require_mapping(
        snapshot.get("operator_input"),
        "candidate_snapshot.operator_input",
    )
    catalog_economics = _require_mapping(
        snapshot["catalog_economics"],
        "candidate_snapshot.catalog_economics",
    )

    promoted_decision: dict[str, Any] = {
        "outcome": final_decision,
        "permission_gate": "REVIEW",
        "reason": (
            "Producto local promovido explícitamente por el operador "
            "para vista previa y exportación local."
        ),
        "reason_codes": list(normalized_reason_codes),
        "caveats": [
            "La entrada procede de un archivo local del operador.",
            "No constituye evidencia de mercado, demanda o inventario.",
            "Publicación, gasto y writes permanecen bloqueados.",
        ],
    }
    snapshot_methodology = snapshot.get("methodology")
    if snapshot_methodology is not None:
        promoted_decision["methodology"] = _json_ready(
            _require_mapping(
                snapshot_methodology,
                "candidate_snapshot.methodology",
            )
        )

    return {
        "fixture_id": (
            "canonical_"
            + _require_text(
                source_fixture.get("fixture_id"),
                "catalog_fixture.fixture_id",
            )
        ),
        "source_kind": LOCAL_PRODUCT_PROMOTION_SOURCE_KIND,
        "scenario": "operator_approved_local_product_promotion",
        "canonical_bridge": {
            "schema_version": CUSTODY_SCHEMA_VERSION,
            "source_kind": LOCAL_PRODUCT_PROMOTION_SOURCE_KIND,
            "candidate_id": candidate_id,
            "candidate_sha256": validated["candidate_sha256"],
            "candidate_snapshot": snapshot,
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
            "name": product_name,
            "category": snapshot["category"],
            "supplier": snapshot["supplier_mode"],
            "market": snapshot["market"],
            "status": snapshot["product_status"],
        },
        "decision": promoted_decision,
        "operator_input": _json_ready(snapshot_operator_input),
        "evidence": _json_ready(snapshot_evidence),
        "economics": {
            "currency": "MXN",
            "price_mxn": format(base.price, ".2f"),
            "product_cost_mxn": catalog_economics[
                "product_cost_mxn"
            ],
            "shipping_cost_mxn": catalog_economics[
                "shipping_cost_mxn"
            ],
            "payment_fee_mxn": catalog_economics[
                "payment_fee_mxn"
            ],
            "landed_cost_mxn": format(base.landed_cost, ".2f"),
            "estimated_cac_mxn": format(base.estimated_cac, ".2f"),
            "expected_units": financial_input.expected_units,
            "contribution_margin_mxn": format(
                base.contribution_margin,
                ".2f",
            ),
            "break_even_cac_mxn": format(
                base.break_even_cac,
                ".2f",
            ),
            "financial_decision": FinancialDecision.PASS.value,
            "notes": (
                "Economía Decimal local determinista; no son datos "
                "live de mercado."
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


def _validate_local_product_custody_bindings(
    *,
    fixture: Mapping[str, Any],
    economics: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> None:
    _require_exact_keys(
        snapshot,
        _LOCAL_SNAPSHOT_FIELDS,
        "fixture.canonical_bridge.candidate_snapshot",
    )
    product = _require_mapping(
        fixture.get("product"),
        "fixture.product",
    )
    decision = _require_mapping(
        fixture.get("decision"),
        "fixture.decision",
    )
    operator_input = _require_mapping(
        fixture.get("operator_input"),
        "fixture.operator_input",
    )
    evidence = _require_mapping(
        fixture.get("evidence"),
        "fixture.evidence",
    )
    snapshot_operator_input = _require_mapping(
        snapshot.get("operator_input"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "operator_input"
        ),
    )
    snapshot_evidence = _require_mapping(
        snapshot.get("evidence"),
        "fixture.canonical_bridge.candidate_snapshot.evidence",
    )
    product_status = _require_text(
        snapshot.get("product_status"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "product_status"
        ),
    )
    if product.get("status") != product_status:
        raise CanonicalProductBridgeError(
            "fixture.product.status does not match canonical snapshot"
        )

    snapshot_reason_codes = _require_text_sequence(
        snapshot.get("reason_codes"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "reason_codes"
        ),
    )
    if list(snapshot_reason_codes) != snapshot.get("reason_codes"):
        raise CanonicalProductBridgeError(
            "fixture canonical snapshot reason_codes must be "
            "sorted and unique"
        )
    if decision.get("reason_codes") != list(snapshot_reason_codes):
        raise CanonicalProductBridgeError(
            "fixture.decision.reason_codes does not match "
            "canonical snapshot"
        )

    snapshot_methodology = snapshot.get("methodology")
    if snapshot_methodology is None:
        if "methodology" in decision:
            raise CanonicalProductBridgeError(
                "fixture.decision.methodology does not match "
                "canonical snapshot"
            )
    else:
        canonical_methodology = _require_mapping(
            snapshot_methodology,
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "methodology"
            ),
        )
        promoted_methodology = _require_mapping(
            decision.get("methodology"),
            "fixture.decision.methodology",
        )
        if promoted_methodology != canonical_methodology:
            raise CanonicalProductBridgeError(
                "fixture.decision.methodology does not match "
                "canonical snapshot"
            )

    if operator_input != snapshot_operator_input:
        raise CanonicalProductBridgeError(
            "fixture.operator_input does not match canonical snapshot"
        )
    if evidence != snapshot_evidence:
        raise CanonicalProductBridgeError(
            "fixture.evidence does not match canonical snapshot"
        )

    provenance = _require_mapping(
        snapshot.get("local_provenance"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "local_provenance"
        ),
    )
    _require_exact_keys(
        provenance,
        _LOCAL_PROVENANCE_FIELDS,
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "local_provenance"
        ),
    )
    catalog_economics = _require_mapping(
        snapshot.get("catalog_economics"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics"
        ),
    )
    _require_exact_keys(
        catalog_economics,
        _LOCAL_CATALOG_ECONOMICS_FIELDS,
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics"
        ),
    )

    if provenance.get("source_kind") != LOCAL_CATALOG_SOURCE_KIND:
        raise CanonicalProductBridgeError(
            "fixture canonical local provenance source_kind mismatch"
        )
    source_fixture_digest = _require_text(
        provenance.get("source_fixture_sha256"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "local_provenance.source_fixture_sha256"
        ),
    )
    if not _SHA256_RE.fullmatch(source_fixture_digest):
        raise CanonicalProductBridgeError(
            "fixture canonical local source_fixture_sha256 must be "
            "64 lowercase hexadecimal characters"
        )
    source_fixture_id = _require_text(
        provenance.get("fixture_id"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "local_provenance.fixture_id"
        ),
    )
    _require_text(
        provenance.get("scenario"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "local_provenance.scenario"
        ),
    )
    if fixture.get("fixture_id") != (
        "canonical_" + source_fixture_id
    ):
        raise CanonicalProductBridgeError(
            "fixture.fixture_id does not match local provenance"
        )
    if fixture.get("scenario") != (
        "operator_approved_local_product_promotion"
    ):
        raise CanonicalProductBridgeError(
            "fixture.scenario must remain local product promotion"
        )
    if catalog_economics.get("currency") != "MXN":
        raise CanonicalProductBridgeError(
            "fixture canonical catalog economics currency must be MXN"
        )

    _require_decimal_match(
        snapshot.get("price"),
        catalog_economics.get("price_mxn"),
        actual_path=(
            "fixture.canonical_bridge.candidate_snapshot.price"
        ),
        expected_path=(
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics.price_mxn"
        ),
    )
    catalog_product_cost = _require_finite_decimal(
        catalog_economics.get("product_cost_mxn"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics.product_cost_mxn"
        ),
        minimum=Decimal("0"),
    )
    catalog_shipping_cost = _require_finite_decimal(
        catalog_economics.get("shipping_cost_mxn"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics.shipping_cost_mxn"
        ),
        minimum=Decimal("0"),
    )
    _require_finite_decimal(
        catalog_economics.get("payment_fee_mxn"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics.payment_fee_mxn"
        ),
        minimum=Decimal("0"),
    )
    _require_decimal_match(
        snapshot.get("cost"),
        catalog_product_cost + catalog_shipping_cost,
        actual_path=(
            "fixture.canonical_bridge.candidate_snapshot.cost"
        ),
        expected_path=(
            "fixture.canonical_bridge.candidate_snapshot."
            "catalog_economics product + shipping"
        ),
    )
    _require_finite_decimal(
        snapshot.get("estimated_cac"),
        (
            "fixture.canonical_bridge.candidate_snapshot."
            "estimated_cac"
        ),
        minimum=Decimal("0"),
    )
    expected_units = snapshot.get("expected_units")
    if (
        isinstance(expected_units, bool)
        or not isinstance(expected_units, int)
        or expected_units <= 0
    ):
        raise CanonicalProductBridgeError(
            "fixture canonical expected_units must be a positive integer"
        )

    recompute_input = FinancialInput(
        product_id=_require_text(
            snapshot.get("product_id"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "product_id"
            ),
        ),
        name=_require_text(
            snapshot.get("product_name"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "product_name"
            ),
        ),
        price=_require_finite_decimal(
            snapshot.get("price"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "price"
            ),
            minimum=Decimal("0.01"),
        ),
        landed_cost=_require_finite_decimal(
            snapshot.get("cost"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "cost"
            ),
            minimum=Decimal("0.01"),
        ),
        estimated_cac=_require_finite_decimal(
            snapshot.get("estimated_cac"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "estimated_cac"
            ),
            minimum=Decimal("0"),
        ),
        expected_units=expected_units,
    )
    recompute_assumptions = FinancialAssumptions(
        payment_fee_pct=Decimal("0"),
        payment_fixed_fee=_require_finite_decimal(
            catalog_economics.get("payment_fee_mxn"),
            (
                "fixture.canonical_bridge.candidate_snapshot."
                "catalog_economics.payment_fee_mxn"
            ),
            minimum=Decimal("0"),
        ),
    )
    try:
        recomputed = evaluate_financials(
            recompute_input,
            assumptions=recompute_assumptions,
        )
    except ValueError as exc:
        raise CanonicalProductBridgeError(
            "fixture canonical financial input is invalid"
        ) from exc
    if recomputed.decision is not FinancialDecision.PASS:
        raise CanonicalProductBridgeError(
            "fixture canonical financial decision must remain PASS"
        )
    if snapshot_reason_codes != tuple(
        sorted(set(recomputed.reason_codes))
    ):
        raise CanonicalProductBridgeError(
            "fixture canonical reason_codes must match "
            "canonical financial evaluation"
        )
    recomputed_base = recomputed.scenarios[ScenarioName.BASE]

    for economics_field, snapshot_value, snapshot_path in (
        (
            "product_cost_mxn",
            catalog_economics.get("product_cost_mxn"),
            "candidate_snapshot.catalog_economics.product_cost_mxn",
        ),
        (
            "shipping_cost_mxn",
            catalog_economics.get("shipping_cost_mxn"),
            "candidate_snapshot.catalog_economics.shipping_cost_mxn",
        ),
        (
            "payment_fee_mxn",
            catalog_economics.get("payment_fee_mxn"),
            "candidate_snapshot.catalog_economics.payment_fee_mxn",
        ),
        (
            "estimated_cac_mxn",
            snapshot.get("estimated_cac"),
            "candidate_snapshot.estimated_cac",
        ),
    ):
        _require_decimal_match(
            economics.get(economics_field),
            snapshot_value,
            actual_path=f"fixture.economics.{economics_field}",
            expected_path=(
                "fixture.canonical_bridge." + snapshot_path
            ),
        )

    for economics_field, expected_value in (
        (
            "contribution_margin_mxn",
            recomputed_base.contribution_margin,
        ),
        (
            "break_even_cac_mxn",
            recomputed_base.break_even_cac,
        ),
    ):
        _require_decimal_match(
            economics.get(economics_field),
            expected_value,
            actual_path=f"fixture.economics.{economics_field}",
            expected_path=(
                "canonical Decimal financial evaluation"
            ),
        )

    if economics.get("expected_units") != expected_units:
        raise CanonicalProductBridgeError(
            "fixture.economics.expected_units must match "
            "canonical snapshot"
        )
    if economics.get("financial_decision") != FinancialDecision.PASS.value:
        raise CanonicalProductBridgeError(
            "fixture.economics.financial_decision must remain PASS"
        )


def validate_promoted_fixture_custody(
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify promoted fixture provenance without trusting source_kind alone."""
    fixture_value = _require_mapping(
        fixture,
        "fixture",
    )

    source_kind = fixture_value.get("source_kind")
    allowed_source_kinds = {
        SOURCE_KIND,
        LOCAL_PRODUCT_PROMOTION_SOURCE_KIND,
    }
    if source_kind not in allowed_source_kinds:
        raise CanonicalProductBridgeError(
            "fixture.source_kind must be one of:"
            + ",".join(sorted(allowed_source_kinds))
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

    if custody.get("source_kind") != source_kind:
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

    if source_kind == LOCAL_PRODUCT_PROMOTION_SOURCE_KIND:
        _validate_local_product_custody_bindings(
            fixture=fixture_value,
            economics=economics,
            snapshot=snapshot,
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
    decision_map = (
        _LOCAL_FINAL_TO_FINANCIAL_DECISION
        if source_kind == LOCAL_PRODUCT_PROMOTION_SOURCE_KIND
        else _FINAL_TO_FINANCIAL_DECISION
    )
    expected_financial_decision = decision_map.get(final_decision)

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
        "source_kind": source_kind,
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


def _require_finite_decimal(
    value: Any,
    path: str,
    *,
    minimum: Decimal,
) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise CanonicalProductBridgeError(
            f"{path} must be a finite decimal"
        )
    try:
        parsed = (
            value
            if isinstance(value, Decimal)
            else Decimal(str(value).strip())
        )
    except (InvalidOperation, TypeError, ValueError):
        raise CanonicalProductBridgeError(
            f"{path} must be a finite decimal"
        ) from None
    if not parsed.is_finite() or parsed < minimum:
        raise CanonicalProductBridgeError(
            f"{path} must be a finite decimal >= {minimum}"
        )
    return parsed


def _require_text_sequence(
    value: Any,
    path: str,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CanonicalProductBridgeError(
            f"{path} must be a sequence of strings"
        )
    normalized = [
        _require_text(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]
    return tuple(sorted(set(normalized)))


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
    "CUSTODY_SCHEMA_VERSION",
    "LOCAL_CATALOG_SOURCE_KIND",
    "LOCAL_PRODUCT_FINAL_DECISION",
    "LOCAL_PRODUCT_PROMOTION_SOURCE_KIND",
    "SCHEMA_VERSION",
    "SOURCE_KIND",
    "CanonicalProductBridgeError",
    "canonicalize_discovery_candidate",
    "canonicalize_local_product_candidate",
    "discovery_candidate_sha256",
    "local_product_candidate_sha256",
    "promote_local_product_to_canonical_fixture",
    "promote_smoke_result_to_local_fixture",
    "serialize_discovery_candidate",
    "serialize_local_product_candidate",
    "validate_local_product_promotion_approval",
    "validate_promoted_fixture_custody",
    "validate_promotion_approval",
]

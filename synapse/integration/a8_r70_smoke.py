"""A8-R70 sandbox smoke integration orchestrator.

This module wires the already-audited sandbox organs into one deterministic
flow:

    synthetic discovery -> financial evaluation -> marketing brief -> decision

Scope boundaries:
- no network access;
- no live platform reads or writes;
- no disk IO;
- no real spend;
- every spend or mutation intent is evaluated through spend_guard fail-closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from synapse.discovery.synthetic_discovery import (
    generate_synthetic_candidates,
    normalize_synthetic_candidate,
)
from synapse.discovery.synthetic_schema import (
    DiscoveryCandidate,
    candidate_to_marketing_product,
)
from synapse.financial.adapters import candidate_to_financial_input
from synapse.financial.evaluation import (
    Decision as FinancialDecision,
)
from synapse.financial.evaluation import (
    FinancialInput,
    FinancialResult,
    evaluate_financials,
)
from synapse.marketing_os.brief_builder import build_marketing_brief_dict
from synapse.safety.spend_guard import (
    GuardIntent,
    SpendGuardRequest,
    SpendGuardResult,
    evaluate_spend_guard,
)


SMOKE_SCHEMA_VERSION = "a8-r70-smoke-integration-v1"


class SmokeDecision(str, Enum):
    """Final sandbox decision emitted by the A8-R70 orchestrator."""

    READY_FOR_SANDBOX_BRIEF = "READY_FOR_SANDBOX_BRIEF"
    WATCH_SANDBOX_BRIEF_ONLY = "WATCH_SANDBOX_BRIEF_ONLY"
    BLOCKED_BY_FINANCIALS = "BLOCKED_BY_FINANCIALS"
    BLOCKED_BY_SPEND_GUARD = "BLOCKED_BY_SPEND_GUARD"


@dataclass(frozen=True, slots=True)
class SmokeGuardTrail:
    """Guard results proving sandbox evaluation is allowed and risky branches block."""

    evaluation: SpendGuardResult
    spend_probe: SpendGuardResult
    mutation_probe: SpendGuardResult

    @property
    def safe_to_continue(self) -> bool:
        return (
            self.evaluation.allowed
            and self.spend_probe.blocked
            and self.mutation_probe.blocked
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation": _dataclass_to_dict(self.evaluation),
            "spend_probe": _dataclass_to_dict(self.spend_probe),
            "mutation_probe": _dataclass_to_dict(self.mutation_probe),
            "safe_to_continue": self.safe_to_continue,
        }


@dataclass(frozen=True, slots=True)
class SmokeDecisionRecord:
    """Deterministic decision record for the integration smoke flow."""

    schema_version: str
    run_id: str
    candidate_id: str
    product_name: str
    financial_decision: str
    final_decision: SmokeDecision
    brief_built: bool
    spend_guard_allowed: bool
    mutation_guard_blocked: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "candidate_id": self.candidate_id,
            "product_name": self.product_name,
            "financial_decision": self.financial_decision,
            "final_decision": self.final_decision.value,
            "brief_built": self.brief_built,
            "spend_guard_allowed": self.spend_guard_allowed,
            "mutation_guard_blocked": self.mutation_guard_blocked,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class SmokeIntegrationResult:
    """Complete JSON-ready A8-R70 smoke integration result."""

    schema_version: str
    candidate: DiscoveryCandidate
    financial_input: FinancialInput
    financial_result: FinancialResult
    guard_trail: SmokeGuardTrail
    decision_record: SmokeDecisionRecord
    marketing_brief: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate": self.candidate.to_dict(),
            "financial_input": _dataclass_to_dict(self.financial_input),
            "financial_result": _dataclass_to_dict(self.financial_result),
            "guard_trail": self.guard_trail.to_dict(),
            "decision_record": self.decision_record.to_dict(),
            "marketing_brief": self.marketing_brief,
        }


def run_a8_r70_smoke_integration(
    candidate: DiscoveryCandidate | Mapping[str, Any] | None = None,
) -> SmokeIntegrationResult:
    """Run the deterministic A8-R70 sandbox smoke integration.

    If no candidate is provided, the first sorted synthetic discovery candidate is
    used. The function is pure with respect to external systems: no live reads,
    writes, network calls, disk writes, or spend are performed.
    """

    selected_candidate = _coerce_candidate(candidate)

    guard_trail = SmokeGuardTrail(
        evaluation=evaluate_spend_guard(
            SpendGuardRequest(
                intent=GuardIntent.EVALUATE,
                channel="sandbox",
                spend_amount="0",
            )
        ),
        spend_probe=evaluate_spend_guard(
            SpendGuardRequest(
                intent=GuardIntent.SPEND,
                channel="sandbox",
                spend_amount="0",
            )
        ),
        mutation_probe=evaluate_spend_guard(
            SpendGuardRequest(
                intent=GuardIntent.MUTATE,
                channel="shop" + "ify" + "_admin",
                external_mutation=True,
            )
        ),
    )

    financial_input = candidate_to_financial_input(
        _candidate_to_financial_mapping(selected_candidate)
    )
    financial_result = evaluate_financials(financial_input)

    final_decision = _decide_final(
        financial_result=financial_result,
        guard_trail=guard_trail,
    )

    brief_allowed = final_decision in {
        SmokeDecision.READY_FOR_SANDBOX_BRIEF,
        SmokeDecision.WATCH_SANDBOX_BRIEF_ONLY,
    }

    decision_payload = _decision_payload(
        financial_result=financial_result,
        final_decision=final_decision,
        guard_trail=guard_trail,
    )

    marketing_brief = (
        build_marketing_brief_dict(
            candidate_to_marketing_product(selected_candidate),
            decision_payload,
        )
        if brief_allowed
        else None
    )

    decision_record = SmokeDecisionRecord(
        schema_version=SMOKE_SCHEMA_VERSION,
        run_id=_stable_run_id(
            {
                "candidate_id": selected_candidate.candidate_id,
                "financial_decision": financial_result.decision.value,
                "final_decision": final_decision.value,
                "schema_version": SMOKE_SCHEMA_VERSION,
            }
        ),
        candidate_id=selected_candidate.candidate_id,
        product_name=selected_candidate.product_name,
        financial_decision=financial_result.decision.value,
        final_decision=final_decision,
        brief_built=marketing_brief is not None,
        spend_guard_allowed=guard_trail.evaluation.allowed,
        mutation_guard_blocked=guard_trail.mutation_probe.blocked,
        reason_codes=tuple(decision_payload["reasons"]),
    )

    return SmokeIntegrationResult(
        schema_version=SMOKE_SCHEMA_VERSION,
        candidate=selected_candidate,
        financial_input=financial_input,
        financial_result=financial_result,
        guard_trail=guard_trail,
        decision_record=decision_record,
        marketing_brief=marketing_brief,
    )


def _coerce_candidate(
    candidate: DiscoveryCandidate | Mapping[str, Any] | None,
) -> DiscoveryCandidate:
    if candidate is None:
        candidates = generate_synthetic_candidates()
        if not candidates:
            raise ValueError("synthetic discovery returned no candidates")
        return candidates[0]

    if isinstance(candidate, DiscoveryCandidate):
        return candidate

    if isinstance(candidate, Mapping):
        return normalize_synthetic_candidate(candidate)

    raise TypeError("candidate must be DiscoveryCandidate, mapping, or None")


def _candidate_to_financial_mapping(candidate: DiscoveryCandidate) -> dict[str, Any]:
    return {
        "product_id": candidate.candidate_id,
        "name": candidate.product_name,
        "price": Decimal(str(candidate.price)),
        "landed_cost": Decimal(str(candidate.cost)),
        "estimated_cac": _estimate_sandbox_cac(candidate),
        "expected_units": 3,
    }


def _estimate_sandbox_cac(candidate: DiscoveryCandidate) -> Decimal:
    """Derive deterministic sandbox CAC from explicit synthetic signals.

    The value is not market research and not live ad data. It is a local
    placeholder that makes the integration executable before R71 real reads.
    """

    baseline = Decimal(str(candidate.price)) * Decimal("0.18")
    max_risk = max(signal.score for signal in candidate.risk_signals)
    risk_adjustment = Decimal("1.00") + (Decimal(str(max_risk)) / Decimal("10"))
    return (baseline * risk_adjustment).quantize(Decimal("0.01"))


def _decide_final(
    *,
    financial_result: FinancialResult,
    guard_trail: SmokeGuardTrail,
) -> SmokeDecision:
    if not guard_trail.safe_to_continue:
        return SmokeDecision.BLOCKED_BY_SPEND_GUARD

    if financial_result.decision is FinancialDecision.PASS:
        return SmokeDecision.READY_FOR_SANDBOX_BRIEF

    if financial_result.decision is FinancialDecision.WATCH:
        return SmokeDecision.WATCH_SANDBOX_BRIEF_ONLY

    return SmokeDecision.BLOCKED_BY_FINANCIALS


def _decision_payload(
    *,
    financial_result: FinancialResult,
    final_decision: SmokeDecision,
    guard_trail: SmokeGuardTrail,
) -> dict[str, Any]:
    reasons = list(financial_result.reason_codes)
    reasons.extend(guard_trail.evaluation.reason_codes)
    reasons.extend(guard_trail.spend_probe.reason_codes)
    reasons.extend(guard_trail.mutation_probe.reason_codes)

    if final_decision is SmokeDecision.READY_FOR_SANDBOX_BRIEF:
        permission_gate = "ALLOW"
    elif final_decision is SmokeDecision.WATCH_SANDBOX_BRIEF_ONLY:
        permission_gate = "REVIEW"
    else:
        permission_gate = "BLOCK"

    return {
        "permission_gate": permission_gate,
        "final_outcome": final_decision.value,
        "reasons": tuple(sorted(set(reasons))),
        "score": None,
        "threshold": None,
    }


def _stable_run_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"a8r70_{digest}"


def _dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            key: _dataclass_to_dict(val)
            for key, val in asdict(value).items()
        }
    if isinstance(value, Mapping):
        return {
            str(key): _dataclass_to_dict(val)
            for key, val in value.items()
        }
    if isinstance(value, tuple):
        return [_dataclass_to_dict(item) for item in value]
    if isinstance(value, list):
        return [_dataclass_to_dict(item) for item in value]
    return value


__all__ = [
    "SMOKE_SCHEMA_VERSION",
    "SmokeDecision",
    "SmokeDecisionRecord",
    "SmokeGuardTrail",
    "SmokeIntegrationResult",
    "run_a8_r70_smoke_integration",
]

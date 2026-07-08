"""Local evidence reader for A8-R79A feedback foundation.

Reads source artifacts from disk and produces deterministic snapshots. It never
mutates source artifacts; derived outputs must be written to a caller-provided
output path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from synapse.learning.feedback_signal import derive_feedback_signal
from synapse.learning.outcome_schema import (
    FeedbackSignal,
    OutcomeSnapshot,
    OutcomeStatus,
    PredictionSnapshot,
    decimal_from,
)

_ZERO = Decimal("0")


@dataclass(frozen=True)
class EvidenceReadResult:
    prediction: PredictionSnapshot | None
    outcome: OutcomeSnapshot | None
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object at {path}")
    return data


def _first_existing(run_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = run_dir / name
        if candidate.exists():
            return candidate
    return None


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == _ZERO:
        raise ValueError("denominator must not be zero")
    return numerator / denominator


def _confidence_from_score(value: Any) -> Decimal:
    score = decimal_from(value if value is not None else "0", "score")
    if score > Decimal("1"):
        return score / Decimal("100")
    return score


def read_run_evidence(run_dir: str | Path) -> EvidenceReadResult:
    """Read scenario/decision/outcome artifacts from one local run dir."""

    root = Path(run_dir)
    refs: list[str] = []
    reasons: list[str] = []

    scenario_path = _first_existing(root, ("scenario.json",))
    decision_path = _first_existing(root, ("decision.json",))
    outcome_path = _first_existing(root, ("outcome.json", "learning_outcome.json", "observed_outcome.json"))

    prediction: PredictionSnapshot | None = None
    outcome: OutcomeSnapshot | None = None

    if scenario_path is None:
        reasons.append("MISSING_SCENARIO_JSON")
    if decision_path is None:
        reasons.append("MISSING_DECISION_JSON")

    if scenario_path is not None:
        refs.append(str(scenario_path))
    if decision_path is not None:
        refs.append(str(decision_path))

    if scenario_path is not None and decision_path is not None:
        try:
            scenario = _read_json(scenario_path)
            decision = _read_json(decision_path)

            price = decimal_from(scenario.get("proposed_price_mxn"), "proposed_price_mxn")
            cost = decimal_from(scenario.get("estimated_landed_cost_mxn"), "estimated_landed_cost_mxn")
            margin = price - cost
            roi = _ratio(margin, cost)

            decision_id = str(decision.get("decision_id") or decision.get("id") or scenario.get("scenario_id")).strip()
            candidate_id = str(scenario.get("scenario_id") or scenario.get("product_name") or decision_id).strip()
            risk_level = str(decision.get("final_outcome") or decision.get("permission_gate") or "UNKNOWN").strip()
            confidence = _confidence_from_score(decision.get("score"))
            created_at = str(decision.get("generated_at") or scenario.get("created_at") or "UNKNOWN").strip()

            prediction = PredictionSnapshot(
                candidate_id=candidate_id,
                decision_id=decision_id,
                expected_margin=margin,
                expected_roi=roi,
                risk_level=risk_level,
                confidence=confidence,
                created_at=created_at,
            )
        except Exception as exc:
            prediction = None
            reasons.append(f"INVALID_PREDICTION_INPUT:{type(exc).__name__}")

    if outcome_path is None:
        reasons.append("MISSING_OUTCOME_JSON")
    else:
        refs.append(str(outcome_path))
        try:
            raw = _read_json(outcome_path)
            decision_id = str(raw.get("decision_id") or (prediction.decision_id if prediction else "UNKNOWN")).strip()
            revenue = raw.get("observed_revenue", raw.get("revenue"))
            cost = raw.get("observed_cost", raw.get("cost"))
            observed_revenue = decimal_from(revenue, "observed_revenue") if revenue is not None else None
            observed_cost = decimal_from(cost, "observed_cost") if cost is not None else None

            if raw.get("observed_margin") is not None:
                observed_margin = decimal_from(raw.get("observed_margin"), "observed_margin")
            elif observed_revenue is not None and observed_cost is not None:
                observed_margin = observed_revenue - observed_cost
            else:
                observed_margin = None

            if raw.get("observed_roi") is not None:
                observed_roi = decimal_from(raw.get("observed_roi"), "observed_roi")
            elif observed_margin is not None and observed_cost is not None:
                observed_roi = _ratio(observed_margin, observed_cost)
            else:
                observed_roi = None

            status = raw.get("status") or ("OBSERVED" if observed_margin is not None and observed_roi is not None else "PARTIAL")
            outcome = OutcomeSnapshot(
                decision_id=decision_id,
                observed_revenue=observed_revenue,
                observed_cost=observed_cost,
                observed_margin=observed_margin,
                observed_roi=observed_roi,
                source=str(outcome_path),
                observed_at=str(raw.get("observed_at") or raw.get("generated_at") or "UNKNOWN"),
                status=OutcomeStatus(str(status).upper()),
                reason_codes=tuple(raw.get("reason_codes") or ()),
            )
        except Exception as exc:
            outcome = OutcomeSnapshot(
                decision_id=prediction.decision_id if prediction else "UNKNOWN",
                observed_revenue=None,
                observed_cost=None,
                observed_margin=None,
                observed_roi=None,
                source=str(outcome_path),
                observed_at="UNKNOWN",
                status=OutcomeStatus.INVALID,
                reason_codes=(f"INVALID_OUTCOME_INPUT:{type(exc).__name__}",),
            )

    return EvidenceReadResult(
        prediction=prediction,
        outcome=outcome,
        evidence_refs=tuple(refs),
        reason_codes=tuple(reasons),
    )


def build_feedback_signal_for_run_dir(run_dir: str | Path, generated_at: str) -> FeedbackSignal:
    result = read_run_evidence(run_dir)
    signal = derive_feedback_signal(
        prediction=result.prediction,
        outcome=result.outcome,
        evidence_refs=result.evidence_refs,
        generated_at=generated_at,
    )

    if result.reason_codes and signal.signal_status.value == "UNKNOWN":
        return FeedbackSignal(
            decision_id=signal.decision_id,
            signal_status=signal.signal_status,
            margin_delta=signal.margin_delta,
            roi_delta=signal.roi_delta,
            confidence_delta=signal.confidence_delta,
            recommendation=signal.recommendation,
            evidence_refs=signal.evidence_refs,
            generated_at=signal.generated_at,
            reason_codes=tuple(dict.fromkeys((*signal.reason_codes, *result.reason_codes))),
        )

    return signal


def write_feedback_signal(signal: FeedbackSignal, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = signal.to_dict()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
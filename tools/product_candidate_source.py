"""SYNAPSE Product Candidate Source Contract.

This module validates and normalizes local product candidate source payloads.

Design rule:
    Source ingestion creates candidates.
    Product decision engine selects champion.
    Source data must not declare or force a champion.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


SOURCE_CONTRACT_VERSION = "A8-R33.product-candidate-source.v1"

REQUIRED_CANDIDATE_FIELDS = (
    "sku",
    "name",
    "niche",
    "landed_cost",
    "sell_price",
    "shipping_days",
    "supplier_score",
    "demand_score",
    "saturation_score",
    "content_fit_score",
    "problem_severity_score",
    "compliance_risk_score",
    "return_risk_score",
)

NUMERIC_FIELDS = (
    "landed_cost",
    "sell_price",
    "shipping_days",
    "supplier_score",
    "demand_score",
    "saturation_score",
    "content_fit_score",
    "problem_severity_score",
    "compliance_risk_score",
    "return_risk_score",
)

SCORE_FIELDS = (
    "supplier_score",
    "demand_score",
    "saturation_score",
    "content_fit_score",
    "problem_severity_score",
    "compliance_risk_score",
    "return_risk_score",
)

FORBIDDEN_TOP_LEVEL_KEYS = (
    "champion",
    "selected_product",
    "selected_sku",
    "forced_winner",
)

FORBIDDEN_ROW_KEYS = (
    "champion",
    "is_champion",
    "selected",
    "force_select",
    "forced_winner",
)


def normalize_candidate_source(
    payload: Any,
    *,
    source_id: str = "local_candidate_source",
) -> dict[str, Any]:
    """Normalize local candidate source data into an auditable candidate packet."""

    clean_source_id = _require_non_empty_string_value(source_id, "source_id")
    raw_rows = _extract_rows(payload)
    source_sha256 = _sha256_json(_canonical_source_for_hash(payload))

    valid_candidates: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    seen_skus: set[str] = set()

    for index, row in enumerate(raw_rows):
        row_number = index + 1

        try:
            candidate = _normalize_row(row)
            sku = candidate["sku"]

            if sku in seen_skus:
                raise ValueError("duplicate_sku")

            seen_skus.add(sku)
            valid_candidates.append(candidate)
        except Exception as exc:
            rejected_rows.append(
                {
                    "row_number": row_number,
                    "reason": str(exc),
                    "raw_row": row if isinstance(row, dict) else {"value": row},
                }
            )

    quality_report = {
        "input_rows": len(raw_rows),
        "valid_candidates": len(valid_candidates),
        "rejected_rows": len(rejected_rows),
        "duplicate_skus_blocked": _count_rejections(rejected_rows, "duplicate_sku"),
        "manual_selection_markers_blocked": _count_manual_selection_rejections(rejected_rows),
        "valid_ratio": _ratio(len(valid_candidates), len(raw_rows)),
    }

    return {
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_id": clean_source_id,
        "source_sha256": source_sha256,
        "manual_champion_provided": False,
        "selection_mode": "source_normalization_only",
        "candidates": valid_candidates,
        "rejected_rows": rejected_rows,
        "source_quality_report": quality_report,
        "quality_gates": {
            "has_valid_candidates": len(valid_candidates) > 0,
            "all_skus_unique": len(valid_candidates) == len({item["sku"] for item in valid_candidates}),
            "manual_champion_blocked": True,
            "source_hash_present": bool(source_sha256),
            "ready_for_product_decision_cli": len(valid_candidates) > 0,
        },
    }


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for forbidden in FORBIDDEN_TOP_LEVEL_KEYS:
            if forbidden in payload:
                raise ValueError(f"manual_selection_key_forbidden:{forbidden}")

        if "candidates" in payload:
            rows = payload["candidates"]
        elif "rows" in payload:
            rows = payload["rows"]
        else:
            raise ValueError("source payload must contain candidates or rows")
    else:
        raise ValueError("source payload must be object or list")

    if not isinstance(rows, list):
        raise ValueError("source rows must be a list")

    if not rows:
        raise ValueError("source rows must not be empty")

    return rows

def _normalize_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("row_must_be_object")

    for forbidden in FORBIDDEN_ROW_KEYS:
        if forbidden in row:
            raise ValueError(f"manual_selection_key_forbidden:{forbidden}")

    missing = [field for field in REQUIRED_CANDIDATE_FIELDS if field not in row]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    normalized = {
        "sku": _require_non_empty_string(row, "sku"),
        "name": _require_non_empty_string(row, "name"),
        "niche": _require_non_empty_string(row, "niche"),
    }

    for field in NUMERIC_FIELDS:
        normalized[field] = _require_number(row, field)

    if normalized["landed_cost"] <= 0:
        raise ValueError("landed_cost_must_be_positive")

    if normalized["sell_price"] <= 0:
        raise ValueError("sell_price_must_be_positive")

    if normalized["sell_price"] <= normalized["landed_cost"]:
        raise ValueError("sell_price_must_exceed_landed_cost")

    if normalized["shipping_days"] < 0:
        raise ValueError("shipping_days_must_be_non_negative")

    for field in SCORE_FIELDS:
        value = normalized[field]
        if value < 0 or value > 100:
            raise ValueError(f"{field}_must_be_between_0_and_100")

    return normalized


def _require_non_empty_string(row: Mapping[str, Any], key: str) -> str:
    return _require_non_empty_string_value(row[key], key)


def _require_non_empty_string_value(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key}_must_be_string")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{key}_must_not_be_empty")

    return cleaned


def _require_number(row: Mapping[str, Any], key: str) -> float:
    value = row[key]

    if isinstance(value, bool):
        raise ValueError(f"{key}_must_be_number")

    if not isinstance(value, (int, float)):
        raise ValueError(f"{key}_must_be_number")

    return float(value)


def _canonical_source_for_hash(payload: Any) -> Any:
    return payload


def _sha256_json(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _count_rejections(rejected_rows: list[dict[str, Any]], reason: str) -> int:
    return sum(1 for item in rejected_rows if item["reason"] == reason)


def _count_manual_selection_rejections(rejected_rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in rejected_rows
        if item["reason"].startswith("manual_selection_key_forbidden:")
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)

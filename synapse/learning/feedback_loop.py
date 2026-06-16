"""Local feedback-loop evidence materialization for SYNAPSE.

A8-R79B connects the existing in-memory A8-R70 smoke result to local,
read-only evidence that can be consumed by the learning substrate and UI.

This module does not call external services, does not spend money, and does not
mutate source evidence. It only writes derived local artifacts under an explicit
run directory supplied by the caller.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path
from typing import Any, Mapping

from synapse.learning.evidence_reader import (
    build_feedback_signal_for_run_dir,
    write_feedback_signal,
)


FEEDBACK_SIGNAL_FILE = "feedback_signal.json"
OUTCOME_PLACEHOLDER_FILE = "outcome.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return dict(data) if isinstance(data, Mapping) else {}
    if dataclasses.is_dataclass(value):
        data = dataclasses.asdict(value)
        return dict(data) if isinstance(data, Mapping) else {}
    return {}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(encoded + "\n", encoding="utf-8")


def _dump_ndjson(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded_rows = [
        json.dumps(_jsonable(row), ensure_ascii=False, sort_keys=True)
        for row in rows
    ]
    path.write_text("\n".join(encoded_rows) + "\n", encoding="utf-8")


def _first(mapping: Mapping[str, Any], *keys: str, fallback: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return fallback


def _string_decimal(value: Any, fallback: str = "0") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _call_build_feedback_signal(run_dir: Path, generated_at: str) -> Any:
    signature = inspect.signature(build_feedback_signal_for_run_dir)
    if "generated_at" in signature.parameters:
        return build_feedback_signal_for_run_dir(run_dir, generated_at=generated_at)
    return build_feedback_signal_for_run_dir(run_dir)


def _call_write_feedback_signal(signal: Any, output_path: Path) -> None:
    signature = inspect.signature(write_feedback_signal)
    params = list(signature.parameters)

    if not params:
        raise TypeError("write_feedback_signal has no parameters")

    first = params[0].lower()
    if "path" in first or "output" in first:
        write_feedback_signal(output_path, signal)
        return

    try:
        write_feedback_signal(signal, output_path)
    except TypeError:
        write_feedback_signal(output_path, signal)


def _signal_to_mapping(signal: Any) -> dict[str, Any]:
    if isinstance(signal, Mapping):
        return dict(signal)
    if hasattr(signal, "to_dict"):
        data = signal.to_dict()
        return dict(data) if isinstance(data, Mapping) else {}
    if dataclasses.is_dataclass(signal):
        data = dataclasses.asdict(signal)
        return dict(data) if isinstance(data, Mapping) else {}
    return {}


def _normalize_local_path_refs(value: Any, base_dir: Path) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_local_path_refs(item, base_dir)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_local_path_refs(item, base_dir) for item in value]
    if isinstance(value, tuple):
        return [_normalize_local_path_refs(item, base_dir) for item in value]
    if isinstance(value, str):
        try:
            candidate = Path(value)
        except (OSError, ValueError):
            return value
        if not candidate.is_absolute():
            return value
        try:
            relative = candidate.resolve().relative_to(base_dir.resolve())
        except (OSError, ValueError):
            return value
        return relative.as_posix()
    return value


def _normalize_feedback_signal_file(path: Path, base_dir: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_local_path_refs(payload, base_dir)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized



def _first_nested_value(payload: object, keys: tuple[str, ...]) -> Any:
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return value

        for value in payload.values():
            found = _first_nested_value(value, keys)
            if found is not None and found != "":
                return found

    if isinstance(payload, (list, tuple)):
        for item in payload:
            found = _first_nested_value(item, keys)
            if found is not None and found != "":
                return found

    return None


def _with_reader_compatible_prediction_fields(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Add flat prediction fields expected by evidence_reader without mutating input."""

    scenario = dict(payload)

    if scenario.get("proposed_price_mxn") is None:
        proposed_price = _first_nested_value(
            scenario,
            (
                "proposed_price_mxn",
                "price_mxn",
                "selling_price_mxn",
                "sale_price_mxn",
                "proposed_price",
                "price",
            ),
        )
        if proposed_price is not None:
            scenario["proposed_price_mxn"] = proposed_price

    if scenario.get("estimated_landed_cost_mxn") is None:
        landed_cost = _first_nested_value(
            scenario,
            (
                "estimated_landed_cost_mxn",
                "landed_cost_mxn",
                "estimated_landed_cost",
                "landed_cost",
                "unit_landed_cost_mxn",
                "unit_cost_mxn",
                "supplier_cost_mxn",
                "product_cost_mxn",
                "source_cost_mxn",
                "cost_mxn",
                "product_cost",
                "cost",
            ),
        )
        if landed_cost is not None:
            scenario["estimated_landed_cost_mxn"] = landed_cost

    return scenario

def materialize_smoke_feedback_run(
    smoke_result: Any,
    run_dir: Path | str,
    *,
    generated_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    """Write a local evidence run and derived feedback signal.

    The caller must provide an explicit run directory. The function writes only
    inside that directory.

    The outcome emitted here is an UNKNOWN placeholder. It intentionally does
    not mark the signal as OBSERVED because no real commercial outcome has
    occurred in the sandbox smoke.
    """

    output_dir = Path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = _as_mapping(smoke_result)
    if not payload and hasattr(smoke_result, "to_dict"):
        payload = _as_mapping(smoke_result.to_dict())

    candidate = _as_mapping(payload.get("candidate"))
    financial_input = _as_mapping(payload.get("financial_input"))
    financial_result = _as_mapping(payload.get("financial_result"))
    guard_trail = _as_mapping(payload.get("guard_trail"))
    decision_record = _as_mapping(payload.get("decision_record"))
    marketing_brief = payload.get("marketing_brief")

    decision_id = str(
        _first(
            decision_record,
            "run_id",
            "decision_id",
            fallback=_first(candidate, "candidate_id", "product_id", fallback="UNKNOWN_DECISION"),
        )
    )
    product_id = str(
        _first(
            decision_record,
            "candidate_id",
            fallback=_first(candidate, "candidate_id", "product_id", fallback=decision_id),
        )
    )
    product_name = str(
        _first(
            decision_record,
            "product_name",
            fallback=_first(candidate, "product_name", "name", fallback=product_id),
        )
    )

    price = _string_decimal(
        _first(financial_input, "price", fallback=_first(candidate, "price", fallback="0"))
    )
    landed_cost = _string_decimal(
        _first(
            financial_input,
            "landed_cost",
            "cost",
            fallback=_first(candidate, "cost", "landed_cost", fallback="0"),
        )
    )
    estimated_cac = _string_decimal(
        _first(financial_input, "estimated_cac", "cac", fallback="0")
    )

    expected_margin = _string_decimal(
        _first(
            financial_result,
            "expected_margin",
            "contribution_margin",
            "gross_margin",
            "net_margin",
            "profit",
            "margin",
            fallback="0",
        )
    )
    expected_roi = _string_decimal(
        _first(
            financial_result,
            "expected_roi",
            "roi",
            "roi_ratio",
            "return_on_ad_spend",
            fallback="0",
        )
    )

    scenario_payload = {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "scenario_id": decision_id,
        "decision_id": decision_id,
        "product_id": product_id,
        "candidate_id": product_id,
        "product_name": product_name,
        "source": "a8_r70_smoke_integration",
        "candidate": candidate,
        "financial_input": financial_input,
        "generated_at": generated_at,
    }

    decision_payload = {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "decision_id": decision_id,
        "run_id": decision_id,
        "product_id": product_id,
        "candidate_id": product_id,
        "product_name": product_name,
        "expected_decision": str(
            _first(decision_record, "final_decision", "expected_decision", fallback="UNKNOWN")
        ),
        "final_decision": str(_first(decision_record, "final_decision", fallback="UNKNOWN")),
        "final_outcome": str(_first(decision_record, "final_decision", fallback="UNKNOWN")),
        "permission_gate": str(_first(decision_record, "final_decision", fallback="UNKNOWN")),
        "financial_decision": str(_first(decision_record, "financial_decision", fallback="UNKNOWN")),
        "brief_built": bool(_first(decision_record, "brief_built", fallback=False)),
        "spend_guard_allowed": bool(_first(decision_record, "spend_guard_allowed", fallback=False)),
        "mutation_guard_blocked": bool(_first(decision_record, "mutation_guard_blocked", fallback=True)),
        "reason_codes": list(_first(decision_record, "reason_codes", fallback=[])),
        "price": price,
        "landed_cost": landed_cost,
        "estimated_cac": estimated_cac,
        "expected_margin": expected_margin,
        "expected_roi": expected_roi,
        "score": _string_decimal(_first(financial_result, "score", fallback="0")),
        "threshold": _string_decimal(_first(financial_result, "threshold", fallback="0")),
        "financial_result": financial_result,
        "guard_trail": guard_trail,
        "generated_at": generated_at,
    }

    safety_payload = {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "runtime_mode": "sandbox",
        "live_reads": 0,
        "live_writes": 0,
        "external_writes": 0,
        "real_spend": 0,
        "spend_guard": guard_trail,
        "generated_at": generated_at,
    }

    creative_payload = {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "product_id": product_id,
        "brief_built": marketing_brief is not None,
        "marketing_brief": marketing_brief,
        "generated_at": generated_at,
    }

    outcome_payload = {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "decision_id": decision_id,
        "product_id": product_id,
        "status": "UNKNOWN",
        "outcome_status": "UNKNOWN",
        "observed": False,
        "observed_at": None,
        "realized_margin": None,
        "realized_roi": None,
        "reason_codes": ["MISSING_REAL_OUTCOME"],
        "generated_at": generated_at,
    }

    ledger_rows = [
        {
            "schema_version": "a8_r79b.feedback_loop.v1",
            "event_type": "a8_r79b.feedback_loop.materialized",
            "decision_id": decision_id,
            "product_id": product_id,
            "source": "a8_r70_smoke_integration",
            "generated_at": generated_at,
        },
        {
            "schema_version": "a8_r79b.feedback_loop.v1",
            "event_type": "a8_r79b.outcome.placeholder_unknown",
            "decision_id": decision_id,
            "product_id": product_id,
            "reason_codes": ["MISSING_REAL_OUTCOME"],
            "generated_at": generated_at,
        },
    ]

    paths = {
        "scenario": output_dir / "scenario.json",
        "decision": output_dir / "decision.json",
        "safety": output_dir / "safety_posture.json",
        "creative": output_dir / "creative_pack.json",
        "ledger_sandbox": output_dir / "ledger_sandbox.ndjson",
        "ledger": output_dir / "ledger.ndjson",
        "outcome": output_dir / OUTCOME_PLACEHOLDER_FILE,
        "feedback_signal": output_dir / FEEDBACK_SIGNAL_FILE,
    }

    _dump_json(paths["scenario"], _with_reader_compatible_prediction_fields(scenario_payload))
    _dump_json(paths["decision"], decision_payload)
    _dump_json(paths["safety"], safety_payload)
    _dump_json(paths["creative"], creative_payload)
    _dump_ndjson(paths["ledger_sandbox"], ledger_rows)
    _dump_ndjson(paths["ledger"], ledger_rows)
    _dump_json(paths["outcome"], outcome_payload)

    signal = _call_build_feedback_signal(output_dir, generated_at)
    _call_write_feedback_signal(signal, paths["feedback_signal"])

    if not paths["feedback_signal"].is_file():
        raise RuntimeError("feedback_signal.json was not created")

    signal_payload = _normalize_feedback_signal_file(paths["feedback_signal"], output_dir)

    return {
        "schema_version": "a8_r79b.feedback_loop.v1",
        "run_dir": str(output_dir),
        "decision_id": decision_id,
        "product_id": product_id,
        "feedback_signal_path": str(paths["feedback_signal"]),
        "feedback_signal": signal_payload,
        "written_files": tuple(str(path) for path in paths.values()),
        "live_writes": 0,
        "external_writes": 0,
        "real_spend": 0,
    }


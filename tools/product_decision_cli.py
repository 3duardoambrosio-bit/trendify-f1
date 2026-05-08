"""SYNAPSE Product Decision CLI.

Deterministic CLI wrapper for the Product Decision Engine.

Input JSON contract:
    {
      "candidates": [...],
      "constraints": {... optional ...},
      "weights": {... optional ...},
      "backup_count": 3
    }

The top-level JSON may also be a raw list of candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from product_decision_engine import ENGINE_VERSION, select_product_candidates


CLI_VERSION = "A8-R32.product-decision-cli.v1"


def build_product_decision_artifact(input_payload: Any) -> dict[str, Any]:
    """Build a deterministic product decision artifact from JSON-compatible data."""

    normalized = _normalize_input_payload(input_payload)
    canonical_input = _canonical_json(normalized)
    input_sha256 = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest().upper()

    decision = select_product_candidates(
        normalized["candidates"],
        constraints=normalized.get("constraints"),
        weights=normalized.get("weights"),
        backup_count=normalized["backup_count"],
    )

    artifact = {
        "artifact_version": CLI_VERSION,
        "engine_version": ENGINE_VERSION,
        "artifact_type": "product_decision_packet",
        "input_sha256": input_sha256,
        "selection_mode": decision["selection_mode"],
        "manual_selection_used": decision["manual_selection_used"],
        "operator_role": "strategy_constraints_and_gate_approval",
        "decision": decision,
        "quality_gates": {
            "has_candidates": decision["counts"]["input"] > 0,
            "has_champion": decision["champion"] is not None,
            "champion_explainable": decision["acceptance"]["champion_explainable"],
            "manual_selection_blocked_as_primary_flow": (
                decision["acceptance"]["manual_selection_blocked_as_primary_flow"]
            ),
            "deterministic_input_hash_present": bool(input_sha256),
        },
    }

    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a SYNAPSE product decision artifact from candidate JSON."
    )
    parser.add_argument("--input", required=True, help="Path to product candidate JSON input.")
    parser.add_argument("--output", required=True, help="Path to write decision artifact JSON.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented JSON for review.",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        payload = _read_json(input_path)
        artifact = build_product_decision_artifact(payload)
        _write_json(output_path, artifact, pretty=args.pretty)
    except Exception as exc:
        print(f"PRODUCT_DECISION_CLI_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"PRODUCT_DECISION_CLI_VERSION={CLI_VERSION}")
    print(f"PRODUCT_DECISION_ENGINE_VERSION={ENGINE_VERSION}")
    print(f"PRODUCT_DECISION_INPUT_SHA256={artifact['input_sha256']}")
    print(f"PRODUCT_DECISION_OUTPUT={output_path}")
    print(f"PRODUCT_DECISION_MANUAL_SELECTION_USED={int(artifact['manual_selection_used'])}")
    print(f"PRODUCT_DECISION_HAS_CHAMPION={int(artifact['quality_gates']['has_champion'])}")
    print("PRODUCT_DECISION_CLI_PASS=1")
    return 0


def _normalize_input_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        normalized = {
            "candidates": payload,
            "constraints": None,
            "weights": None,
            "backup_count": 3,
        }
    elif isinstance(payload, dict):
        if "candidates" not in payload:
            raise ValueError("input object must contain candidates")
        normalized = {
            "candidates": payload["candidates"],
            "constraints": payload.get("constraints"),
            "weights": payload.get("weights"),
            "backup_count": payload.get("backup_count", 3),
        }
    else:
        raise ValueError("input payload must be an object or list")

    candidates = normalized["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    if not candidates:
        raise ValueError("candidates must not be empty")

    backup_count = normalized["backup_count"]
    if isinstance(backup_count, bool) or not isinstance(backup_count, int):
        raise ValueError("backup_count must be an integer")
    if backup_count < 0:
        raise ValueError("backup_count must be >= 0")

    constraints = normalized["constraints"]
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError("constraints must be an object when provided")

    weights = normalized["weights"]
    if weights is not None and not isinstance(weights, dict):
        raise ValueError("weights must be an object when provided")

    return normalized


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any], *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _canonical_json(payload, pretty=pretty)
    path.write_text(text + "\n", encoding="utf-8")


def _canonical_json(payload: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())

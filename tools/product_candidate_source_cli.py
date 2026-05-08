"""SYNAPSE Product Candidate Source CLI.

Executable wrapper for A8-R33 Product Candidate Source Contract.

Input:
    local JSON object/list containing product candidate rows.

Output:
    normalized candidate source packet JSON, ready for product decision CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from product_candidate_source import SOURCE_CONTRACT_VERSION, normalize_candidate_source


SOURCE_CLI_VERSION = "A8-R34.product-candidate-source-cli.v1"


def build_candidate_source_artifact(
    payload: Any,
    *,
    source_id: str,
) -> dict[str, Any]:
    """Build a deterministic normalized candidate source artifact."""

    normalized = normalize_candidate_source(payload, source_id=source_id)

    return {
        "artifact_version": SOURCE_CLI_VERSION,
        "artifact_type": "normalized_product_candidate_source",
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_id": normalized["source_id"],
        "source_sha256": normalized["source_sha256"],
        "manual_champion_provided": normalized["manual_champion_provided"],
        "selection_mode": normalized["selection_mode"],
        "candidates": normalized["candidates"],
        "rejected_rows": normalized["rejected_rows"],
        "source_quality_report": normalized["source_quality_report"],
        "quality_gates": normalized["quality_gates"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize SYNAPSE product candidate source JSON."
    )
    parser.add_argument("--input", required=True, help="Path to local candidate source JSON.")
    parser.add_argument("--output", required=True, help="Path to write normalized source artifact JSON.")
    parser.add_argument(
        "--source-id",
        default="local_candidate_source",
        help="Stable source identifier for audit output.",
    )
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
        artifact = build_candidate_source_artifact(payload, source_id=args.source_id)
        _write_json(output_path, artifact, pretty=args.pretty)
    except Exception as exc:
        print(f"PRODUCT_CANDIDATE_SOURCE_CLI_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    report = artifact["source_quality_report"]
    gates = artifact["quality_gates"]

    print(f"PRODUCT_CANDIDATE_SOURCE_CLI_VERSION={SOURCE_CLI_VERSION}")
    print(f"PRODUCT_CANDIDATE_SOURCE_CONTRACT_VERSION={SOURCE_CONTRACT_VERSION}")
    print(f"PRODUCT_CANDIDATE_SOURCE_ID={artifact['source_id']}")
    print(f"PRODUCT_CANDIDATE_SOURCE_SHA256={artifact['source_sha256']}")
    print(f"PRODUCT_CANDIDATE_SOURCE_OUTPUT={output_path}")
    print(f"PRODUCT_CANDIDATE_SOURCE_VALID_CANDIDATES={report['valid_candidates']}")
    print(f"PRODUCT_CANDIDATE_SOURCE_REJECTED_ROWS={report['rejected_rows']}")
    print(f"PRODUCT_CANDIDATE_SOURCE_READY_FOR_DECISION_CLI={int(gates['ready_for_product_decision_cli'])}")
    print(f"PRODUCT_CANDIDATE_SOURCE_MANUAL_CHAMPION_PROVIDED={int(artifact['manual_champion_provided'])}")
    print("PRODUCT_CANDIDATE_SOURCE_CLI_PASS=1")
    return 0


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

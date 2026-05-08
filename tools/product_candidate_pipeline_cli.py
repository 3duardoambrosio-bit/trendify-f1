"""SYNAPSE Local Product Candidate Pipeline CLI.

A8-R35 chains local candidate source normalization into product decision artifact
generation without scraping, supplier APIs, external commerce writes, paid media spend, or manual
champion selection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from product_candidate_source_cli import (
    SOURCE_CLI_VERSION,
    build_candidate_source_artifact,
)
from product_decision_cli import CLI_VERSION as DECISION_CLI_VERSION
from product_decision_cli import build_product_decision_artifact


PIPELINE_CLI_VERSION = "A8-R35.product-candidate-pipeline-cli.v1"

SOURCE_ARTIFACT_FILENAME = "normalized_candidate_source.json"
DECISION_ARTIFACT_FILENAME = "product_decision_artifact.json"
PIPELINE_MANIFEST_FILENAME = "product_candidate_pipeline_manifest.json"


def build_product_candidate_pipeline_artifact(
    source_payload: Any,
    *,
    source_id: str,
    backup_count: int,
) -> dict[str, Any]:
    """Build a deterministic local pipeline manifest."""

    if isinstance(backup_count, bool) or not isinstance(backup_count, int):
        raise ValueError("backup_count must be an integer")
    if backup_count < 0:
        raise ValueError("backup_count must be >= 0")

    source_artifact = build_candidate_source_artifact(
        source_payload,
        source_id=source_id,
    )

    decision_payload = {
        "backup_count": backup_count,
        "candidates": source_artifact["candidates"],
    }

    decision_artifact = build_product_decision_artifact(decision_payload)
    champion = decision_artifact["decision"]["champion"]

    manifest = {
        "artifact_version": PIPELINE_CLI_VERSION,
        "artifact_type": "local_product_candidate_pipeline_manifest",
        "source_cli_version": SOURCE_CLI_VERSION,
        "decision_cli_version": DECISION_CLI_VERSION,
        "source_id": source_artifact["source_id"],
        "source_sha256": source_artifact["source_sha256"],
        "decision_input_sha256": decision_artifact["input_sha256"],
        "selection_mode": decision_artifact["selection_mode"],
        "manual_selection_used": decision_artifact["manual_selection_used"],
        "manual_champion_provided": source_artifact["manual_champion_provided"],
        "backup_count": backup_count,
        "counts": {
            "source_input_rows": source_artifact["source_quality_report"]["input_rows"],
            "source_valid_candidates": source_artifact["source_quality_report"]["valid_candidates"],
            "source_rejected_rows": source_artifact["source_quality_report"]["rejected_rows"],
            "decision_input_candidates": decision_artifact["decision"]["counts"]["input"],
            "decision_passed_candidates": decision_artifact["decision"]["counts"]["passed"],
            "decision_blocked_candidates": decision_artifact["decision"]["counts"]["blocked"],
            "decision_backups": decision_artifact["decision"]["counts"]["backups"],
        },
        "champion_sku": champion["sku"] if champion else None,
        "pipeline_quality_gates": {
            "source_ready_for_decision_cli": source_artifact["quality_gates"][
                "ready_for_product_decision_cli"
            ],
            "decision_has_champion": decision_artifact["quality_gates"]["has_champion"],
            "decision_champion_explainable": decision_artifact["quality_gates"][
                "champion_explainable"
            ],
            "manual_selection_blocked": (
                source_artifact["manual_champion_provided"] is False
                and decision_artifact["manual_selection_used"] is False
            ),
            "local_only_execution": True,
        },
        "output_files": {
            "source_artifact": SOURCE_ARTIFACT_FILENAME,
            "decision_artifact": DECISION_ARTIFACT_FILENAME,
            "pipeline_manifest": PIPELINE_MANIFEST_FILENAME,
        },
    }

    return {
        "source_artifact": source_artifact,
        "decision_artifact": decision_artifact,
        "pipeline_manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run local SYNAPSE candidate source normalization and product decision."
    )
    parser.add_argument("--input", required=True, help="Path to local candidate source JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for pipeline artifacts.")
    parser.add_argument(
        "--source-id",
        default="local_candidate_source",
        help="Stable source identifier for audit output.",
    )
    parser.add_argument(
        "--backup-count",
        type=int,
        default=3,
        help="Number of backup candidates to include in decision artifact.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented JSON artifacts for review.",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    try:
        payload = _read_json(input_path)
        result = build_product_candidate_pipeline_artifact(
            payload,
            source_id=args.source_id,
            backup_count=args.backup_count,
        )
        _write_pipeline_outputs(output_dir, result, pretty=args.pretty)
    except Exception as exc:
        print(f"PRODUCT_CANDIDATE_PIPELINE_CLI_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    manifest = result["pipeline_manifest"]
    gates = manifest["pipeline_quality_gates"]

    print(f"PRODUCT_CANDIDATE_PIPELINE_CLI_VERSION={PIPELINE_CLI_VERSION}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_SOURCE_CLI_VERSION={SOURCE_CLI_VERSION}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_DECISION_CLI_VERSION={DECISION_CLI_VERSION}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_OUTPUT_DIR={output_dir}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_SOURCE_SHA256={manifest['source_sha256']}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_DECISION_INPUT_SHA256={manifest['decision_input_sha256']}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_CHAMPION_SKU={manifest['champion_sku']}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_MANUAL_SELECTION_USED={int(manifest['manual_selection_used'])}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_MANUAL_CHAMPION_PROVIDED={int(manifest['manual_champion_provided'])}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_SOURCE_READY={int(gates['source_ready_for_decision_cli'])}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_DECISION_HAS_CHAMPION={int(gates['decision_has_champion'])}")
    print(f"PRODUCT_CANDIDATE_PIPELINE_LOCAL_ONLY_EXECUTION={int(gates['local_only_execution'])}")
    print("PRODUCT_CANDIDATE_PIPELINE_CLI_PASS=1")
    return 0


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_pipeline_outputs(
    output_dir: Path,
    result: dict[str, Any],
    *,
    pretty: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_json(output_dir / SOURCE_ARTIFACT_FILENAME, result["source_artifact"], pretty=pretty)
    _write_json(output_dir / DECISION_ARTIFACT_FILENAME, result["decision_artifact"], pretty=pretty)
    _write_json(output_dir / PIPELINE_MANIFEST_FILENAME, result["pipeline_manifest"], pretty=pretty)


def _write_json(path: Path, payload: dict[str, Any], *, pretty: bool) -> None:
    text = _canonical_json(payload, pretty=pretty)
    path.write_text(text + "\n", encoding="utf-8")


def _canonical_json(payload: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())

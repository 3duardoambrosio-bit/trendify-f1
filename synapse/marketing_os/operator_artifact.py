from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from synapse.marketing_os.selling_pack import (
    SELLING_PACK_BOUNDARIES,
    build_first_selling_pack_dict,
)

FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION = "a8-r88.first_selling_pack_artifact.v1"
DEFAULT_ARTIFACT_TIMESTAMP = "2026-06-19T00:00:00Z"

FIRST_SELLING_PACK_ARTIFACT_BOUNDARIES: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *SELLING_PACK_BOUNDARIES,
            "local_artifact_only",
            "operator_review_required",
        )
    )
)


@dataclass(frozen=True)
class FirstSellingPackArtifact:
    """Local-only persisted operator artifact for a FirstSellingPack."""

    artifact_dir: Path
    run_id: str
    manifest: Mapping[str, Any]
    files: Mapping[str, Path]

    def to_dict(self) -> dict[str, Any]:
        return first_selling_pack_artifact_to_dict(self)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return value


def _mapping_get(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _slug(value: Any, default: str) -> str:
    text = _text(value, default).lower()
    chars: list[str] = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    slug = "".join(chars).strip("-")
    return slug[:64] or default


def _stable_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_stable_json_bytes(payload)).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(text + "\n", encoding="utf-8")


def _write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_ndjson(path: Path, events: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(_json_safe(event), ensure_ascii=False, sort_keys=True)
        for event in events
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _product_id(product: Any) -> str:
    return _text(
        _mapping_get(
            product,
            "product_id",
            _mapping_get(product, "candidate_id", _mapping_get(product, "id", None)),
        ),
        "unknown-product",
    )


def _product_name(product: Any) -> str:
    return _text(
        _mapping_get(product, "title", _mapping_get(product, "name", None)),
        "Unknown product",
    )


def _derive_run_id(product: Any, decision: Any, generated_at: str, daily_budget_mxn: Any) -> str:
    seed = {
        "schema_version": FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION,
        "product": _json_safe(product),
        "decision": _json_safe(decision),
        "generated_at": generated_at,
        "daily_budget_mxn": _json_safe(daily_budget_mxn),
    }
    digest = _sha256(seed)[:12]
    return f"a8_r88_{_slug(_product_id(product), 'product')}_{digest}"


def _operator_review_lines(pack: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    warnings = list(pack.get("warnings") or [])
    lines = [
        "# First Selling Pack Operator Review",
        "",
        f"- Schema: {manifest['schema_version']}",
        f"- Run ID: {manifest['run_id']}",
        f"- Product ID: {manifest['product_id']}",
        f"- Product name: {manifest['product_name']}",
        f"- Platform: {pack.get('expert_pack', {}).get('campaign', {}).get('platform', 'unknown')}",
        f"- Ready for operator review: {pack.get('ready_for_operator_review')}",
        "",
        "## Boundaries",
        "",
    ]
    lines.extend(f"- {boundary}" for boundary in manifest["boundaries"])
    lines.extend(
        [
            "",
            "## Operator checklist",
            "",
            "- Review claims before any external use.",
            "- Do not publish automatically.",
            "- Do not spend automatically.",
            "- Do not create fulfillment action.",
            "- Keep this artifact local unless an audited export path exists.",
            "",
            "## Warnings",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    return lines


def first_selling_pack_artifact_to_dict(
    artifact: FirstSellingPackArtifact,
) -> dict[str, Any]:
    return {
        "artifact_dir": str(artifact.artifact_dir),
        "run_id": artifact.run_id,
        "manifest": dict(artifact.manifest),
        "files": {key: str(path) for key, path in artifact.files.items()},
    }


def write_first_selling_pack_artifact(
    product: Any,
    decision: Any,
    output_root: str | Path,
    *,
    run_id: str | None = None,
    daily_budget_mxn: Decimal | str | int | None = None,
    generated_at: str = DEFAULT_ARTIFACT_TIMESTAMP,
) -> FirstSellingPackArtifact:
    """Persist a local-only FirstSellingPack operator artifact.

    This function writes local evidence files only. It does not call external
    networks, connectors, publishing systems, ad APIs, fulfillment APIs, or spend
    surfaces.
    """

    resolved_run_id = run_id or _derive_run_id(
        product,
        decision,
        generated_at,
        daily_budget_mxn,
    )
    artifact_dir = Path(output_root) / resolved_run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    pack = build_first_selling_pack_dict(
        product,
        decision,
        daily_budget_mxn=daily_budget_mxn,
    )

    product_id = _text(pack.get("product_id"), _product_id(product))
    product_name = _text(pack.get("product_name"), _product_name(product))

    scenario = {
        "schema_version": "a8-r88.operator_artifact_scenario.v1",
        "source": "a8_r88_first_selling_pack_artifact",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "dry_run": True,
        "product_id": product_id,
        "product_name": product_name,
        "product": _json_safe(product),
        "boundaries": list(FIRST_SELLING_PACK_ARTIFACT_BOUNDARIES),
    }

    decision_payload = {
        "schema_version": "a8-r88.operator_artifact_decision.v1",
        "source": "a8_r88_first_selling_pack_artifact",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "product_id": product_id,
        "product_name": product_name,
        "source_decision": _json_safe(decision),
        "ready_for_operator_review": bool(pack.get("ready_for_operator_review")),
        "warnings": list(pack.get("warnings") or []),
        "boundaries": list(FIRST_SELLING_PACK_ARTIFACT_BOUNDARIES),
    }

    burnin_summary = {
        "schema_version": "a8-r88.operator_artifact_burnin_summary.v1",
        "run_id": resolved_run_id,
        "checks": {
            "local_artifact_only": True,
            "dry_run_only": True,
            "operator_in_control": True,
            "no_live_writes": True,
            "no_automatic_spend": True,
            "no_fulfillment_automation": True,
            "claims_require_operator_review": True,
        },
    }

    ledger_event = {
        "schema_version": "a8-r88.operator_artifact_ledger_event.v1",
        "event_type": "first_selling_pack_artifact_written",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "product_id": product_id,
        "product_name": product_name,
        "dry_run": True,
        "external_side_effects": False,
    }

    files: dict[str, Path] = {
        "scenario": artifact_dir / "scenario.json",
        "decision": artifact_dir / "decision.json",
        "first_selling_pack": artifact_dir / "first_selling_pack.json",
        "marketing_brief": artifact_dir / "marketing_brief.json",
        "expert_pack": artifact_dir / "expert_pack.json",
        "burnin_summary": artifact_dir / "burnin_summary.json",
        "ledger": artifact_dir / "ledger.ndjson",
        "ledger_sandbox": artifact_dir / "ledger_sandbox.ndjson",
        "operator_review": artifact_dir / "operator_review.md",
        "creative_bundle_review": artifact_dir / "creative_bundle" / "operator_review.md",
        "manifest": artifact_dir / "manifest.json",
    }

    _write_json(files["scenario"], scenario)
    _write_json(files["decision"], decision_payload)
    _write_json(files["first_selling_pack"], pack)
    _write_json(files["marketing_brief"], pack["marketing_brief"])
    _write_json(files["expert_pack"], pack["expert_pack"])
    _write_json(files["burnin_summary"], burnin_summary)
    _write_ndjson(files["ledger"], [ledger_event])
    _write_ndjson(files["ledger_sandbox"], [ledger_event])

    manifest = {
        "schema_version": FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "first_selling_pack_operator_artifact",
        "run_id": resolved_run_id,
        "generated_at": generated_at,
        "product_id": product_id,
        "product_name": product_name,
        "boundaries": list(FIRST_SELLING_PACK_ARTIFACT_BOUNDARIES),
        "files": {
            key: str(path.relative_to(artifact_dir))
            for key, path in files.items()
            if key != "manifest"
        },
        "content_sha256": {
            "scenario": _sha256(scenario),
            "decision": _sha256(decision_payload),
            "first_selling_pack": _sha256(pack),
            "marketing_brief": _sha256(pack["marketing_brief"]),
            "expert_pack": _sha256(pack["expert_pack"]),
            "burnin_summary": _sha256(burnin_summary),
            "ledger_event": _sha256(ledger_event),
        },
    }

    _write_text(files["operator_review"], _operator_review_lines(pack, manifest))
    _write_text(files["creative_bundle_review"], _operator_review_lines(pack, manifest))
    _write_json(files["manifest"], manifest)

    return FirstSellingPackArtifact(
        artifact_dir=artifact_dir,
        run_id=resolved_run_id,
        manifest=manifest,
        files=files,
    )


__all__ = [
    "FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION",
    "FIRST_SELLING_PACK_ARTIFACT_BOUNDARIES",
    "FirstSellingPackArtifact",
    "first_selling_pack_artifact_to_dict",
    "write_first_selling_pack_artifact",
]
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from synapse.ui.read_model import (
    build_first_selling_pack_artifact_inventory,
    load_first_selling_pack_artifacts,
)

OPERATOR_CONSOLE_SCHEMA_VERSION = "a8-r89.operator_console.v1"

OPERATOR_CONSOLE_STAGE_ORDER: tuple[str, ...] = (
    "product",
    "evaluation",
    "decision",
    "selling_pack",
    "operator_artifact",
)

OPERATOR_CONSOLE_BOUNDARIES: tuple[str, ...] = (
    "dry_run_only",
    "operator_in_control",
    "no_live_writes",
    "no_automatic_spend",
    "no_fulfillment_automation",
    "claims_require_operator_review",
    "local_artifact_only",
    "operator_review_required",
)

READY = "ready"
MISSING = "missing"
EMPTY = "empty"
UNKNOWN = "unknown"


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_str(value: Any, *, default: str = UNKNOWN) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    return str(value)


def _first_text(*values: Any, default: str = UNKNOWN) -> str:
    for value in values:
        text = _safe_str(value, default="")
        if text:
            return text
    return default


def _has_data(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    if value == {}:
        return False
    return True


def _status(*values: Any) -> str:
    return READY if any(_has_data(value) for value in values) else MISSING


def _call_read_model(
    func: Callable[..., Any],
    root: str | Path,
    *,
    limit: int,
) -> Any:
    try:
        return func(root, limit=limit)
    except TypeError:
        return func(root)


def _artifacts_from_loader_result(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        candidates = (
            value.get("artifacts")
            or value.get("items")
            or value.get("rows")
            or []
        )
    else:
        candidates = value

    artifacts: list[Mapping[str, Any]] = []
    for item in _sequence(candidates):
        mapped = _mapping(item)
        if mapped:
            artifacts.append(mapped)
    return artifacts


def _normalize_boundaries(*sources: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for source in sources:
        for item in _sequence(source):
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)

    return out


def _stage_statuses(
    *,
    product_id: str,
    product_name: str,
    evaluation: Mapping[str, Any],
    decision: Mapping[str, Any],
    pack: Mapping[str, Any],
    manifest: Mapping[str, Any],
    artifact_dir: str,
) -> list[dict[str, str]]:
    return [
        {
            "stage": "product",
            "status": _status(product_id if product_id != UNKNOWN else None, product_name if product_name != UNKNOWN else None),
        },
        {
            "stage": "evaluation",
            "status": _status(evaluation, decision.get("financials"), decision.get("financial_summary")),
        },
        {
            "stage": "decision",
            "status": _status(decision, decision.get("decision"), decision.get("status")),
        },
        {
            "stage": "selling_pack",
            "status": _status(pack, pack.get("expert_pack"), pack.get("marketing_brief")),
        },
        {
            "stage": "operator_artifact",
            "status": _status(manifest, artifact_dir if artifact_dir != UNKNOWN else None),
        },
    ]


def build_operator_console_row(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Build one deterministic local read-only operator console row.

    The row is derived from already-persisted FirstSellingPack artifacts. This
    function does not mutate evidence, call external systems, publish, spend, or
    execute connector code.
    """

    mapped = _mapping(artifact)
    manifest = _mapping(mapped.get("manifest"))
    pack = _mapping(
        mapped.get("first_selling_pack")
        or mapped.get("selling_pack")
        or mapped.get("pack")
    )
    decision = _mapping(mapped.get("decision") or pack.get("decision"))
    marketing_brief = _mapping(
        mapped.get("marketing_brief")
        or pack.get("marketing_brief")
    )
    expert_pack = _mapping(
        mapped.get("expert_pack")
        or pack.get("expert_pack")
    )
    evaluation = _mapping(
        mapped.get("evaluation")
        or mapped.get("financial_evaluation")
        or mapped.get("financial")
        or pack.get("evaluation")
        or pack.get("financial")
    )

    artifact_dir = _first_text(
        mapped.get("artifact_dir"),
        mapped.get("run_dir"),
        manifest.get("artifact_dir"),
    )
    run_id = _first_text(
        mapped.get("run_id"),
        manifest.get("run_id"),
        Path(artifact_dir).name if artifact_dir != UNKNOWN else None,
    )
    product_id = _first_text(
        mapped.get("product_id"),
        manifest.get("product_id"),
        pack.get("product_id"),
    )
    product_name = _first_text(
        mapped.get("product_name"),
        manifest.get("product_name"),
        pack.get("product_name"),
        pack.get("name"),
    )
    decision_label = _first_text(
        decision.get("decision"),
        decision.get("status"),
        pack.get("decision"),
        manifest.get("decision"),
    )
    platform = _first_text(
        mapped.get("platform"),
        manifest.get("platform"),
        _mapping(expert_pack.get("campaign")).get("platform"),
        _mapping(pack.get("campaign")).get("platform"),
    )

    ready_for_operator_review = bool(
        mapped.get("ready_for_operator_review")
        or manifest.get("ready_for_operator_review")
        or pack.get("ready_for_operator_review")
    )

    warnings = [
        str(item)
        for item in _sequence(
            mapped.get("warnings")
            or pack.get("warnings")
            or manifest.get("warnings")
        )
        if str(item).strip()
    ]

    boundaries = _normalize_boundaries(
        manifest.get("boundaries"),
        pack.get("boundaries"),
        OPERATOR_CONSOLE_BOUNDARIES,
    )

    stage_statuses = _stage_statuses(
        product_id=product_id,
        product_name=product_name,
        evaluation=evaluation,
        decision=decision,
        pack=pack,
        manifest=manifest,
        artifact_dir=artifact_dir,
    )

    return {
        "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
        "run_id": run_id,
        "artifact_dir": artifact_dir,
        "product_id": product_id,
        "product_name": product_name,
        "decision": decision_label,
        "platform": platform,
        "ready_for_operator_review": ready_for_operator_review,
        "stage_order": list(OPERATOR_CONSOLE_STAGE_ORDER),
        "stage_statuses": stage_statuses,
        "warnings": warnings,
        "boundaries": boundaries,
        "has_marketing_brief": bool(marketing_brief),
        "has_expert_pack": bool(expert_pack),
        "read_only": True,
        "external_side_effects": False,
    }


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _safe_str(row.get("run_id")),
        _safe_str(row.get("product_id")),
        _safe_str(row.get("artifact_dir")),
    )


def build_operator_console_model(
    root: str | Path,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Build the local read-only operator console model.

    Source of truth is the persisted FirstSellingPack artifact read-model. This
    function returns data only. It does not perform UI rendering and does not
    mutate local or external state.
    """

    root_path = Path(root)
    inventory = _call_read_model(
        build_first_selling_pack_artifact_inventory,
        root_path,
        limit=limit,
    )
    artifacts = _artifacts_from_loader_result(
        _call_read_model(load_first_selling_pack_artifacts, root_path, limit=limit)
    )
    rows = sorted(
        (build_operator_console_row(artifact) for artifact in artifacts),
        key=_sort_key,
    )

    return {
        "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
        "root": str(root_path),
        "status": READY if rows else EMPTY,
        "row_count": len(rows),
        "limit": limit,
        "stage_order": list(OPERATOR_CONSOLE_STAGE_ORDER),
        "boundaries": list(OPERATOR_CONSOLE_BOUNDARIES),
        "rows": rows,
        "inventory": inventory,
        "read_only": True,
        "external_side_effects": False,
    }


def build_operator_console_panel(
    root: str | Path,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Build a presentation-ready, read-only panel payload."""

    model = build_operator_console_model(root, limit=limit)
    ready_rows = sum(
        1
        for row in model["rows"]
        if row.get("ready_for_operator_review") is True
    )

    return {
        "schema_version": OPERATOR_CONSOLE_SCHEMA_VERSION,
        "title": "Operator Console",
        "status": model["status"],
        "row_count": model["row_count"],
        "ready_for_operator_review_count": ready_rows,
        "stage_order": list(OPERATOR_CONSOLE_STAGE_ORDER),
        "rows": model["rows"],
        "read_only": True,
        "external_side_effects": False,
    }


__all__ = [
    "OPERATOR_CONSOLE_BOUNDARIES",
    "OPERATOR_CONSOLE_SCHEMA_VERSION",
    "OPERATOR_CONSOLE_STAGE_ORDER",
    "build_operator_console_model",
    "build_operator_console_panel",
    "build_operator_console_row",
]
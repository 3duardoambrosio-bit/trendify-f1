"""First dry-run selling pack consumer for Marketing Expert Foundation.

This module is the first operational consumer of A8-R86.

It does not publish, spend, fulfill, or call external services. It composes the
existing Marketing OS brief contract with the Expert Foundation pack and returns
a deterministic operator-review package.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from synapse.marketing_os.brief_builder import build_marketing_brief_dict
from synapse.marketing_os.expert_foundation import (
    MarketingExpertPack,
    build_marketing_expert_pack,
    pack_to_dict,
)


SELLING_PACK_BOUNDARIES = (
    "dry_run_only",
    "operator_in_control",
    "no_live_writes",
    "no_automatic_spend",
    "no_fulfillment_automation",
    "claims_require_operator_review",
)


@dataclass(frozen=True)
class FirstSellingPack:
    """Operator-review package built from a product decision."""

    product_id: str
    product_name: str
    marketing_brief: Mapping[str, Any]
    expert_pack: Mapping[str, Any]
    permission_status: str
    ready_for_operator_review: bool
    boundaries: tuple[str, ...]
    warnings: tuple[str, ...]


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _mapping_get(source: Any, key: str, fallback: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, fallback)
    return getattr(source, key, fallback)


def _nested_status(marketing_brief: Mapping[str, Any]) -> str:
    permission = marketing_brief.get("permission")

    if isinstance(permission, Mapping):
        return _text(permission.get("status"), "review_required")

    if hasattr(permission, "status"):
        return _text(getattr(permission, "status"), "review_required")

    return _text(marketing_brief.get("permission_status"), "review_required")


def _product_id(product: Any, marketing_brief: Mapping[str, Any]) -> str:
    return _text(
        marketing_brief.get("product_id")
        or _mapping_get(product, "product_id")
        or _mapping_get(product, "candidate_id")
        or _mapping_get(product, "id"),
        "unknown-product",
    )


def _product_name(product: Any, marketing_brief: Mapping[str, Any]) -> str:
    return _text(
        marketing_brief.get("product_name")
        or _mapping_get(product, "title")
        or _mapping_get(product, "name")
        or _mapping_get(product, "product_name"),
        "Producto sin nombre",
    )


def build_first_selling_pack(
    product: Mapping[str, Any] | Any,
    decision: Mapping[str, Any] | Any,
    *,
    financials: Mapping[str, Any] | None = None,
    daily_budget_mxn: Decimal | str | int = Decimal("300"),
) -> FirstSellingPack:
    """Build the first dry-run selling pack for operator review."""

    marketing_brief = build_marketing_brief_dict(product, decision)

    expert: MarketingExpertPack = build_marketing_expert_pack(
        product if isinstance(product, Mapping) else {
            "title": _product_name(product, marketing_brief),
            "product_id": _product_id(product, marketing_brief),
        },
        financials or (decision if isinstance(decision, Mapping) else {}),
        daily_budget_mxn=daily_budget_mxn,
    )
    expert_dict = pack_to_dict(expert)

    permission_status = _nested_status(marketing_brief)
    expert_boundaries = tuple(str(x) for x in expert_dict.get("boundaries", ()))
    boundaries = tuple(dict.fromkeys(SELLING_PACK_BOUNDARIES + expert_boundaries))

    ready_for_operator_review = (
        permission_status in {"allowed", "review_required"}
        and "no_live_writes" in boundaries
        and "no_automatic_spend" in boundaries
        and "dry_run_only" in boundaries
    )

    warnings = tuple(str(x) for x in expert_dict.get("warnings", ()))

    return FirstSellingPack(
        product_id=_product_id(product, marketing_brief),
        product_name=_product_name(product, marketing_brief),
        marketing_brief=marketing_brief,
        expert_pack=expert_dict,
        permission_status=permission_status,
        ready_for_operator_review=ready_for_operator_review,
        boundaries=boundaries,
        warnings=warnings,
    )


def first_selling_pack_to_dict(pack: FirstSellingPack) -> dict[str, Any]:
    """Serialize a FirstSellingPack into JSON-friendly primitives."""

    return {
        "product_id": pack.product_id,
        "product_name": pack.product_name,
        "marketing_brief": dict(pack.marketing_brief),
        "expert_pack": dict(pack.expert_pack),
        "permission_status": pack.permission_status,
        "ready_for_operator_review": pack.ready_for_operator_review,
        "boundaries": list(pack.boundaries),
        "warnings": list(pack.warnings),
    }


def build_first_selling_pack_dict(
    product: Mapping[str, Any] | Any,
    decision: Mapping[str, Any] | Any,
    *,
    financials: Mapping[str, Any] | None = None,
    daily_budget_mxn: Decimal | str | int = Decimal("300"),
) -> dict[str, Any]:
    """Build and serialize the first dry-run selling pack."""

    return first_selling_pack_to_dict(
        build_first_selling_pack(
            product,
            decision,
            financials=financials,
            daily_budget_mxn=daily_budget_mxn,
        )
    )
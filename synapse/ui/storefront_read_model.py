"""Deterministic local storefront read model for A8-R112I1.

The builder consumes operator-controlled A8-R110 catalog fixtures together with
their explicit A8-R111 methodology context. It emits a JSON-ready local preview
model only.

It performs no IO, network access, external mutation, checkout, publication,
spend, campaign creation, Shopify mutation, Meta mutation, or fulfillment.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

SCHEMA_VERSION = "a8-r112.storefront_read_model.v1"
MODE = "LOCAL_PREVIEW"
SOURCE_KIND = "operator_local_catalog_import"
CURRENCY = "MXN"
METHODOLOGY_SCHEMA_VERSION = (
    "synapse.marketing_methodology.decision_engine.v1"
)

STATUS_READY = "READY"
STATUS_PRICE_MISSING = "PRICE_MISSING"
STATUS_METHODOLOGY_MISSING = "METHODOLOGY_MISSING"
STATUS_PRICE_AND_METHODOLOGY_MISSING = (
    "PRICE_AND_METHODOLOGY_MISSING"
)

_REQUIRED_ITEM_FIELDS = frozenset({"fixture", "methodology_context"})
_REQUIRED_CONTEXT_FIELDS: tuple[str, ...] = (
    "product_facts",
    "product_id",
    "buyer_state",
    "proof_available",
    "claim_risk",
    "channel",
    "margin_profile",
    "category",
)
_ALLOWED_CONTEXT_FIELDS = frozenset(
    (*_REQUIRED_CONTEXT_FIELDS, "candidate_output")
)
_MONEY = Decimal("0.01")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ABSOLUTE_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")


class StorefrontReadModelError(ValueError):
    """Raised when the local storefront contract must fail closed."""


def build_storefront_read_model(
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic, non-publishable local storefront read model.

    Each item must contain exactly:
    - ``fixture``: an A8-R110 fixture, optionally enriched by A8-R111.
    - ``methodology_context``: the exact explicit operator context used by R111.

    The context is validated for binding and readiness but is not copied into
    public content. Methodology safe output is also never treated as publication
    authorization or customer-facing copy.
    """

    materialized = _require_sequence(items, "items", allow_empty=True)
    products: list[dict[str, Any]] = []
    seen_product_ids: set[str] = set()
    seen_product_slugs: dict[str, str] = {}
    collection_members: dict[str, dict[str, Any]] = {}

    for index, raw_item in enumerate(materialized):
        item_path = f"items[{index}]"
        item = _require_mapping(raw_item, item_path)
        _require_exact_keys(
            item,
            required=_REQUIRED_ITEM_FIELDS,
            allowed=_REQUIRED_ITEM_FIELDS,
            path=item_path,
        )

        fixture = _require_mapping(
            item.get("fixture"),
            f"{item_path}.fixture",
        )
        context = _validate_methodology_context(
            item.get("methodology_context"),
            f"{item_path}.methodology_context",
        )
        product = _build_product(
            fixture=fixture,
            context=context,
            path=item_path,
        )

        product_id = product["product_id"]
        product_slug = product["slug"]

        if product_id in seen_product_ids:
            raise StorefrontReadModelError(
                f"duplicate_product_id={product_id}"
            )
        seen_product_ids.add(product_id)

        prior_product_id = seen_product_slugs.get(product_slug)
        if prior_product_id is not None:
            raise StorefrontReadModelError(
                "duplicate_product_slug="
                f"{product_slug}:{prior_product_id},{product_id}"
            )
        seen_product_slugs[product_slug] = product_id

        category = product["category"]
        collection_slug = _slug(category, f"{item_path}.product.category")
        collection = collection_members.setdefault(
            collection_slug,
            {
                "slug": collection_slug,
                "title": category,
                "product_ids": [],
            },
        )
        if collection["title"] != category:
            raise StorefrontReadModelError(
                "collection_slug_collision="
                f"{collection_slug}:{collection['title']},{category}"
            )
        collection["product_ids"].append(product_id)
        products.append(product)

    products.sort(key=lambda item: item["product_id"])

    collections: list[dict[str, Any]] = []
    for collection_slug in sorted(collection_members):
        collection = collection_members[collection_slug]
        collections.append(
            {
                "slug": collection["slug"],
                "title": collection["title"],
                "product_ids": sorted(collection["product_ids"]),
                "routes": {
                    "collection": f"/collections/{collection_slug}",
                },
            }
        )

    featured_product_ids = [
        product["product_id"]
        for product in products
        if product["preview_status"] == STATUS_READY
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "currency": CURRENCY,
        "safety": {
            "checkout_enabled": False,
            "publication_enabled": False,
            "external_writes_enabled": False,
            "fulfillment_enabled": False,
            "spend_enabled": False,
        },
        "home": {
            "featured_product_ids": featured_product_ids,
            "routes": {"home": "/"},
        },
        "collections": collections,
        "products": products,
    }


def serialize_storefront_read_model(
    model: Mapping[str, Any],
) -> str:
    """Serialize a read model into canonical deterministic JSON bytes-as-text."""

    if not isinstance(model, Mapping):
        raise StorefrontReadModelError("model must be a mapping")

    try:
        return (
            json.dumps(
                model,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise StorefrontReadModelError(
            "model must be finite and JSON serializable"
        ) from exc


def _build_product(
    *,
    fixture: Mapping[str, Any],
    context: Mapping[str, Any],
    path: str,
) -> dict[str, Any]:
    source_kind = _require_nonempty_text(
        fixture.get("source_kind"),
        f"{path}.fixture.source_kind",
    )
    if source_kind != SOURCE_KIND:
        raise StorefrontReadModelError(
            f"{path}.fixture.source_kind must be {SOURCE_KIND}"
        )

    product = _require_mapping(
        fixture.get("product"),
        f"{path}.fixture.product",
    )
    product_id = _require_nonempty_text(
        product.get("product_id"),
        f"{path}.fixture.product.product_id",
    )
    title = _require_nonempty_text(
        product.get("name"),
        f"{path}.fixture.product.name",
    )
    category = _require_nonempty_text(
        product.get("category"),
        f"{path}.fixture.product.category",
    )
    _require_nonempty_text(
        product.get("supplier"),
        f"{path}.fixture.product.supplier",
    )
    market = _require_nonempty_text(
        product.get("market"),
        f"{path}.fixture.product.market",
    )
    if market != "MX":
        raise StorefrontReadModelError(
            f"{path}.fixture.product.market must be MX"
        )

    decision = _require_mapping(
        fixture.get("decision"),
        f"{path}.fixture.decision",
    )
    outcome = _require_nonempty_text(
        decision.get("outcome"),
        f"{path}.fixture.decision.outcome",
    )
    permission_gate = _require_nonempty_text(
        decision.get("permission_gate"),
        f"{path}.fixture.decision.permission_gate",
    )
    if permission_gate != "REVIEW":
        raise StorefrontReadModelError(
            f"{path}.fixture.decision.permission_gate must remain REVIEW"
        )

    if context["product_id"] != product_id:
        raise StorefrontReadModelError(
            f"{path}.methodology_context.product_id must exactly match "
            "fixture.product.product_id"
        )
    if context["category"] != category:
        raise StorefrontReadModelError(
            f"{path}.methodology_context.category must exactly match "
            "fixture.product.category"
        )

    methodology_present, methodology_status, review_required = (
        _validate_methodology(
            decision.get("methodology"),
            f"{path}.fixture.decision.methodology",
        )
    )
    price = _build_price(
        fixture.get("economics"),
        f"{path}.fixture.economics",
    )
    preview_status = _preview_status(
        price_available=price["state"] == "AVAILABLE",
        methodology_present=methodology_present,
    )
    product_slug = _slug(product_id, f"{path}.fixture.product.product_id")

    return {
        "product_id": product_id,
        "slug": product_slug,
        "title": title,
        "category": category,
        "market": market,
        "preview_status": preview_status,
        "publication_status": "NOT_AUTHORIZED",
        "price": price,
        "public_content": {
            "title": title,
            "description": "",
            "facts": [],
            "proof": [],
            "content_state": "IDENTITY_ONLY",
        },
        "routes": {
            "product_detail": f"/products/{product_slug}",
        },
        "operator_context": {
            "permission_gate": permission_gate,
            "decision_outcome": outcome,
            "methodology_present": methodology_present,
            "methodology_status": methodology_status,
            "methodology_operator_review_required": review_required,
            "product_fact_count": len(context["product_facts"]),
            "proof_available_count": len(context["proof_available"]),
        },
    }


def _validate_methodology_context(
    value: Any,
    path: str,
) -> dict[str, Any]:
    context = _require_mapping(value, path)
    if any(not isinstance(key, str) for key in context):
        raise StorefrontReadModelError(f"{path} keys must be strings")

    _require_exact_keys(
        context,
        required=frozenset(_REQUIRED_CONTEXT_FIELDS),
        allowed=_ALLOWED_CONTEXT_FIELDS,
        path=path,
    )

    return {
        "product_facts": _require_string_sequence(
            context.get("product_facts"),
            f"{path}.product_facts",
            allow_empty=False,
        ),
        "product_id": _require_nonempty_text(
            context.get("product_id"),
            f"{path}.product_id",
        ),
        "buyer_state": _require_nonempty_text(
            context.get("buyer_state"),
            f"{path}.buyer_state",
        ),
        "proof_available": _require_string_sequence(
            context.get("proof_available"),
            f"{path}.proof_available",
            allow_empty=True,
        ),
        "claim_risk": _require_nonempty_text(
            context.get("claim_risk"),
            f"{path}.claim_risk",
        ),
        "channel": _require_nonempty_text(
            context.get("channel"),
            f"{path}.channel",
        ),
        "margin_profile": _require_nonempty_text(
            context.get("margin_profile"),
            f"{path}.margin_profile",
        ),
        "category": _require_nonempty_text(
            context.get("category"),
            f"{path}.category",
        ),
        "candidate_output": _require_text(
            context.get("candidate_output", ""),
            f"{path}.candidate_output",
        ),
    }


def _validate_methodology(
    value: Any,
    path: str,
) -> tuple[bool, str, bool | None]:
    if value is None:
        return False, "missing", None

    methodology = _require_mapping(value, path)
    schema_version = _require_nonempty_text(
        methodology.get("schema_version"),
        f"{path}.schema_version",
    )
    if schema_version != METHODOLOGY_SCHEMA_VERSION:
        raise StorefrontReadModelError(
            f"{path}.schema_version must be "
            f"{METHODOLOGY_SCHEMA_VERSION}"
        )

    status = _require_nonempty_text(
        methodology.get("status"),
        f"{path}.status",
    )
    _require_nonempty_text(
        methodology.get("selected_rule_id"),
        f"{path}.selected_rule_id",
    )
    _require_nonempty_text(
        methodology.get("selected_framework"),
        f"{path}.selected_framework",
    )
    _require_nonempty_text(
        methodology.get("safe_output"),
        f"{path}.safe_output",
    )

    review_required = methodology.get("operator_review_required")
    if not isinstance(review_required, bool):
        raise StorefrontReadModelError(
            f"{path}.operator_review_required must be a boolean"
        )

    return True, status, review_required


def _build_price(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {
            "state": "MISSING",
            "currency": CURRENCY,
            "amount": None,
        }

    economics = _require_mapping(value, path)
    currency = _require_nonempty_text(
        economics.get("currency"),
        f"{path}.currency",
    )
    if currency != CURRENCY:
        raise StorefrontReadModelError(
            f"{path}.currency must be {CURRENCY}"
        )

    amount = _positive_money(
        economics.get("price_mxn"),
        f"{path}.price_mxn",
    )
    return {
        "state": "AVAILABLE",
        "currency": CURRENCY,
        "amount": format(amount, ".2f"),
    }


def _positive_money(value: Any, path: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise StorefrontReadModelError(
            f"{path} must be a positive finite decimal"
        )

    try:
        amount = (
            value
            if isinstance(value, Decimal)
            else Decimal(str(value).strip())
        )
    except (InvalidOperation, ValueError):
        raise StorefrontReadModelError(
            f"{path} must be a positive finite decimal"
        ) from None

    if not amount.is_finite() or amount <= Decimal("0"):
        raise StorefrontReadModelError(
            f"{path} must be a positive finite decimal"
        )

    quantized = amount.quantize(_MONEY, rounding=ROUND_HALF_UP)
    if quantized <= Decimal("0"):
        raise StorefrontReadModelError(
            f"{path} must be a positive finite decimal after cent rounding"
        )

    return quantized


def _preview_status(
    *,
    price_available: bool,
    methodology_present: bool,
) -> str:
    if price_available and methodology_present:
        return STATUS_READY
    if not price_available and not methodology_present:
        return STATUS_PRICE_AND_METHODOLOGY_MISSING
    if not price_available:
        return STATUS_PRICE_MISSING
    return STATUS_METHODOLOGY_MISSING


def _slug(value: str, path: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = _SLUG_RE.sub("-", normalized).strip("-")
    if not slug:
        raise StorefrontReadModelError(
            f"{path} must produce a non-empty route slug"
        )
    return slug


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    path: str,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    unexpected = sorted(keys - allowed)

    if missing:
        raise StorefrontReadModelError(
            f"{path}.missing_fields=" + ",".join(missing)
        )
    if unexpected:
        raise StorefrontReadModelError(
            f"{path}.unexpected_fields=" + ",".join(unexpected)
        )


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StorefrontReadModelError(f"{path} must be a mapping")
    return value


def _require_sequence(
    value: Any,
    path: str,
    *,
    allow_empty: bool,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise StorefrontReadModelError(f"{path} must be a sequence")

    materialized = tuple(value)
    if not allow_empty and not materialized:
        raise StorefrontReadModelError(
            f"{path} must contain at least one item"
        )
    return materialized


def _require_string_sequence(
    value: Any,
    path: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    materialized = _require_sequence(
        value,
        path,
        allow_empty=allow_empty,
    )
    result: list[str] = []

    for index, item in enumerate(materialized):
        text = _require_nonempty_text(item, f"{path}[{index}]")
        if _ABSOLUTE_URL_RE.search(text):
            raise StorefrontReadModelError(
                f"{path}[{index}] must not contain an absolute URL"
            )
        result.append(text)

    return tuple(result)


def _require_nonempty_text(value: Any, path: str) -> str:
    text = _require_text(value, path).strip()
    if not text:
        raise StorefrontReadModelError(
            f"{path} must be a non-empty string"
        )
    return text


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise StorefrontReadModelError(f"{path} must be a string")
    return value


__all__ = [
    "CURRENCY",
    "MODE",
    "SCHEMA_VERSION",
    "SOURCE_KIND",
    "STATUS_METHODOLOGY_MISSING",
    "STATUS_PRICE_AND_METHODOLOGY_MISSING",
    "STATUS_PRICE_MISSING",
    "STATUS_READY",
    "StorefrontReadModelError",
    "build_storefront_read_model",
    "serialize_storefront_read_model",
]

"""Operator-approved customer copy boundary for A8-R112I2.

This module validates deterministic copy explicitly supplied and approved by an
operator for local preview. It never generates copy, authorizes publication,
performs network access, writes externally, spends, fulfills, or calls Shopify,
Dropi, or Meta.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "a8-r112.customer_copy_approval.v1"
APPROVAL_STATUS = "APPROVED_FOR_LOCAL_PREVIEW"
APPROVAL_SCOPE = "LOCAL_PREVIEW_ONLY"
CONTENT_STATE = "OPERATOR_APPROVED_LOCAL_COPY"

_REQUIRED_ENVELOPE_FIELDS = frozenset({"copy", "approval"})
_REQUIRED_COPY_FIELDS = frozenset(
    {"product_id", "title", "description", "facts", "proof"}
)
_REQUIRED_APPROVAL_FIELDS = frozenset(
    {
        "status",
        "scope",
        "approved_copy_sha256",
        "publication_authorized",
        "external_writes_authorized",
    }
)

_ABSOLUTE_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_MAX_PRODUCT_ID_LENGTH = 200
_MAX_TITLE_LENGTH = 160
_MAX_DESCRIPTION_LENGTH = 2000
_MAX_LIST_ITEMS = 8
_MAX_LIST_ITEM_LENGTH = 400


class CustomerCopyApprovalError(ValueError):
    """Raised when customer copy approval must fail closed."""


def canonicalize_customer_copy(
    value: Any,
    *,
    expected_product_id: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize the exact operator-supplied copy payload."""

    copy_value = _require_mapping(value, "copy")
    _require_exact_keys(
        copy_value,
        required=_REQUIRED_COPY_FIELDS,
        allowed=_REQUIRED_COPY_FIELDS,
        path="copy",
    )

    product_id = _require_nonempty_text(
        copy_value.get("product_id"),
        "copy.product_id",
        max_length=_MAX_PRODUCT_ID_LENGTH,
    )
    if expected_product_id is not None and product_id != expected_product_id:
        raise CustomerCopyApprovalError(
            "copy.product_id must exactly match the storefront product"
        )

    return {
        "product_id": product_id,
        "title": _require_nonempty_text(
            copy_value.get("title"),
            "copy.title",
            max_length=_MAX_TITLE_LENGTH,
        ),
        "description": _require_nonempty_text(
            copy_value.get("description"),
            "copy.description",
            max_length=_MAX_DESCRIPTION_LENGTH,
        ),
        "facts": list(
            _require_string_sequence(copy_value.get("facts"), "copy.facts")
        ),
        "proof": list(
            _require_string_sequence(copy_value.get("proof"), "copy.proof")
        ),
    }


def serialize_customer_copy(value: Any) -> str:
    """Return canonical UTF-8 JSON text used for approval custody."""

    canonical = canonicalize_customer_copy(value)
    return (
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def customer_copy_sha256(value: Any) -> str:
    """Return SHA-256 of the canonical customer-copy bytes."""

    serialized = serialize_customer_copy(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_operator_approved_customer_copy(
    value: Any,
    *,
    expected_product_id: str,
) -> dict[str, Any]:
    """Validate approval custody and return the bounded public projection."""

    envelope = _require_mapping(value, "customer_copy_approval")
    _require_exact_keys(
        envelope,
        required=_REQUIRED_ENVELOPE_FIELDS,
        allowed=_REQUIRED_ENVELOPE_FIELDS,
        path="customer_copy_approval",
    )

    canonical_copy = canonicalize_customer_copy(
        envelope.get("copy"),
        expected_product_id=expected_product_id,
    )

    approval = _require_mapping(
        envelope.get("approval"),
        "customer_copy_approval.approval",
    )
    _require_exact_keys(
        approval,
        required=_REQUIRED_APPROVAL_FIELDS,
        allowed=_REQUIRED_APPROVAL_FIELDS,
        path="customer_copy_approval.approval",
    )

    status = _require_nonempty_text(
        approval.get("status"),
        "customer_copy_approval.approval.status",
        max_length=100,
    )
    if status != APPROVAL_STATUS:
        raise CustomerCopyApprovalError(
            f"approval.status must be {APPROVAL_STATUS}"
        )

    scope = _require_nonempty_text(
        approval.get("scope"),
        "customer_copy_approval.approval.scope",
        max_length=100,
    )
    if scope != APPROVAL_SCOPE:
        raise CustomerCopyApprovalError(
            f"approval.scope must be {APPROVAL_SCOPE}"
        )

    if approval.get("publication_authorized") is not False:
        raise CustomerCopyApprovalError(
            "approval.publication_authorized must be false"
        )

    if approval.get("external_writes_authorized") is not False:
        raise CustomerCopyApprovalError(
            "approval.external_writes_authorized must be false"
        )

    supplied_digest = _require_nonempty_text(
        approval.get("approved_copy_sha256"),
        "customer_copy_approval.approval.approved_copy_sha256",
        max_length=64,
    )
    if not _SHA256_RE.fullmatch(supplied_digest):
        raise CustomerCopyApprovalError(
            "approval.approved_copy_sha256 must be 64 lowercase "
            "hexadecimal characters"
        )

    expected_digest = customer_copy_sha256(canonical_copy)
    if not hmac.compare_digest(supplied_digest, expected_digest):
        raise CustomerCopyApprovalError(
            "approval.approved_copy_sha256 mismatch"
        )

    return {
        "title": canonical_copy["title"],
        "description": canonical_copy["description"],
        "facts": list(canonical_copy["facts"]),
        "proof": list(canonical_copy["proof"]),
        "content_state": CONTENT_STATE,
    }


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
        raise CustomerCopyApprovalError(
            f"{path}.missing_fields=" + ",".join(missing)
        )
    if unexpected:
        raise CustomerCopyApprovalError(
            f"{path}.unexpected_fields=" + ",".join(unexpected)
        )


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CustomerCopyApprovalError(f"{path} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise CustomerCopyApprovalError(f"{path} keys must be strings")
    return value


def _require_string_sequence(value: Any, path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CustomerCopyApprovalError(f"{path} must be a sequence")

    materialized = tuple(value)
    if len(materialized) > _MAX_LIST_ITEMS:
        raise CustomerCopyApprovalError(
            f"{path} must contain at most {_MAX_LIST_ITEMS} items"
        )

    result: list[str] = []
    for index, item in enumerate(materialized):
        result.append(
            _require_nonempty_text(
                item,
                f"{path}[{index}]",
                max_length=_MAX_LIST_ITEM_LENGTH,
            )
        )
    return tuple(result)


def _require_nonempty_text(
    value: Any,
    path: str,
    *,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise CustomerCopyApprovalError(f"{path} must be a string")

    text = value.strip()
    if not text:
        raise CustomerCopyApprovalError(
            f"{path} must be a non-empty string"
        )
    if len(text) > max_length:
        raise CustomerCopyApprovalError(
            f"{path} exceeds maximum length {max_length}"
        )
    if _ABSOLUTE_URL_RE.search(text):
        raise CustomerCopyApprovalError(
            f"{path} must not contain an absolute URL"
        )
    return text


__all__ = [
    "APPROVAL_SCOPE",
    "APPROVAL_STATUS",
    "CONTENT_STATE",
    "SCHEMA_VERSION",
    "CustomerCopyApprovalError",
    "canonicalize_customer_copy",
    "customer_copy_sha256",
    "serialize_customer_copy",
    "validate_operator_approved_customer_copy",
]

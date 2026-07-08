"""Pure adapters from sandbox product candidates into financial inputs.

The adapter layer is intentionally thin:
- no IO
- no live calls
- no scraping
- no external mutation
- no invented economics

It only converts explicit local candidate fields into ``FinancialInput``.
Missing required economics fail closed with ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from synapse.financial.evaluation import FinancialInput


_MISSING = object()

_PRODUCT_ID_ALIASES = ("product_id", "id")
_NAME_ALIASES = ("name", "title")
_PRICE_ALIASES = ("price",)
_LANDED_COST_ALIASES = ("landed_cost", "cost")
_ESTIMATED_CAC_ALIASES = ("estimated_cac",)
_EXPECTED_UNITS_ALIASES = ("expected_units",)


def candidate_to_financial_input(candidate: Mapping[str, Any] | object) -> FinancialInput:
    """Convert an explicit sandbox candidate into ``FinancialInput``.

    Accepted candidate shapes:
    - mapping/dict with explicit economics
    - object with explicit attributes

    Required aliases:
    - product_id or id
    - name or title
    - price
    - landed_cost or cost
    - estimated_cac

    Optional:
    - expected_units, default 1
    """

    product_id = _required_text(candidate, field_name="product_id", aliases=_PRODUCT_ID_ALIASES)
    name = _required_text(candidate, field_name="name", aliases=_NAME_ALIASES)
    price = _required_decimal(candidate, field_name="price", aliases=_PRICE_ALIASES)
    landed_cost = _required_decimal(
        candidate,
        field_name="landed_cost",
        aliases=_LANDED_COST_ALIASES,
    )
    estimated_cac = _required_decimal(
        candidate,
        field_name="estimated_cac",
        aliases=_ESTIMATED_CAC_ALIASES,
    )
    expected_units = _optional_positive_int(
        candidate,
        field_name="expected_units",
        aliases=_EXPECTED_UNITS_ALIASES,
        default=1,
    )

    return FinancialInput(
        product_id=product_id,
        name=name,
        price=price,
        landed_cost=landed_cost,
        estimated_cac=estimated_cac,
        expected_units=expected_units,
    )


def to_financial_input(candidate: Mapping[str, Any] | object) -> FinancialInput:
    """Alias for callers that prefer a short adapter name."""

    return candidate_to_financial_input(candidate)


def _required_text(
    source: Mapping[str, Any] | object,
    *,
    field_name: str,
    aliases: tuple[str, ...],
) -> str:
    value = _read_alias(source, aliases)
    if value is _MISSING:
        raise ValueError(_missing_message(field_name, aliases))

    if not isinstance(value, str):
        value = str(value)

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")

    return cleaned


def _required_decimal(
    source: Mapping[str, Any] | object,
    *,
    field_name: str,
    aliases: tuple[str, ...],
) -> Decimal:
    value = _read_alias(source, aliases)
    if value is _MISSING:
        raise ValueError(_missing_message(field_name, aliases))

    return _to_finite_decimal(value=value, field_name=field_name)


def _optional_positive_int(
    source: Mapping[str, Any] | object,
    *,
    field_name: str,
    aliases: tuple[str, ...],
    default: int,
) -> int:
    value = _read_alias(source, aliases)
    if value is _MISSING:
        return default

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")

    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None

    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise ValueError(f"{field_name} must be a positive integer")

    units = int(parsed)
    if units <= 0:
        raise ValueError(f"{field_name} must be a positive integer")

    return units


def _to_finite_decimal(*, value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite decimal")

    if isinstance(value, Decimal):
        parsed = value
    else:
        if value is None:
            raise ValueError(f"{field_name} must be a finite decimal")

        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{field_name} must be a finite decimal")

        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f"{field_name} must be a finite decimal") from None

    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")

    return parsed


def _read_alias(source: Mapping[str, Any] | object, aliases: tuple[str, ...]) -> Any:
    if isinstance(source, Mapping):
        for alias in aliases:
            if alias in source:
                return source[alias]
        return _MISSING

    for alias in aliases:
        if hasattr(source, alias):
            return getattr(source, alias)

    return _MISSING


def _missing_message(field_name: str, aliases: tuple[str, ...]) -> str:
    return f"missing required field: {field_name} (aliases: {', '.join(aliases)})"
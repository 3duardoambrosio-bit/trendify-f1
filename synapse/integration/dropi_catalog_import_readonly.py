"""Read-only local Dropi catalog import.

This module accepts operator-supplied local CSV catalog data and normalizes it
into deterministic records that can be inspected or adapted by SYNAPSE's
existing evaluation pipeline. It intentionally performs no live Dropi access
and no external mutation.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Mapping


_MXN = Decimal("0.01")

_REQUIRED_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "product_name"),
    "supplier_cost_mxn": ("supplier_cost_mxn", "cost_mxn", "price_mxn"),
    "shipping_cost_mxn": ("shipping_cost_mxn", "shipping_mxn"),
    "supplier": ("supplier", "supplier_name"),
    "stock": ("stock", "stock_qty", "inventory"),
    "sku": ("sku", "supplier_sku", "external_id"),
}

_OPTIONAL_ALIASES: dict[str, tuple[str, ...]] = {
    "category": ("category",),
    "image_url": ("image_url",),
    "product_url": ("product_url",),
    "description": ("description",),
    "weight_kg": ("weight_kg",),
    "supplier_rating": ("supplier_rating",),
    "shipping_days": ("shipping_days",),
    "brand": ("brand",),
}


class DropiCatalogImportError(ValueError):
    """Raised when local catalog data cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class DropiCatalogImportRecord:
    source_row_number: int
    title: str
    supplier: str
    sku: str
    supplier_cost_mxn: Decimal
    shipping_cost_mxn: Decimal
    stock: int
    category: str = ""
    image_url: str = ""
    product_url: str = ""
    description: str = ""
    brand: str = ""
    weight_kg: Decimal | None = None
    supplier_rating: Decimal | None = None
    shipping_days: int | None = None

    @property
    def landed_cost_mxn(self) -> Decimal:
        return _money(self.supplier_cost_mxn + self.shipping_cost_mxn, "landed_cost_mxn")

    def to_evaluation_seed(self) -> dict[str, str | int]:
        return {
            "title": self.title,
            "supplier": self.supplier,
            "sku": self.sku,
            "supplier_cost_mxn": str(self.supplier_cost_mxn),
            "shipping_cost_mxn": str(self.shipping_cost_mxn),
            "landed_cost_mxn": str(self.landed_cost_mxn),
            "stock": self.stock,
            "category": self.category,
            "brand": self.brand,
        }


def parse_dropi_catalog_csv(path: str | Path, *, encoding: str = "utf-8") -> tuple[DropiCatalogImportRecord, ...]:
    csv_path = Path(path)
    text = csv_path.read_text(encoding=encoding)
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise DropiCatalogImportError("csv_missing_header")

    records: list[DropiCatalogImportRecord] = []
    for index, row in enumerate(reader, start=2):
        records.append(normalize_dropi_catalog_row(row, source_row_number=index))

    return tuple(records)


def normalize_dropi_catalog_row(
    row: Mapping[str, object],
    *,
    source_row_number: int = 1,
) -> DropiCatalogImportRecord:
    normalized = {_normalize_key(str(k)): v for k, v in row.items()}

    title = _required_text(normalized, "title")
    supplier = _required_text(normalized, "supplier")
    sku = _required_text(normalized, "sku")
    supplier_cost = _money(_required_value(normalized, "supplier_cost_mxn"), "supplier_cost_mxn")
    shipping_cost = _money(_required_value(normalized, "shipping_cost_mxn"), "shipping_cost_mxn")
    stock = _stock(_required_value(normalized, "stock"))

    return DropiCatalogImportRecord(
        source_row_number=source_row_number,
        title=title,
        supplier=supplier,
        sku=sku,
        supplier_cost_mxn=supplier_cost,
        shipping_cost_mxn=shipping_cost,
        stock=stock,
        category=_optional_text(normalized, "category"),
        image_url=_optional_text(normalized, "image_url"),
        product_url=_optional_text(normalized, "product_url"),
        description=_optional_text(normalized, "description"),
        brand=_optional_text(normalized, "brand"),
        weight_kg=_optional_decimal(normalized, "weight_kg"),
        supplier_rating=_optional_decimal(normalized, "supplier_rating"),
        shipping_days=_optional_int(normalized, "shipping_days"),
    )


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def _required_value(row: Mapping[str, object], canonical: str) -> object:
    for alias in _REQUIRED_ALIASES[canonical]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    raise DropiCatalogImportError(f"missing_required_field:{canonical}")


def _optional_value(row: Mapping[str, object], canonical: str) -> object | None:
    for alias in _OPTIONAL_ALIASES[canonical]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def _required_text(row: Mapping[str, object], canonical: str) -> str:
    value = str(_required_value(row, canonical)).strip()
    if not value:
        raise DropiCatalogImportError(f"empty_required_field:{canonical}")
    return value


def _optional_text(row: Mapping[str, object], canonical: str) -> str:
    value = _optional_value(row, canonical)
    if value in (None, ""):
        return ""
    return str(value).strip()


def _money(value: object, field: str) -> Decimal:
    if isinstance(value, float):
        raise DropiCatalogImportError(f"float_money_not_allowed:{field}")
    if isinstance(value, bool):
        raise DropiCatalogImportError(f"invalid_money:{field}")

    if isinstance(value, Decimal):
        raw = value
    else:
        text = str(value).strip().replace("$", "").replace(",", "")
        if not text:
            raise DropiCatalogImportError(f"empty_money:{field}")
        try:
            raw = Decimal(text)
        except (InvalidOperation, ValueError) as exc:
            raise DropiCatalogImportError(f"invalid_money:{field}") from exc

    if raw < 0:
        raise DropiCatalogImportError(f"negative_money:{field}")

    return raw.quantize(_MXN, rounding=ROUND_HALF_UP)


def _stock(value: object) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise DropiCatalogImportError("invalid_stock")
    text = str(value).strip()
    if not text or "." in text:
        raise DropiCatalogImportError("invalid_stock")
    try:
        parsed = int(text)
    except ValueError as exc:
        raise DropiCatalogImportError("invalid_stock") from exc
    if parsed < 0:
        raise DropiCatalogImportError("negative_stock")
    return parsed


def _optional_decimal(row: Mapping[str, object], canonical: str) -> Decimal | None:
    value = _optional_value(row, canonical)
    if value in (None, ""):
        return None
    if isinstance(value, float):
        raise DropiCatalogImportError(f"float_decimal_not_allowed:{canonical}")
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise DropiCatalogImportError(f"invalid_decimal:{canonical}") from exc


def _optional_int(row: Mapping[str, object], canonical: str) -> int | None:
    value = _optional_value(row, canonical)
    if value in (None, ""):
        return None
    return _stock(value)
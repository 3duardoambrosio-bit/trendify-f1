from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


SEED_FALLBACK_PRICE = "29.99"
SEED_FALLBACK_COMPARE_AT = "49.99"
SEED_FALLBACK_TAG = "seed_placeholder_price"
SHOPIFY_DRAFT_CONTRACT_VERSION = "synapse.shopify.draft_export.v1"
SHOPIFY_DRAFT_SAFETY_TAGS: tuple[str, ...] = (
    "shopify_mode=draft_export",
    "published=false",
    "external_write=false",
    "shopify_api_called=false",
    "operator_publication_approval=false",
)
SHOPIFY_FIELDNAMES: tuple[str, ...] = (
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "SEO Title",
    "SEO Description",
    "Status",
)
_MONEY = Decimal("0.01")
_SHOPIFY_HANDLE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_SPREADSHEET_PREFIX_TRIM = " \t\r\n\v\f\ufeff\u200b"


class ShopifyDraftExportError(ValueError):
    """Raised when the strict local-only draft contract must fail closed."""


def _strict_csv_text(
    value: Any,
    field: str,
    *,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str):
        raise ShopifyDraftExportError(f"{field} must be a string")
    if not value and not allow_empty:
        raise ShopifyDraftExportError(
            f"{field} must be a non-empty string"
        )
    if value != value.strip():
        raise ShopifyDraftExportError(
            f"{field} must not contain surrounding whitespace"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ShopifyDraftExportError(
            f"{field} must not contain control characters"
        )
    formula_candidate = value.lstrip(_SPREADSHEET_PREFIX_TRIM)
    if formula_candidate.startswith(_FORMULA_PREFIXES):
        raise ShopifyDraftExportError(
            f"{field} must not contain a spreadsheet formula prefix"
        )
    return value


def _strict_nonempty_text(value: Any, field: str) -> str:
    return _strict_csv_text(value, field, allow_empty=False)


def _strict_money(value: Any, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ShopifyDraftExportError(
            f"{field} must be a positive finite decimal"
        )
    try:
        amount = (
            value
            if isinstance(value, Decimal)
            else Decimal(str(value).strip())
        )
        amount = amount.quantize(_MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ShopifyDraftExportError(
            f"{field} must be a positive finite decimal"
        ) from None
    if not amount.is_finite() or amount <= Decimal("0"):
        raise ShopifyDraftExportError(
            f"{field} must be a positive finite decimal"
        )
    return format(amount, ".2f")


def _strict_tags(tags: Sequence[str]) -> list[str]:
    if isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence):
        raise ShopifyDraftExportError("tags must be a sequence of strings")

    safety_by_key = {
        marker.split("=", 1)[0]: marker
        for marker in SHOPIFY_DRAFT_SAFETY_TAGS
    }
    normalized: list[str] = []
    seen: set[str] = set()

    for index, value in enumerate(tags):
        tag = _strict_csv_text(
            value,
            f"tags[{index}]",
            allow_empty=False,
        )
        if "," in tag:
            raise ShopifyDraftExportError(
                f"tags[{index}] must be one Shopify tag"
            )

        lowered = tag.lower()
        key = lowered.split("=", 1)[0].strip()
        safety_marker = safety_by_key.get(key)
        if safety_marker is not None and tag != safety_marker:
            raise ShopifyDraftExportError(
                f"tags[{index}] conflicts with safety marker {key}"
            )
        if lowered not in seen:
            seen.add(lowered)
            normalized.append(tag)

    for marker in SHOPIFY_DRAFT_SAFETY_TAGS:
        if marker not in seen:
            seen.add(marker)
            normalized.append(marker)
    return normalized


def build_shopify_draft_row(
    *,
    product_id: str,
    expected_product_id: str,
    title: str,
    price_mxn: Decimal | str | int | float,
    description: str = "",
    category: str = "",
    handle: str,
    vendor: str = "TrendifyHub",
    tags: Sequence[str] = (),
) -> dict[str, str]:
    """Build one strict, deterministic, local-only Shopify draft row.

    Unlike the legacy CLI path, this checkpoint helper has no seed behavior,
    missing-row defaults, publication switch, transport, client, or file IO.
    """

    resolved_product_id = _strict_nonempty_text(
        product_id,
        "product_id",
    )
    resolved_expected_product_id = _strict_nonempty_text(
        expected_product_id,
        "expected_product_id",
    )
    if resolved_product_id != resolved_expected_product_id:
        raise ShopifyDraftExportError(
            "product_id must exactly match expected_product_id"
        )

    resolved_title = _strict_nonempty_text(title, "title")
    resolved_handle = _strict_nonempty_text(handle, "handle")
    if not _SHOPIFY_HANDLE_RE.fullmatch(resolved_handle):
        raise ShopifyDraftExportError(
            "handle must contain lowercase ASCII letters, digits, and "
            "single hyphen separators only"
        )
    resolved_vendor = _strict_nonempty_text(vendor, "vendor")
    resolved_description = _strict_csv_text(
        description,
        "description",
        allow_empty=True,
    )
    resolved_category = _strict_csv_text(
        category,
        "category",
        allow_empty=True,
    )

    resolved_tags = _strict_tags(tags)
    escaped_description = html.escape(
        resolved_description,
        quote=True,
    )

    return {
        "Handle": resolved_handle,
        "Title": resolved_title,
        "Body (HTML)": escaped_description,
        "Vendor": resolved_vendor,
        "Type": resolved_category,
        "Tags": ", ".join(resolved_tags),
        "Published": "FALSE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": resolved_product_id,
        "Variant Grams": "",
        "Variant Inventory Tracker": "",
        "Variant Inventory Qty": "",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": _strict_money(price_mxn, "price_mxn"),
        "Variant Compare At Price": "",
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Variant Barcode": "",
        "Image Src": "",
        "Image Position": "",
        "Image Alt Text": "",
        "SEO Title": resolved_title,
        "SEO Description": resolved_description,
        "Status": "draft",
    }


def serialize_shopify_draft_export(
    row: Mapping[str, Any],
) -> str:
    """Serialize one strict draft row as deterministic UTF-8/LF-ready CSV."""

    if not isinstance(row, Mapping):
        raise ShopifyDraftExportError("row must be a mapping")

    expected = set(SHOPIFY_FIELDNAMES)
    actual = set(row)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise ShopifyDraftExportError(
            "row.missing_fields=" + ",".join(missing)
        )
    if unexpected:
        raise ShopifyDraftExportError(
            "row.unexpected_fields=" + ",".join(unexpected)
        )
    if any(not isinstance(row[field], str) for field in SHOPIFY_FIELDNAMES):
        raise ShopifyDraftExportError("all row values must be strings")
    for field in SHOPIFY_FIELDNAMES:
        _strict_csv_text(
            row[field],
            field,
            allow_empty=True,
        )

    if row["Published"] != "FALSE":
        raise ShopifyDraftExportError("Published must remain FALSE")
    if row["Status"] != "draft":
        raise ShopifyDraftExportError("Status must remain draft")
    if row["Variant Fulfillment Service"] != "manual":
        raise ShopifyDraftExportError(
            "Variant Fulfillment Service must remain manual"
        )
    if row["Variant Inventory Tracker"] or row["Variant Inventory Qty"]:
        raise ShopifyDraftExportError(
            "draft inventory fields must remain empty"
        )
    _strict_nonempty_text(row["Variant SKU"], "Variant SKU")
    _strict_nonempty_text(row["Title"], "Title")
    if not _SHOPIFY_HANDLE_RE.fullmatch(row["Handle"]):
        raise ShopifyDraftExportError("Handle must remain canonical")
    if row["Variant Price"] != _strict_money(
        row["Variant Price"],
        "Variant Price",
    ):
        raise ShopifyDraftExportError(
            "Variant Price must remain canonical"
        )
    if "<" in row["Body (HTML)"] or ">" in row["Body (HTML)"]:
        raise ShopifyDraftExportError(
            "Body (HTML) must contain escaped operator text only"
        )

    serialized_tag_values = tuple(
        tag.strip()
        for tag in row["Tags"].split(",")
        if tag.strip()
    )
    _strict_tags(serialized_tag_values)
    serialized_tags = {
        tag.lower()
        for tag in serialized_tag_values
    }
    missing_markers = [
        marker
        for marker in SHOPIFY_DRAFT_SAFETY_TAGS
        if marker not in serialized_tags
    ]
    if missing_markers:
        raise ShopifyDraftExportError(
            "row.missing_safety_markers=" + ",".join(missing_markers)
        )

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(SHOPIFY_FIELDNAMES),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(
        {
            field: row[field]
            for field in SHOPIFY_FIELDNAMES
        }
    )
    serialized = stream.getvalue()
    if "\r" in serialized:
        raise ShopifyDraftExportError(
            "serialized draft must contain LF line endings only"
        )
    return serialized


def _to_list(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v).strip() for v in x if str(v).strip()]
    s = str(x).strip()
    if not s:
        return []
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [str(v).strip() for v in obj if str(v).strip()]
        except Exception:
            pass
    parts = re.split(r"[,\|]\s*", s)
    return [p.strip() for p in parts if p.strip()]


def _pick_row(canonical_csv: Path, product_id: str) -> dict[str, str]:
    if not canonical_csv.exists():
        return {}
    with canonical_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("product_id") or "").strip() == product_id:
                return {k: (v or "").strip() for k, v in row.items()}
    return {}


def _merge_tags(existing: str, add: list[str]) -> str:
    raw = [x.strip() for x in (existing or "").split(",") if x.strip()]
    seen = {x.lower() for x in raw}
    out = raw[:]
    for t in add:
        tt = (t or "").strip()
        if not tt:
            continue
        if tt.lower() not in seen:
            seen.add(tt.lower())
            out.append(tt)
    return ", ".join(out)


def _write_csv_utf8_lf(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-dir", required=True, help="Kit directory (exports/<product_id>)")
    ap.add_argument("--canonical-csv", required=True, help="canonical_products.csv")
    ap.add_argument("--vendor", default="TrendifyHub")
    ap.add_argument("--status", default="draft")
    args = ap.parse_args(argv)

    kit_dir = Path(args.kit_dir)
    product_id = kit_dir.name

    canonical_csv = Path(args.canonical_csv)
    row = _pick_row(canonical_csv, product_id)

    title = row.get("title") or row.get("name") or product_id
    handle = row.get("handle") or f"{product_id}-product"
    tags_raw = row.get("tags") or ""
    tags = ", ".join(_to_list(tags_raw)) if tags_raw else ""

    # images (first image for Shopify import)
    img = (
        row.get("image_url")
        or row.get("image_src")
        or row.get("image")
        or row.get("thumbnail")
        or ""
    )
    if not img:
        imgs = _to_list(row.get("images") or row.get("image_urls") or "")
        img = imgs[0] if imgs else ""

    # pricing
    price = row.get("price") or row.get("sale_price") or ""
    compare_at = row.get("compare_at_price") or row.get("original_price") or row.get("msrp") or ""

    # seed-only fallback (keeps real products clean)
    used_seed_price = False
    if product_id == "seed" and (not price or price.strip() == ""):
        price = SEED_FALLBACK_PRICE
        if not compare_at:
            compare_at = SEED_FALLBACK_COMPARE_AT
        used_seed_price = True
        tags = _merge_tags(tags, [SEED_FALLBACK_TAG])

    # SEO
    seo_title = row.get("seo_title") or title
    seo_desc = row.get("seo_description") or (row.get("description") or row.get("body") or "")

    fieldnames = list(SHOPIFY_FIELDNAMES)

    out_csv = kit_dir / "shopify" / "shopify_products.csv"

    base = {
        "Handle": handle,
        "Title": title,
        "Body (HTML)": "",
        "Vendor": (row.get("vendor") or "").strip() or args.vendor,
        "Type": (row.get("type") or row.get("category") or "").strip(),
        "Tags": tags,
        "Published": "FALSE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": row.get("sku") or "",
        "Variant Grams": row.get("grams") or "",
        "Variant Inventory Tracker": "",
        "Variant Inventory Qty": row.get("inventory_qty") or row.get("stock") or row.get("inventory") or "",
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": price,
        "Variant Compare At Price": compare_at,
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Variant Barcode": row.get("barcode") or "",
        "Image Src": img,
        "Image Position": "1" if img else "",
        "Image Alt Text": title if img else "",
        "SEO Title": seo_title,
        "SEO Description": seo_desc,
        "Status": args.status,
    }

    _write_csv_utf8_lf(out_csv, fieldnames, [base])

    print("shopify_export_from_canonical: OK")
    print(f"- csv: {out_csv}")
    print(f"- product_id: {product_id}")
    print(f"- has_image: {bool(img)}")
    print(f"- has_price: {bool(price)}")
    print(f"- seed_price_fallback: {used_seed_price}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

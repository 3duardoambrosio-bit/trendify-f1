# synapse/shopify/shopify_import.py
"""
Shopify Import Generator (CSV) para SYNAPSE.

Objetivo:
- Generar CSV "excel-safe" (utf-8-sig) para importar productos a Shopify.
- Sin API por ahora: esto es F1 para operar ya sin fricción.

Notas:
- Shopify soporta muchas columnas; aquí damos un set "mínimo serio" + extensible.
- NO asumimos imágenes locales: permitimos image URLs.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, asdict, field
from typing import Dict, Iterable, List, Optional


SHOPIFY_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
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
    "Image Src",
    "Image Position",
    "SEO Title",
    "SEO Description",
    "Status",
]


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in [" ", "-", "_"]:
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "product"


@dataclass(frozen=True)
class ShopifyProductInput:
    product_id: str
    title: str
    price_mxn: float
    vendor: str = "TrendifyHub"
    product_type: str = "General"
    category: str = "Electronics"
    tags: List[str] = field(default_factory=list)
    body_html: str = ""
    compare_at_mxn: float = 0.0
    sku: str = ""
    inventory_qty: int = 0
    image_urls: List[str] = field(default_factory=list)
    seo_title: str = ""
    seo_description: str = ""


def generate_shopify_csv(
    products: Iterable[ShopifyProductInput],
    out_path: str,
    *,
    encoding: str = "utf-8-sig",
) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with open(out_path, "w", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=SHOPIFY_COLUMNS)
        w.writeheader()

        for p in products:
            handle = _slug(p.title) + "-" + str(p.product_id).strip()

            base = {
                "Handle": handle,
                "Title": p.title,
                "Body (HTML)": p.body_html or "",
                "Vendor": p.vendor,
                "Product Category": p.category,
                "Type": p.product_type,
                "Tags": ", ".join([t.strip() for t in p.tags if t.strip()]),
                "Published": "TRUE",
                "Option1 Name": "Title",
                "Option1 Value": "Default Title",
                "Variant SKU": p.sku or f"SKU-{p.product_id}",
                "Variant Grams": "0",
                "Variant Inventory Tracker": "shopify",
                "Variant Inventory Qty": str(int(p.inventory_qty)),
                "Variant Inventory Policy": "deny",
                "Variant Fulfillment Service": "manual",
                "Variant Price": f"{float(p.price_mxn):.2f}",
                "Variant Compare At Price": f"{float(p.compare_at_mxn):.2f}" if p.compare_at_mxn else "",
                "Variant Requires Shipping": "TRUE",
                "Variant Taxable": "TRUE",
                "SEO Title": p.seo_title or p.title,
                "SEO Description": p.seo_description or "",
                "Status": "active",
            }

            if not p.image_urls:
                w.writerow({**base, "Image Src": "", "Image Position": ""})
                continue

            pos = 1
            for img in p.image_urls:
                w.writerow({**base, "Image Src": img, "Image Position": str(pos)})
                pos += 1

    return out_path

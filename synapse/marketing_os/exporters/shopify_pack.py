from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _as_handle(s: str) -> str:
    s2 = "".join([c.lower() if c.isalnum() else "-" for c in s.strip()])
    while "--" in s2:
        s2 = s2.replace("--", "-")
    return s2.strip("-") or "product"


def write_shopify_products_csv(
    out_dir: Path,
    *,
    product: dict[str, Any],
    tags: list[str] | None = None,
    vendor: str = "TrendifyHub",
    status: str = "draft",
) -> Path:
    """
    Writes a minimal Shopify products CSV (UTF-8-SIG to play nice with Excel on Windows).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "shopify_products.csv"

    title = str(product.get("title") or product.get("name") or product.get("product_name") or "Product")
    body = str(product.get("description") or product.get("desc") or "")
    handle = _as_handle(str(product.get("handle") or title))
    tags_s = ", ".join(tags or [])

    fieldnames = [
        "Handle",
        "Title",
        "Body (HTML)",
        "Vendor",
        "Tags",
        "Status",
    ]

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(
            {
                "Handle": handle,
                "Title": title,
                "Body (HTML)": body,
                "Vendor": vendor,
                "Tags": tags_s,
                "Status": status,
            }
        )
    return out

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any


def _as_handle(s: str) -> str:
    """
    Shopify handle:
    - ASCII lowercase
    - [a-z0-9-]
    - no accents
    - no double hyphens
    """
    s = (s or "").strip()
    if not s:
        return "product"

    # Strip accents -> ASCII
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")

    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")

    # Shopify handle practical limit (keep it sane)
    if len(s) > 200:
        s = s[:200].rstrip("-")

    return s or "product"


def write_shopify_products_csv(
    out_dir: Path,
    *,
    product: dict[str, Any],
    tags: list[str] | None = None,
    vendor: str = "TrendifyHub",
    status: str = "draft",
) -> Path:
    """
    Writes a minimal Shopify products CSV:
    - UTF-8 (NO BOM)
    - LF only
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

    # Force LF + UTF-8 no BOM
    with out.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
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

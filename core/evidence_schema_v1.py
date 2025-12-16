from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EvidenceV1:
    product_id: str
    supplier_url: str
    price_usd: float
    shipping_usd_to_mexico: float
    rating: float
    reviews: int
    sold: int
    recommended_variant: str

    @staticmethod
    def from_dict(product_id: str, d: Dict[str, Any]) -> "EvidenceV1":
        url = str(d.get("supplier_url", "") or "")
        if not url:
            raise ValueError("supplier_url required")

        return EvidenceV1(
            product_id=product_id,
            supplier_url=url,
            price_usd=float(d.get("price_usd", 0.0) or 0.0),
            shipping_usd_to_mexico=float(d.get("shipping_usd_to_mexico", d.get("shipping_usd", 0.0)) or 0.0),
            rating=float(d.get("rating", 0.0) or 0.0),
            reviews=int(d.get("reviews", 0) or 0),
            sold=int(d.get("sold", 0) or 0),
            recommended_variant=str(d.get("recommended_variant", "") or ""),
        )
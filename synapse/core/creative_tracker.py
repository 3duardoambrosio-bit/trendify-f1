from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from synapse.core.models import ALLOWED_VARIANT_STATUS, ComparisonReport, CreativeVariant, utc_now


def _variant_to_dict(item: CreativeVariant) -> dict:
    return {
        "variant_id": item.variant_id,
        "product_id": item.product_id,
        "created_at": item.created_at.isoformat(),
        "angle": item.angle,
        "hook": item.hook,
        "format": item.format,
        "asset_path": item.asset_path,
        "status": item.status,
        "spend_total": str(item.spend_total),
        "impressions": item.impressions,
        "clicks": item.clicks,
        "conversions": item.conversions,
        "revenue": str(item.revenue),
        "roas": None if item.roas is None else str(item.roas),
        "ctr": None if item.ctr is None else str(item.ctr),
        "cpa": None if item.cpa is None else str(item.cpa),
        "decision_ids": list(item.decision_ids),
        "kill_reason": item.kill_reason,
        "kill_decision_id": item.kill_decision_id,
    }


def _variant_from_dict(data: dict) -> CreativeVariant:
    return CreativeVariant(
        variant_id=data["variant_id"],
        product_id=data["product_id"],
        created_at=datetime.fromisoformat(data["created_at"]),
        angle=data["angle"],
        hook=data["hook"],
        format=data["format"],
        asset_path=data["asset_path"],
        status=data.get("status", "untested"),
        spend_total=Decimal(data.get("spend_total", "0")),
        impressions=int(data.get("impressions", 0)),
        clicks=int(data.get("clicks", 0)),
        conversions=int(data.get("conversions", 0)),
        revenue=Decimal(data.get("revenue", "0")),
        roas=None if data.get("roas") is None else Decimal(data["roas"]),
        ctr=None if data.get("ctr") is None else Decimal(data["ctr"]),
        cpa=None if data.get("cpa") is None else Decimal(data["cpa"]),
        decision_ids=tuple(data.get("decision_ids", [])),
        kill_reason=data.get("kill_reason"),
        kill_decision_id=data.get("kill_decision_id"),
    )


class CreativeTracker:
    def __init__(self, path: str = "data/creatives/variants.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, CreativeVariant] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                item = _variant_from_dict(json.loads(line))
                self._items[item.variant_id] = item

    def _flush(self) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for item in self._items.values():
                fh.write(json.dumps(_variant_to_dict(item), ensure_ascii=False) + "\n")

    def register(self, product_id: str, angle: str, hook: str, format: str, asset_path: str) -> CreativeVariant:
        variant = CreativeVariant(
            variant_id=str(uuid.uuid4()),
            product_id=product_id,
            created_at=utc_now(),
            angle=angle,
            hook=hook,
            format=format,
            asset_path=asset_path,
        )
        self._items[variant.variant_id] = variant
        self._flush()
        return variant

    def update_metrics(
        self,
        variant_id: str,
        spend: Decimal,
        impressions: int,
        clicks: int,
        conversions: int,
        revenue: Decimal,
    ) -> CreativeVariant:
        current = self._items[variant_id]
        new_spend = current.spend_total + Decimal(str(spend))
        new_impressions = current.impressions + int(impressions)
        new_clicks = current.clicks + int(clicks)
        new_conversions = current.conversions + int(conversions)
        new_revenue = current.revenue + Decimal(str(revenue))
        new_roas = None if new_spend == 0 else (new_revenue / new_spend)
        new_ctr = None if new_impressions == 0 else (Decimal(new_clicks) / Decimal(new_impressions))
        new_cpa = None if new_conversions == 0 else (new_spend / Decimal(new_conversions))
        updated = replace(
            current,
            spend_total=new_spend,
            impressions=new_impressions,
            clicks=new_clicks,
            conversions=new_conversions,
            revenue=new_revenue,
            roas=new_roas,
            ctr=new_ctr,
            cpa=new_cpa,
        )
        self._items[variant_id] = updated
        self._flush()
        return updated

    def change_status(
        self,
        variant_id: str,
        new_status: str,
        reason: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> CreativeVariant:
        if new_status not in ALLOWED_VARIANT_STATUS:
            raise ValueError(f"invalid status: {new_status}")
        current = self._items[variant_id]
        decision_ids = tuple(list(current.decision_ids) + ([] if decision_id is None else [decision_id]))
        updated = replace(
            current,
            status=new_status,
            decision_ids=decision_ids,
            kill_reason=reason if new_status == "killed" else current.kill_reason,
            kill_decision_id=decision_id if new_status == "killed" else current.kill_decision_id,
        )
        self._items[variant_id] = updated
        self._flush()
        return updated

    def get_active(self, product_id: str) -> list[CreativeVariant]:
        return [
            item for item in self._items.values()
            if item.product_id == product_id and item.status == "active"
        ]

    def get_all(self, product_id: Optional[str] = None) -> list[CreativeVariant]:
        items = list(self._items.values())
        if product_id is None:
            return items
        return [item for item in items if item.product_id == product_id]

    def compare(self, product_id: str) -> ComparisonReport:
        variants = [item for item in self._items.values() if item.product_id == product_id]
        ranked = tuple(sorted(
            variants,
            key=lambda item: (Decimal("-1") if item.roas is None else item.roas),
            reverse=True,
        ))
        return ComparisonReport(
            product_id=product_id,
            variants=ranked,
            best_variant_id=None if not ranked else ranked[0].variant_id,
            worst_variant_id=None if not ranked else ranked[-1].variant_id,
        )
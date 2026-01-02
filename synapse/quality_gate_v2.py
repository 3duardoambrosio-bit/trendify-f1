from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

def _norm(s: str) -> str:
    return (s or "").strip().lower()

@dataclass(frozen=True)
class GateCheck:
    code: str
    level: str          # "HARD" | "SOFT"
    passed: bool
    detail: str

@dataclass(frozen=True)
class GateResult:
    allowed: bool
    blocked: bool
    true_margin: Optional[float]
    checks: List[GateCheck]

    @property
    def warnings(self) -> List[GateCheck]:
        return [c for c in self.checks if (c.level == "SOFT" and not c.passed)]

    @property
    def blocks(self) -> List[GateCheck]:
        return [c for c in self.checks if (c.level == "HARD" and not c.passed)]

@dataclass(frozen=True)
class QualityConfig:
    # Core econ
    min_true_margin: float = 0.35
    fee_rate: float = 0.04              # payment/platform blended
    return_rate: float = 0.08           # expected refunds/returns impact
    fixed_per_order: float = 0.0        # packing/ops per order estimate
    shipping_estimate: float = 0.0      # simple baseline; can be upgraded later

    # Content
    min_images: int = 1
    banned_brands: Tuple[str, ...] = (
        "apple","airpods","nike","adidas","puma","samsung","sony","bose","jbl","xiaomi","huawei"
    )
    banned_claims: Tuple[str, ...] = (
        "cura","garantizado","100% efectivo","milagro","adelgaza","baja de peso","sin esfuerzo",
        "antes y después","anti-cáncer","diabetes","hipertensión","alzheimer"
    )

class QualityGateV2:
    """
    Quality Gate "F1-lite" (pero serio):
    - ALL-IN margin
    - Brand/IP risk (keyword-based)
    - Compliance claims (keyword-based)
    - Image minimum
    - Output auditable (checks list)
    """
    def __init__(self, cfg: QualityConfig = QualityConfig()) -> None:
        self.cfg = cfg
        self._brand_re = re.compile(r"\b(" + "|".join([re.escape(b) for b in cfg.banned_brands]) + r")\b", re.I)
        # claims pueden venir con espacios; matching flexible
        self._claims = [c.lower() for c in cfg.banned_claims]

    def _get(self, p: Dict[str, Any], *keys: str) -> Any:
        for k in keys:
            if k in p and p[k] is not None:
                return p[k]
        return None

    def true_margin(self, p: Dict[str, Any]) -> Optional[float]:
        sp = self._get(p, "suggested_price","price","sp")
        cost = self._get(p, "sale_price","cost","provider_price")
        if sp is None or cost is None:
            return None
        try:
            revenue = float(sp)
            base_cost = float(cost)
        except Exception:
            return None
        if revenue <= 0:
            return None

        fees = revenue * float(self.cfg.fee_rate)
        returns = revenue * float(self.cfg.return_rate)
        shipping = float(self.cfg.shipping_estimate)
        fixed = float(self.cfg.fixed_per_order)

        total_cost = base_cost + fees + returns + shipping + fixed
        return (revenue - total_cost) / revenue

    def check(self, p: Dict[str, Any]) -> GateResult:
        name = str(self._get(p, "name","title") or "")
        desc = str(self._get(p, "description","desc") or "")
        imgs = self._get(p, "imgs","images_count")
        if imgs is None:
            # infer from images array if present
            images = self._get(p, "images","gallery")
            if isinstance(images, list):
                imgs = len(images)
            else:
                imgs = 0
        try:
            imgs_i = int(imgs)
        except Exception:
            imgs_i = 0

        tm = self.true_margin(p)

        checks: List[GateCheck] = []

        # HARD: images
        checks.append(GateCheck(
            code="min_images",
            level="HARD",
            passed=(imgs_i >= int(self.cfg.min_images)),
            detail=f"imgs={imgs_i} min={self.cfg.min_images}"
        ))

        # HARD: brand/IP
        brand_hit = self._brand_re.search(_norm(name) + " " + _norm(desc)) is not None
        checks.append(GateCheck(
            code="brand_ip_risk",
            level="HARD",
            passed=(not brand_hit),
            detail="brand keyword detected" if brand_hit else "ok"
        ))

        # HARD: compliance claims
        text = _norm(name) + " " + _norm(desc)
        claim_hit = any(c in text for c in self._claims)
        checks.append(GateCheck(
            code="compliance_claims",
            level="HARD",
            passed=(not claim_hit),
            detail="forbidden claim detected" if claim_hit else "ok"
        ))

        # HARD: all-in margin
        if tm is None:
            checks.append(GateCheck(
                code="true_margin_known",
                level="SOFT",
                passed=False,
                detail="missing price/cost -> cannot compute true margin"
            ))
        else:
            checks.append(GateCheck(
                code="min_true_margin",
                level="HARD",
                passed=(tm >= float(self.cfg.min_true_margin)),
                detail=f"true_margin={tm:.3f} min={self.cfg.min_true_margin}"
            ))

        blocked = any((c.level == "HARD" and not c.passed) for c in checks)
        allowed = not blocked

        return GateResult(
            allowed=allowed,
            blocked=blocked,
            true_margin=tm,
            checks=checks
        )

    def explain(self, res: GateResult) -> Dict[str, Any]:
        return {
            "allowed": res.allowed,
            "blocked": res.blocked,
            "true_margin": res.true_margin,
            "blocks": [asdict(c) for c in res.blocks],
            "warnings": [asdict(c) for c in res.warnings],
        }

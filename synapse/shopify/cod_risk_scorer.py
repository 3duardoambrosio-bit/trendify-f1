# V3GAP:cod_risk_scoring

# V3GAP:A-04_cod_blacklist

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import deal

D0 = Decimal("0")
D1 = Decimal("1")

__MARKER__ = "SESSION_S11_cod_risk_scoring"


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _norm_token(value: str | None) -> str:
    return str(value or "").strip().lower()


def _norm_phone(value: str | None) -> str:
    raw = str(value or "")
    return "".join(ch for ch in raw if ch.isdigit())


@dataclass(frozen=True)
class CodRiskConfig:
    max_cod_amount_mxn: Decimal = Decimal("2500")
    high_risk_threshold: Decimal = Decimal("0.70")
    medium_risk_threshold: Decimal = Decimal("0.40")
    rural_risk_boost: Decimal = Decimal("0.20")
    previous_rejection_boost: Decimal = Decimal("0.15")
    blacklist_customer_ids: tuple[str, ...] = ()
    blacklist_emails: tuple[str, ...] = ()
    blacklist_phones: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodRiskResult:
    score: Decimal
    risk_level: str  # low/medium/high
    cod_allowed: bool
    reason: str


class CodRiskScorer:
    def __init__(self, config: CodRiskConfig | None = None):
        self._cfg = config or CodRiskConfig()

    def _blacklist_reason(
        self,
        *,
        customer_id: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> str | None:
        cid = _norm_token(customer_id)
        email = _norm_token(customer_email)
        phone = _norm_phone(customer_phone)

        blocked_ids = {_norm_token(v) for v in self._cfg.blacklist_customer_ids}
        blocked_emails = {_norm_token(v) for v in self._cfg.blacklist_emails}
        blocked_phones = {_norm_phone(v) for v in self._cfg.blacklist_phones}

        if cid and cid in blocked_ids:
            return "blacklisted_customer_id"
        if email and email in blocked_emails:
            return "blacklisted_email"
        if phone and phone in blocked_phones:
            return "blacklisted_phone"
        return None

    @deal.pre(
        lambda self, amount_mxn, postal_code, is_rural, previous_rejections, **kwargs:
        _d(amount_mxn) >= D0
    )
    @deal.pre(
        lambda self, amount_mxn, postal_code, is_rural, previous_rejections, **kwargs:
        int(previous_rejections) >= 0
    )
    @deal.pre(
        lambda self, amount_mxn, postal_code, is_rural, previous_rejections, **kwargs:
        str(postal_code or "").strip() != ""
    )
    @deal.post(lambda result: result.risk_level in ("low", "medium", "high"))
    @deal.post(lambda result: D0 <= result.score <= D1)
    def score_order(
        self,
        amount_mxn: Decimal,
        postal_code: str,
        is_rural: bool,
        previous_rejections: int,
        *,
        customer_id: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> CodRiskResult:
        blocked_reason = self._blacklist_reason(
            customer_id=customer_id,
            customer_email=customer_email,
            customer_phone=customer_phone,
        )
        if blocked_reason is not None:
            return CodRiskResult(
                score=D1,
                risk_level="high",
                cod_allowed=False,
                reason=blocked_reason,
            )

        if amount_mxn > self._cfg.max_cod_amount_mxn:
            return CodRiskResult(
                score=D1,
                risk_level="high",
                cod_allowed=False,
                reason="amount_exceeds_max_cod_amount",
            )

        denom = self._cfg.max_cod_amount_mxn
        if denom <= D0:
            return CodRiskResult(
                score=D1,
                risk_level="high",
                cod_allowed=False,
                reason="invalid_config_max_cod_amount",
            )

        score = _d(amount_mxn) / denom

        if is_rural:
            score += _d(self._cfg.rural_risk_boost)

        score += _d(previous_rejections) * _d(self._cfg.previous_rejection_boost)

        if score > D1:
            score = D1

        if score > self._cfg.high_risk_threshold:
            return CodRiskResult(
                score=score,
                risk_level="high",
                cod_allowed=False,
                reason="score_above_high_risk_threshold",
            )

        if score > self._cfg.medium_risk_threshold:
            return CodRiskResult(
                score=score,
                risk_level="medium",
                cod_allowed=True,
                reason="score_above_medium_risk_threshold",
            )

        return CodRiskResult(
            score=score,
            risk_level="low",
            cod_allowed=True,
            reason="score_below_medium_risk_threshold",
        )

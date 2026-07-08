"""Sandbox spend and mutation guard for SYNAPSE.

This module is intentionally isolated and pure. It does not call external
services, does not read process environment, does not perform disk access,
and does not mutate runtime state.

The guard answers one question: is this requested action safe under the
current sandbox authorization envelope?
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any


MONEY_QUANT = Decimal("0.01")

LIVE_CHANNEL_KEYWORDS: tuple[str, ...] = (
    "live",
    "prod",
    "production",
    "shopify",
    "dropi",
    "meta",
    "facebook",
    "ads",
)


class GuardDecision(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class GuardIntent(Enum):
    READ = "READ"
    EVALUATE = "EVALUATE"
    SIMULATE = "SIMULATE"
    SPEND = "SPEND"
    WRITE = "WRITE"
    MUTATE = "MUTATE"


class GuardReasonCode(Enum):
    SANDBOX_ACTION_ALLOWED = "SANDBOX_ACTION_ALLOWED"
    AUTHORIZED_ACTION_ALLOWED = "AUTHORIZED_ACTION_ALLOWED"
    BLOCKED_SPEND_REQUIRES_AUTHORIZATION = "BLOCKED_SPEND_REQUIRES_AUTHORIZATION"
    BLOCKED_SPEND_LIMIT_EXCEEDED = "BLOCKED_SPEND_LIMIT_EXCEEDED"
    BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION = (
        "BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION"
    )
    BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION = (
        "BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION"
    )


@dataclass(frozen=True)
class SpendAuthorization:
    spend_allowed: bool = False
    mutation_allowed: bool = False
    live_channel_allowed: bool = False
    max_spend: Decimal | int | str = Decimal("0")

    def __post_init__(self) -> None:
        _require_bool(self.spend_allowed, "spend_allowed")
        _require_bool(self.mutation_allowed, "mutation_allowed")
        _require_bool(self.live_channel_allowed, "live_channel_allowed")
        object.__setattr__(
            self,
            "max_spend",
            _coerce_non_negative_money(self.max_spend, "max_spend"),
        )


@dataclass(frozen=True)
class SpendGuardRequest:
    intent: GuardIntent | str
    channel: str = "sandbox"
    spend_amount: Decimal | int | str = Decimal("0")
    external_mutation: bool = False
    authorization: SpendAuthorization | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent", _coerce_intent(self.intent))
        object.__setattr__(self, "channel", _coerce_channel(self.channel))
        object.__setattr__(
            self,
            "spend_amount",
            _coerce_non_negative_money(self.spend_amount, "spend_amount"),
        )

        _require_bool(self.external_mutation, "external_mutation")

        if self.authorization is None:
            object.__setattr__(self, "authorization", SpendAuthorization())
        elif not isinstance(self.authorization, SpendAuthorization):
            raise ValueError("authorization must be SpendAuthorization or None")


@dataclass(frozen=True)
class SpendGuardResult:
    decision: GuardDecision
    reason_codes: tuple[str, ...]
    spend_amount: Decimal
    max_spend: Decimal
    channel: str

    @property
    def allowed(self) -> bool:
        return self.decision is GuardDecision.ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision is GuardDecision.BLOCK


def evaluate_spend_guard(request: SpendGuardRequest) -> SpendGuardResult:
    if not isinstance(request, SpendGuardRequest):
        raise ValueError("request must be SpendGuardRequest")

    authorization = request.authorization
    assert authorization is not None

    reasons: list[GuardReasonCode] = []

    spend_requested = (
        request.intent is GuardIntent.SPEND
        or request.spend_amount > Decimal("0.00")
    )
    mutation_requested = (
        request.external_mutation
        or request.intent in (GuardIntent.WRITE, GuardIntent.MUTATE)
    )
    live_channel_requested = _channel_requires_live_authorization(request.channel)

    if live_channel_requested and not authorization.live_channel_allowed:
        reasons.append(GuardReasonCode.BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION)

    if spend_requested:
        if not authorization.spend_allowed:
            reasons.append(GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION)
        elif request.spend_amount > authorization.max_spend:
            reasons.append(GuardReasonCode.BLOCKED_SPEND_LIMIT_EXCEEDED)

    if mutation_requested and not authorization.mutation_allowed:
        reasons.append(
            GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION
        )

    if reasons:
        return SpendGuardResult(
            decision=GuardDecision.BLOCK,
            reason_codes=tuple(reason.value for reason in _dedupe_reason_codes(reasons)),
            spend_amount=request.spend_amount,
            max_spend=authorization.max_spend,
            channel=request.channel,
        )

    if spend_requested or mutation_requested or live_channel_requested:
        allow_reason = GuardReasonCode.AUTHORIZED_ACTION_ALLOWED
    else:
        allow_reason = GuardReasonCode.SANDBOX_ACTION_ALLOWED

    return SpendGuardResult(
        decision=GuardDecision.ALLOW,
        reason_codes=(allow_reason.value,),
        spend_amount=request.spend_amount,
        max_spend=authorization.max_spend,
        channel=request.channel,
    )


def assert_spend_guard_allows(request: SpendGuardRequest) -> SpendGuardResult:
    result = evaluate_spend_guard(request)
    if result.blocked:
        raise PermissionError(",".join(result.reason_codes))
    return result


def _dedupe_reason_codes(
    reason_codes: list[GuardReasonCode],
) -> tuple[GuardReasonCode, ...]:
    seen: set[GuardReasonCode] = set()
    deduped: list[GuardReasonCode] = []

    for reason_code in reason_codes:
        if reason_code not in seen:
            seen.add(reason_code)
            deduped.append(reason_code)

    return tuple(deduped)


def _coerce_intent(value: GuardIntent | str) -> GuardIntent:
    if isinstance(value, GuardIntent):
        return value

    if not isinstance(value, str):
        raise ValueError("intent must be GuardIntent or string")

    text = value.strip().upper()
    if not text:
        raise ValueError("intent must not be empty")

    try:
        return GuardIntent(text)
    except ValueError:
        raise ValueError(f"unsupported guard intent: {value}") from None


def _coerce_channel(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("channel must be string")

    text = value.strip()
    if not text:
        raise ValueError("channel must not be empty")

    return text


def _coerce_non_negative_money(value: Any, field_name: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative decimal")

    try:
        decimal_value = (
            value
            if isinstance(value, Decimal)
            else Decimal(str(value).strip())
        )
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a finite non-negative decimal") from None

    if not decimal_value.is_finite() or decimal_value < Decimal("0"):
        raise ValueError(f"{field_name} must be a finite non-negative decimal")

    return decimal_value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be bool")


def _channel_requires_live_authorization(channel: str) -> bool:
    normalized = channel.casefold()
    return any(keyword in normalized for keyword in LIVE_CHANNEL_KEYWORDS)
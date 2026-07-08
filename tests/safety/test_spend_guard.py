from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

import synapse.safety as safety
import synapse.safety.spend_guard as spend_guard
from synapse.safety import (
    GuardDecision,
    GuardIntent,
    GuardReasonCode,
    SpendAuthorization,
    SpendGuardRequest,
    assert_spend_guard_allows,
    evaluate_spend_guard,
)


def test_allows_sandbox_evaluation_without_authorization():
    result = evaluate_spend_guard(
        SpendGuardRequest(intent=GuardIntent.EVALUATE, channel="sandbox")
    )

    assert result.decision is GuardDecision.ALLOW
    assert result.reason_codes == (GuardReasonCode.SANDBOX_ACTION_ALLOWED.value,)
    assert result.allowed is True
    assert result.blocked is False


def test_allows_sandbox_read_without_authorization():
    result = evaluate_spend_guard(SpendGuardRequest(intent="read", channel="sandbox"))

    assert result.decision is GuardDecision.ALLOW
    assert result.reason_codes == (GuardReasonCode.SANDBOX_ACTION_ALLOWED.value,)


def test_blocks_spend_intent_without_authorization_even_when_amount_is_zero():
    result = evaluate_spend_guard(
        SpendGuardRequest(intent=GuardIntent.SPEND, spend_amount="0")
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value,
    )


def test_blocks_positive_spend_amount_without_authorization():
    result = evaluate_spend_guard(
        SpendGuardRequest(intent=GuardIntent.EVALUATE, spend_amount="1.00")
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value,
    )


def test_blocks_external_mutation_without_authorization():
    result = evaluate_spend_guard(
        SpendGuardRequest(intent=GuardIntent.EVALUATE, external_mutation=True)
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION.value,
    )


@pytest.mark.parametrize("intent", [GuardIntent.WRITE, GuardIntent.MUTATE, "write", "mutate"])
def test_blocks_write_and_mutate_intents_without_authorization(intent):
    result = evaluate_spend_guard(SpendGuardRequest(intent=intent, channel="sandbox"))

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION.value,
    )


@pytest.mark.parametrize(
    "channel",
    ["live", "production", "shopify_admin", "dropi_orders", "meta_ads", "facebook_ads"],
)
def test_blocks_live_channel_keywords_without_authorization(channel):
    result = evaluate_spend_guard(
        SpendGuardRequest(intent=GuardIntent.READ, channel=channel)
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION.value,
    )


def test_allows_authorized_spend_inside_limit():
    result = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.SPEND,
            channel="sandbox",
            spend_amount="9.99",
            authorization=SpendAuthorization(
                spend_allowed=True,
                max_spend=Decimal("10.00"),
            ),
        )
    )

    assert result.decision is GuardDecision.ALLOW
    assert result.reason_codes == (GuardReasonCode.AUTHORIZED_ACTION_ALLOWED.value,)
    assert result.spend_amount == Decimal("9.99")
    assert result.max_spend == Decimal("10.00")


def test_blocks_authorized_spend_over_limit():
    result = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.SPEND,
            channel="sandbox",
            spend_amount="10.01",
            authorization=SpendAuthorization(
                spend_allowed=True,
                max_spend=Decimal("10.00"),
            ),
        )
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_SPEND_LIMIT_EXCEEDED.value,
    )


def test_allows_authorized_external_mutation_in_sandbox_channel():
    result = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.MUTATE,
            channel="sandbox",
            external_mutation=True,
            authorization=SpendAuthorization(mutation_allowed=True),
        )
    )

    assert result.decision is GuardDecision.ALLOW
    assert result.reason_codes == (GuardReasonCode.AUTHORIZED_ACTION_ALLOWED.value,)


def test_allows_authorized_live_channel_read_without_spend_or_mutation():
    result = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.READ,
            channel="shopify_admin",
            authorization=SpendAuthorization(live_channel_allowed=True),
        )
    )

    assert result.decision is GuardDecision.ALLOW
    assert result.reason_codes == (GuardReasonCode.AUTHORIZED_ACTION_ALLOWED.value,)


def test_multiple_block_reasons_are_stable_and_deduped():
    result = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.SPEND,
            channel="meta_ads",
            spend_amount="5.00",
            external_mutation=True,
        )
    )

    assert result.decision is GuardDecision.BLOCK
    assert result.reason_codes == (
        GuardReasonCode.BLOCKED_LIVE_CHANNEL_REQUIRES_AUTHORIZATION.value,
        GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value,
        GuardReasonCode.BLOCKED_EXTERNAL_MUTATION_REQUIRES_AUTHORIZATION.value,
    )


@pytest.mark.parametrize("bad_value", ["-0.01", "-1", Decimal("-1.00")])
def test_negative_spend_amount_is_rejected(bad_value):
    with pytest.raises(ValueError, match="spend_amount must be a finite non-negative decimal"):
        SpendGuardRequest(intent=GuardIntent.EVALUATE, spend_amount=bad_value)


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_spend_amount_is_rejected(bad_value):
    with pytest.raises(ValueError, match="spend_amount must be a finite non-negative decimal"):
        SpendGuardRequest(intent=GuardIntent.EVALUATE, spend_amount=bad_value)


def test_boolean_spend_amount_is_rejected():
    with pytest.raises(ValueError, match="spend_amount must be a finite non-negative decimal"):
        SpendGuardRequest(intent=GuardIntent.EVALUATE, spend_amount=True)


@pytest.mark.parametrize("bad_value", ["-1", "NaN", "Infinity", True])
def test_invalid_max_spend_is_rejected(bad_value):
    with pytest.raises(ValueError, match="max_spend must be a finite non-negative decimal"):
        SpendAuthorization(max_spend=bad_value)


@pytest.mark.parametrize("field", ["spend_allowed", "mutation_allowed", "live_channel_allowed"])
def test_authorization_boolean_fields_reject_non_bool(field):
    kwargs = {field: "yes"}

    with pytest.raises(ValueError, match=f"{field} must be bool"):
        SpendAuthorization(**kwargs)


def test_unknown_intent_is_rejected():
    with pytest.raises(ValueError, match="unsupported guard intent"):
        SpendGuardRequest(intent="launch_money_cannon")


def test_empty_channel_is_rejected():
    with pytest.raises(ValueError, match="channel must not be empty"):
        SpendGuardRequest(intent=GuardIntent.READ, channel="   ")


def test_assert_spend_guard_allows_returns_result_when_allowed():
    result = assert_spend_guard_allows(
        SpendGuardRequest(intent=GuardIntent.SIMULATE, channel="sandbox")
    )

    assert result.allowed is True


def test_assert_spend_guard_allows_raises_when_blocked():
    with pytest.raises(PermissionError, match=GuardReasonCode.BLOCKED_SPEND_REQUIRES_AUTHORIZATION.value):
        assert_spend_guard_allows(
            SpendGuardRequest(intent=GuardIntent.SPEND, spend_amount="1.00")
        )


def test_repeated_evaluation_is_deterministic():
    request = SpendGuardRequest(
        intent=GuardIntent.SPEND,
        channel="sandbox",
        spend_amount="7.50",
        authorization=SpendAuthorization(spend_allowed=True, max_spend="10.00"),
    )

    assert evaluate_spend_guard(request) == evaluate_spend_guard(request)


def test_package_exports_public_surface():
    assert safety.GuardDecision is GuardDecision
    assert safety.GuardIntent is GuardIntent
    assert safety.SpendAuthorization is SpendAuthorization
    assert safety.SpendGuardRequest is SpendGuardRequest
    assert safety.evaluate_spend_guard is evaluate_spend_guard


def test_spend_guard_source_has_no_io_network_or_environment_tokens():
    source = inspect.getsource(spend_guard)

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "subprocess",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "write_text",
        "read_text",
    )

    for token in forbidden:
        assert token not in source
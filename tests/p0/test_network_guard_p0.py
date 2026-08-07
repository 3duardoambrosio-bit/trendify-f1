from __future__ import annotations

import hashlib

import pytest

from infra.log_sanitizer import INVALID_URL_REDACTED, redact_url
from infra.network_guard import classify_system, decide_url, enforce_url_policy


DUMMY_TOKEN = "SYNAPSE_DUMMY_TOKEN_DO_NOT_USE"


def test_classify_system_domains():
    assert classify_system("https://graph.facebook.com/v20.0/me") == "meta"
    assert classify_system("https://api.dropi.co/orders") == "dropi"
    assert classify_system("https://foo.myshopify.com/admin") == "shopify"
    assert classify_system("https://example.com") is None


def test_default_blocks_sensitive(monkeypatch):
    # Defaults fail-closed: dry_run True -> no network to sensitive domains.
    monkeypatch.delenv("SYNAPSE_DRY_RUN", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_DROPI", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_SHOPIFY", raising=False)

    d = decide_url("https://graph.facebook.com/v20.0/me")
    assert d.allowed is False
    assert d.system == "meta"
    assert "NETWORK_BLOCKED_BY_FLAGS" in (d.reason or "")

    with pytest.raises(RuntimeError) as ex:
        enforce_url_policy("https://api.dropi.co/orders")
    assert "NETWORK_BLOCKED_BY_FLAGS" in str(ex.value)


def test_live_requires_two_switches(monkeypatch):
    # live_meta=1 pero dry_run=1 => sigue bloqueado
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    d1 = decide_url("https://graph.facebook.com/v20.0/me")
    assert d1.allowed is False

    # dry_run=0 + live_meta=1 => permitido
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    d2 = decide_url("https://graph.facebook.com/v20.0/me")
    assert d2.allowed is True


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "access_token",
        "ACCESS_TOKEN",
        "access-token",
        "access%5Ftoken",
        "accessToken",
        "api_key",
        "client_secret",
        "authorization",
    ],
)
def test_block_reason_redacts_sensitive_url_parts(monkeypatch, sensitive_key):
    marker = "SYNAPSE_DUMMY_TOKEN_DO_NOT_USE"
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_META_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)

    url = (
        f"https://{marker}@graph.facebook.com/v22.0/me"
        f"?fields=id%2Cname&{sensitive_key}={marker}"
        f";{sensitive_key}={marker}&limit=25&empty=&flag"
        f"#access_token={marker}"
    )

    decision = decide_url(url)
    assert decision.allowed is False
    assert decision.system == "meta"
    reason = decision.reason or ""
    assert marker not in reason
    assert "system=meta" in reason
    assert "graph.facebook.com/v22.0/me" in reason
    assert "fields=id%2Cname" in reason
    assert "limit=25&empty=&flag" in reason
    assert reason.count("=REDACTED") == 2

    with pytest.raises(RuntimeError) as exc_info:
        enforce_url_policy(url)

    assert str(exc_info.value) == reason


def test_block_reason_preserves_safe_query_literal(monkeypatch):
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_META_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    url = (
        "https://graph.facebook.com/v22.0/me"
        "?fields=id,name&limit=25&after=abc%2B123&empty=&flag"
    )

    decision = decide_url(url)

    assert decision.allowed is False
    assert url in (decision.reason or "")


@pytest.mark.parametrize(
    "url",
    [
        (
            "https://graph.facebook.com/v22.0/safe-path"
            f"?fields=id&access_to%ZZken={DUMMY_TOKEN}&limit=25"
        ),
        (
            "https://graph.facebook.com/v22.0/safe-path"
            f"?fields=id&access_token={DUMMY_TOKEN}%A&limit=25"
        ),
    ],
    ids=["malformed-key", "malformed-value"],
)
def test_invalid_percent_query_fails_closed(monkeypatch, url):
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)

    sanitized = redact_url(url)
    assert sanitized == "https://graph.facebook.com/v22.0/safe-path?REDACTED"
    assert redact_url(url) == sanitized
    assert DUMMY_TOKEN not in sanitized

    decision = decide_url(url)
    reason = decision.reason or ""
    assert decision.allowed is False
    assert decision.system == "meta"
    assert sanitized in reason
    assert DUMMY_TOKEN not in reason

    with pytest.raises(RuntimeError) as exc_info:
        enforce_url_policy(url)

    assert str(exc_info.value) == reason
    assert DUMMY_TOKEN not in repr(exc_info.value)


def test_invalid_percent_userinfo_fails_closed(monkeypatch):
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    url = (
        f"https://user%ZZ:{DUMMY_TOKEN}@graph.facebook.com"
        "/v22.0/safe-path?fields=id"
    )

    sanitized = redact_url(url)
    assert sanitized == "https://graph.facebook.com/v22.0/safe-path?fields=id"
    assert redact_url(url) == sanitized
    assert DUMMY_TOKEN not in sanitized

    reason = decide_url(url).reason or ""
    assert sanitized in reason
    assert DUMMY_TOKEN not in reason


def test_invalid_percent_fragment_fails_closed(monkeypatch):
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    url = (
        "https://graph.facebook.com/v22.0/safe-path?fields=id"
        f"#access_token={DUMMY_TOKEN}%"
    )

    sanitized = redact_url(url)
    assert sanitized == "https://graph.facebook.com/v22.0/safe-path?fields=id"
    assert redact_url(url) == sanitized
    assert DUMMY_TOKEN not in sanitized

    reason = decide_url(url).reason or ""
    assert sanitized in reason
    assert DUMMY_TOKEN not in reason


def test_valid_encoded_secret_is_redacted_and_safe_diagnostics_survive(monkeypatch):
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)
    encoded_token = "".join(f"%{ord(char):02X}" for char in DUMMY_TOKEN)
    safe_sha256 = hashlib.sha256(b"safe diagnostic body").hexdigest()
    safe_id = "campaign_1234567890"
    url = (
        "https://graph.facebook.com/v22.0/safe-path"
        f"?access_token={encoded_token}"
        f"&response_sha256={safe_sha256}&campaign_id={safe_id}&http_status=401"
    )

    sanitized = redact_url(url)

    assert sanitized.startswith("https://graph.facebook.com/v22.0/safe-path?")
    assert "access_token=REDACTED" in sanitized
    assert encoded_token not in sanitized
    assert DUMMY_TOKEN not in sanitized
    assert f"response_sha256={safe_sha256}" in sanitized
    assert f"campaign_id={safe_id}" in sanitized
    assert "http_status=401" in sanitized
    assert redact_url(url) == sanitized

    reason = decide_url(url).reason or ""
    assert sanitized in reason
    assert DUMMY_TOKEN not in reason


def test_parser_error_returns_constant_without_unsafe_url():
    url = (
        f"https://[graph.facebook.com/{DUMMY_TOKEN}"
        f"?access_token={DUMMY_TOKEN}"
    )

    sanitized = redact_url(url)

    assert sanitized == INVALID_URL_REDACTED
    assert DUMMY_TOKEN not in sanitized


def test_nfkc_incompatible_userinfo_fails_closed_without_secret_reflection():
    url = (
        f"https://user\uff1a{DUMMY_TOKEN}@graph.facebook.com"
        "/v22.0/safe-path?fields=id"
    )
    encoded_token = "".join(f"%{ord(char):02X}" for char in DUMMY_TOKEN)
    secret_fragments = (
        DUMMY_TOKEN,
        encoded_token,
        "DUMMY_TOKEN",
        "TOKEN_DO_NOT_USE",
        "DUMMY_TOKEN_DO",
        "MY_TOKEN_DO_NOT",
        "DO_NOT_USE",
        "UMMY_TOK",
        "TOKEN_DO",
    )

    sanitized = redact_url(url)
    decision = decide_url(url)

    assert sanitized == INVALID_URL_REDACTED
    assert redact_url(url) == sanitized
    assert classify_system(url) is None
    assert decision.allowed is False
    assert decision.system is None
    assert decision.reason == (
        f"NETWORK_BLOCKED_INVALID_URL: url={INVALID_URL_REDACTED}"
    )

    with pytest.raises(RuntimeError) as exc_info:
        enforce_url_policy(url)

    rendered_values = (
        sanitized,
        decision.reason or "",
        repr(decision),
        str(exc_info.value),
        repr(exc_info.value),
    )
    for rendered in rendered_values:
        for secret_fragment in secret_fragments:
            assert secret_fragment not in rendered
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None

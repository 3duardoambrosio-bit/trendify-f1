from __future__ import annotations

from collections.abc import Iterator
import inspect

import pytest

from synapse.meta.publisher_adapter import (
    MetaCampaignPayload,
    _is_live_transport_enabled,
    call_create_campaign,
    call_pause_campaign,
)


LIVE_ENV_KEYS = (
    "SYNAPSE_META_LIVE",
    "SYNAPSE_LIVE_META",
    "SYNAPSE_LIVE_WRITE",
    "SYNAPSE_DRY_RUN",
    "META_ACCESS_TOKEN",
    "META_AD_ACCOUNT_ID",
)


@pytest.fixture(autouse=True)
def clean_meta_live_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _payload() -> MetaCampaignPayload:
    kwargs = {
        "name": "A8-R106 guard probe",
        "objective": "OUTCOME_SALES",
        "status": "PAUSED",
    }
    signature = inspect.signature(MetaCampaignPayload)
    return MetaCampaignPayload(
        **{
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
    )


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, False),
        ({"SYNAPSE_META_LIVE": "1"}, False),
        ({"SYNAPSE_META_LIVE": "1", "SYNAPSE_LIVE_META": "1"}, False),
        (
            {
                "SYNAPSE_META_LIVE": "1",
                "SYNAPSE_LIVE_META": "1",
                "SYNAPSE_LIVE_WRITE": "1",
            },
            False,
        ),
        (
            {
                "SYNAPSE_META_LIVE": "1",
                "SYNAPSE_LIVE_META": "1",
                "SYNAPSE_LIVE_WRITE": "1",
                "SYNAPSE_DRY_RUN": "1",
            },
            False,
        ),
        (
            {
                "SYNAPSE_META_LIVE": "1",
                "SYNAPSE_LIVE_META": "1",
                "SYNAPSE_LIVE_WRITE": "1",
                "SYNAPSE_DRY_RUN": "0",
            },
            True,
        ),
    ],
)
def test_a8_r106_i2_live_transport_requires_all_standard_flags(
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    expected: bool,
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert _is_live_transport_enabled() is expected


def test_a8_r106_i2_create_blocks_before_token_when_standard_write_flag_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNAPSE_META_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "0")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")

    with pytest.raises(NotImplementedError) as exc:
        call_create_campaign(_payload())

    message = str(exc.value)
    assert "SYNAPSE_LIVE_WRITE" in message
    assert "META_ACCESS_TOKEN" not in message


def test_a8_r106_i2_pause_blocks_before_token_when_global_meta_flag_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNAPSE_META_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")

    with pytest.raises(NotImplementedError) as exc:
        call_pause_campaign("120000000000000000")

    message = str(exc.value)
    assert "SYNAPSE_LIVE_META" in message
    assert "META_ACCESS_TOKEN" not in message


def test_a8_r106_i2_dry_run_blocks_even_when_live_flags_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNAPSE_META_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")

    with pytest.raises(NotImplementedError) as exc:
        call_create_campaign(_payload())

    message = str(exc.value)
    assert "SYNAPSE_DRY_RUN=0" in message
    assert "META_ACCESS_TOKEN" not in message


def test_a8_r106_i2_all_flags_on_reaches_token_gate_not_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNAPSE_META_LIVE", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_META", "1")
    monkeypatch.setenv("SYNAPSE_LIVE_WRITE", "1")
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "0")

    with pytest.raises(RuntimeError) as exc:
        call_create_campaign(_payload())

    assert "META_ACCESS_TOKEN" in str(exc.value)

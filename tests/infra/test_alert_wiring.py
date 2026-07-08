"""S19 Tests: Alert wiring factory."""

from __future__ import annotations

import os

import pytest

from synapse.infra.alert_wiring import get_alert_sink, reset_alert_sink
from synapse.infra.alerts import NullAlertSink, TelegramAlertSink


@pytest.fixture(autouse=True)
def _clean_wiring():
    reset_alert_sink()
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)
    yield
    reset_alert_sink()
    if old_token is not None:
        os.environ["TELEGRAM_BOT_TOKEN"] = old_token
    if old_chat is not None:
        os.environ["TELEGRAM_CHAT_ID"] = old_chat


def test_returns_null_sink_without_env_vars():
    sink = get_alert_sink(force_new=True)
    assert isinstance(sink, NullAlertSink)


def test_returns_telegram_sink_with_env_vars():
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:ABC"
    os.environ["TELEGRAM_CHAT_ID"] = "999"
    sink = get_alert_sink(force_new=True)
    assert isinstance(sink, TelegramAlertSink)


def test_caches_singleton():
    s1 = get_alert_sink(force_new=True)
    s2 = get_alert_sink()
    assert s1 is s2


def test_force_new_resets_cache():
    s1 = get_alert_sink(force_new=True)
    s2 = get_alert_sink(force_new=True)
    assert s1 is not s2

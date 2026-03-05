"""
S19 — Alert Wiring: factory for AlertSink.

get_alert_sink() reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from env.
If both set → TelegramAlertSink.
If either missing → NullAlertSink (silent, safe).

__MARKER__ embedded below.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from synapse.infra.alerts import AlertSink, NullAlertSink, TelegramAlertSink

__MARKER__ = "SESSION_S19_alert_wiring_2026-03-04"

log = logging.getLogger(__name__)

_cached_sink: Optional[AlertSink] = None


def get_alert_sink(*, force_new: bool = False) -> AlertSink:
    """
    Return the configured AlertSink.

    Caches the instance for the process lifetime (singleton).
    Set force_new=True in tests to reset.
    """
    global _cached_sink
    if _cached_sink is not None and not force_new:
        return _cached_sink

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if token and chat_id:
        log.info("alert_wiring: TelegramAlertSink configured (chat_id=%s...)", chat_id[:4])
        _cached_sink = TelegramAlertSink(token=token, chat_id=chat_id)
    else:
        log.info("alert_wiring: NullAlertSink (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set)")
        _cached_sink = NullAlertSink()

    return _cached_sink


def reset_alert_sink() -> None:
    """Reset cached sink (for tests only)."""
    global _cached_sink
    _cached_sink = None

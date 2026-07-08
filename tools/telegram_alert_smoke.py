"""
Telegram Alert Smoke Test — S17.

Usage:
  $env:TELEGRAM_BOT_TOKEN="123:ABC..."
  $env:TELEGRAM_CHAT_ID="123456789"
  python tools/telegram_alert_smoke.py --text "SYNAPSE smoke" --level WARN
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--level", default="INFO")
    args = ap.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("WARN: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Using dry-run (NullAlertSink).")
        from synapse.infra.alerts import NullAlertSink
        sink = NullAlertSink()
    else:
        from synapse.infra.alerts import TelegramAlertSink
        sink = TelegramAlertSink(token=token, chat_id=chat_id)

    r = sink.send(args.text, level=args.level)

    if r.ok and r.delivered:
        print(f"PASS delivered=1 status={r.status}")
        return 0

    if r.ok and not r.delivered:
        print(f"OK delivered=0 (dry-run or rate-limited) error={r.error}")
        return 0

    print(f"FAIL delivered=0 ok={r.ok} status={r.status} error={r.error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

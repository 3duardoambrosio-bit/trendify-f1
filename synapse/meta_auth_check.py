from __future__ import annotations
from infra.network_guard import enforce_url_policy

from synapse.infra.cli_logging import cli_print

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError


__MARKER__ = "META_AUTH_CHECK_2026-01-15_V1"


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url: str) -> dict:
    try:
        raw = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return {"error": json.loads(body), "http_status": e.code}
        except Exception:
            return {"error": body, "http_status": e.code}


def main() -> int:
    t = os.environ.get("META_ACCESS_TOKEN", "") or ""
    if not t.strip():
        cli_print(json.dumps({
            "marker": __MARKER__,
            "ts": _utc_now_z(),
            "status": "SKIP",
            "reason": "META_ACCESS_TOKEN missing (expected before API Day)",
        }, ensure_ascii=False, indent=2))
        return 0

    u = "https://graph.facebook.com/v22.0/me?" + urllib.parse.urlencode({

    enforce_url_policy(u)
        "fields": "id,name",
        "access_token": t.strip(),
    })
    resp = _get(u)

    ok = isinstance(resp, dict) and ("error" not in resp)
    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": "OK" if ok else "FAIL",
        "response": resp,
        "notes": {
            "no_secrets_printed": True,
            "expected_ok": "resp has id,name",
        }
    }, ensure_ascii=False, indent=2))

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
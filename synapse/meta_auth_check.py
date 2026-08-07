from __future__ import annotations
from infra.network_guard import enforce_url_policy

from synapse.infra.cli_logging import cli_print

import hashlib
import json
import os
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from urllib.error import HTTPError


__MARKER__ = "META_AUTH_CHECK_2026-01-15_V1"
_REDIRECT_DIAGNOSTIC = "META_AUTH_REDIRECT_BLOCKED"
_REDIRECT_CLOSE_DIAGNOSTIC = "META_AUTH_REDIRECT_BLOCKED_CLOSE_FAILED"
_SUCCESS_DIAGNOSTIC = "META_AUTH_OK"
_TRANSPORT_DIAGNOSTIC = "HTTP_TRANSPORT_ERROR"


class _MetaAuthRedirectBlocked(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _response_status(response, default: int) -> int:
    try:
        status = getattr(response, "status", None)
        if status is None:
            getcode = getattr(response, "getcode", None)
            status = getcode() if callable(getcode) else default
        return int(status) if status is not None else default
    except Exception:
        return default


def _read_and_close(response) -> tuple[bytes | None, str | None]:
    body = None
    read_failed = False
    close_failed = False

    try:
        with closing(response) as stream:
            try:
                body = stream.read()
            except Exception:
                read_failed = True
    except Exception:
        close_failed = True

    if read_failed and close_failed:
        return None, "HTTP_RESPONSE_READ_AND_CLOSE_FAILED"
    if read_failed:
        return None, "HTTP_RESPONSE_READ_FAILED"
    if close_failed:
        return None, "HTTP_RESPONSE_CLOSE_FAILED"
    if not isinstance(body, (bytes, bytearray, memoryview)):
        return None, "HTTP_RESPONSE_BODY_TYPE_INVALID"
    return bytes(body), None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        close_failed = False
        if fp is not None:
            try:
                fp.close()
            except Exception:
                close_failed = True
        diagnostic = (
            _REDIRECT_CLOSE_DIAGNOSTIC
            if close_failed
            else _REDIRECT_DIAGNOSTIC
        )
        raise _MetaAuthRedirectBlocked(diagnostic) from None


def _build_no_redirect_opener():
    return urllib.request.build_opener(_NoRedirectHandler())


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url: str, *, access_token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        response = _build_no_redirect_opener().open(request, timeout=30)
    except _MetaAuthRedirectBlocked as exc:
        return {"error": exc.code}
    except HTTPError as exc:
        status = _response_status(exc, 0)
        body, failure = _read_and_close(exc)
        if failure is not None or body is None:
            return {"error": failure or "HTTP_RESPONSE_READ_FAILED", "http_status": status}
        return {
            "error": "HTTP_ERROR_RESPONSE",
            "http_status": status,
            "response_byte_count": len(body),
            "response_sha256": hashlib.sha256(body).hexdigest(),
        }
    except Exception:
        return {"error": _TRANSPORT_DIAGNOSTIC}

    status = _response_status(response, 200)
    body, failure = _read_and_close(response)
    if failure is not None or body is None:
        return {"error": failure or "HTTP_RESPONSE_READ_FAILED", "http_status": status}

    diagnostics = {
        "http_status": status,
        "response_byte_count": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }
    if 200 <= status < 300:
        return {"result": _SUCCESS_DIAGNOSTIC, **diagnostics}
    return {"error": "HTTP_UNEXPECTED_STATUS", **diagnostics}


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

    access_token = t.strip()
    u = "https://graph.facebook.com/v22.0/me?" + urllib.parse.urlencode({
        "fields": "id,name",
    })
    enforce_url_policy(u)
    resp = _get(u, access_token=access_token)

    ok = isinstance(resp, dict) and resp.get("result") == _SUCCESS_DIAGNOSTIC
    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": "OK" if ok else "FAIL",
        "response": resp,
        "notes": {
            "no_secrets_printed": True,
            "expected_ok": "transport returned HTTP 2xx",
        }
    }, ensure_ascii=False, indent=2))

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

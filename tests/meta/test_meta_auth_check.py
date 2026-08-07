from __future__ import annotations

import hashlib
import io
import json
import runpy
import urllib.request
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

import synapse.meta_auth_check as meta_auth_check


DUMMY_TOKEN = "SYNAPSE_DUMMY_TOKEN_DO_NOT_USE"
ENCODED_DUMMY_TOKEN = "".join(f"%{ord(char):02X}" for char in DUMMY_TOKEN)
SPECIFIC_SECRET_FRAGMENTS = (
    DUMMY_TOKEN,
    ENCODED_DUMMY_TOKEN,
    "DUMMY_TOKEN",
    "TOKEN_DO_NOT_USE",
    "DUMMY_TOKEN_DO",
    "MY_TOKEN_DO_NOT",
    "DO_NOT_USE",
    "UMMY_TOK",
    "TOKEN_DO",
)


def _assert_no_secret_material(*values):
    for value in values:
        rendered = str(value)
        for secret_fragment in SPECIFIC_SECRET_FRAGMENTS:
            assert secret_fragment not in rendered


class CloseCountingBytesIO(io.BytesIO):
    def __init__(self, value: bytes, *, status: int = 200):
        super().__init__(value)
        self.status = status
        self.read_count = 0
        self.close_count = 0

    def read(self, *args, **kwargs):
        self.read_count += 1
        return super().read(*args, **kwargs)

    def close(self):
        self.close_count += 1
        super().close()


class CloseFailingResponse(CloseCountingBytesIO):
    def close(self):
        self.close_count += 1
        io.BytesIO.close(self)
        raise RuntimeError(DUMMY_TOKEN)


class PlainCloseCountingResponse:
    def __init__(self, value: bytes, *, status: int = 200):
        self._value = value
        self.status = status
        self.read_count = 0
        self.close_count = 0

    def read(self):
        self.read_count += 1
        return self._value

    def close(self):
        self.close_count += 1


def test_default_guard_blocks_without_exposing_token(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    monkeypatch.setenv("SYNAPSE_DRY_RUN", "1")
    monkeypatch.delenv("SYNAPSE_META_LIVE", raising=False)
    monkeypatch.delenv("SYNAPSE_LIVE_META", raising=False)

    def network_bomb():
        raise AssertionError("opener must not be built")

    monkeypatch.setattr(meta_auth_check, "_build_no_redirect_opener", network_bomb)

    with pytest.raises(RuntimeError) as exc_info:
        meta_auth_check.main()

    message = str(exc_info.value)
    assert "NETWORK_BLOCKED_BY_FLAGS" in message
    assert "graph.facebook.com/v22.0/me" in message
    assert DUMMY_TOKEN not in message
    assert "access_token" not in message
    assert DUMMY_TOKEN not in repr(exc_info.value)


def test_auth_check_uses_header_and_clean_url(monkeypatch, capsys):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    guarded_urls: list[str] = []
    captured: dict[str, object] = {}
    response = CloseCountingBytesIO(b'{"id":"1","name":"dummy"}')

    class FakeOpener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

    monkeypatch.setattr(meta_auth_check, "enforce_url_policy", guarded_urls.append)
    monkeypatch.setattr(
        meta_auth_check,
        "_build_no_redirect_opener",
        lambda: FakeOpener(),
    )

    rc = meta_auth_check.main()

    assert rc == 0
    assert len(guarded_urls) == 1
    guarded_url = guarded_urls[0]
    assert DUMMY_TOKEN not in guarded_url
    assert parse_qs(urlsplit(guarded_url).query) == {"fields": ["id,name"]}

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert DUMMY_TOKEN not in request.full_url
    assert request.get_header("Authorization") == f"Bearer {DUMMY_TOKEN}"
    assert captured["timeout"] == 30
    assert DUMMY_TOKEN not in repr(request)
    captured_output = capsys.readouterr()
    assert DUMMY_TOKEN not in captured_output.out
    assert DUMMY_TOKEN not in captured_output.err
    assert response.read_count == 1
    assert response.close_count == 1


def test_successful_2xx_body_is_replaced_with_safe_diagnostics(
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    body = f'{{"id":"1","name":"dummy","echo":"{DUMMY_TOKEN}"}}'.encode()
    response = PlainCloseCountingResponse(body, status=200)
    guarded_urls: list[str] = []
    captured: dict[str, object] = {}

    class FakeOpener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

    monkeypatch.setattr(meta_auth_check, "enforce_url_policy", guarded_urls.append)
    monkeypatch.setattr(
        meta_auth_check,
        "_build_no_redirect_opener",
        lambda: FakeOpener(),
    )

    rc = meta_auth_check.main()
    captured_output = capsys.readouterr()
    payload = json.loads(captured_output.out)
    safe_response = payload["response"]

    assert rc == 0
    assert payload["status"] == "OK"
    assert safe_response == {
        "result": "META_AUTH_OK",
        "http_status": 200,
        "response_byte_count": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }
    assert len(guarded_urls) == 1
    assert DUMMY_TOKEN not in guarded_urls[0]
    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert DUMMY_TOKEN not in request.full_url
    assert request.get_header("Authorization") == f"Bearer {DUMMY_TOKEN}"
    assert captured["timeout"] == 30
    assert response.read_count == 1
    assert response.close_count == 1
    assert body.decode() not in captured_output.out
    _assert_no_secret_material(
        captured_output.out,
        captured_output.err,
        repr(safe_response),
        repr(request),
    )


def test_successful_response_close_failure_is_sanitized(
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    body = f'{{"echo":"{DUMMY_TOKEN}"}}'.encode()
    response = CloseFailingResponse(body, status=200)

    class FakeOpener:
        def open(self, request, timeout):
            return response

    monkeypatch.setattr(meta_auth_check, "enforce_url_policy", lambda url: None)
    monkeypatch.setattr(
        meta_auth_check,
        "_build_no_redirect_opener",
        lambda: FakeOpener(),
    )

    rc = meta_auth_check.main()
    captured_output = capsys.readouterr()
    payload = json.loads(captured_output.out)

    assert rc == 2
    assert payload["status"] == "FAIL"
    assert payload["response"] == {
        "error": "HTTP_RESPONSE_CLOSE_FAILED",
        "http_status": 200,
    }
    assert response.read_count == 1
    assert response.close_count == 1
    _assert_no_secret_material(
        captured_output.out,
        captured_output.err,
        repr(payload["response"]),
    )


@pytest.mark.parametrize(
    "body",
    [
        f'{{"error":"{DUMMY_TOKEN}"}}'.encode(),
        f"upstream-prefix={DUMMY_TOKEN[:6]}".encode(),
        f"upstream-suffix={DUMMY_TOKEN[-6:]}".encode(),
    ],
    ids=["full", "prefix", "suffix"],
)
def test_http_error_body_is_replaced_with_safe_diagnostics(
    monkeypatch,
    capsys,
    body,
):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    guarded_urls: list[str] = []
    error_body = CloseCountingBytesIO(body, status=401)

    class ErrorOpener:
        def open(self, request, timeout):
            raise HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                error_body,
            )

    monkeypatch.setattr(meta_auth_check, "enforce_url_policy", guarded_urls.append)
    monkeypatch.setattr(
        meta_auth_check,
        "_build_no_redirect_opener",
        lambda: ErrorOpener(),
    )

    rc = meta_auth_check.main()
    captured_output = capsys.readouterr()
    payload = json.loads(captured_output.out)
    response = payload["response"]

    assert rc == 2
    assert len(guarded_urls) == 1
    assert response == {
        "error": "HTTP_ERROR_RESPONSE",
        "http_status": 401,
        "response_byte_count": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }
    assert error_body.read_count == 1
    assert error_body.close_count == 1
    assert body.decode() not in captured_output.out
    for fragment in (DUMMY_TOKEN, DUMMY_TOKEN[:6], DUMMY_TOKEN[-6:]):
        assert fragment not in captured_output.out
        assert fragment not in captured_output.err
        assert fragment not in repr(response)
    _assert_no_secret_material(
        captured_output.out,
        captured_output.err,
        repr(response),
    )


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_cross_origin_redirect_is_blocked_before_second_request(
    monkeypatch,
    capsys,
    status,
):
    second_request_count = 0
    redirect_url = (
        "https://redirect.invalid/collect"
        f"?access_token={DUMMY_TOKEN}"
    )

    def fake_build_opener(handler):
        assert isinstance(handler, meta_auth_check._NoRedirectHandler)
        return handler

    monkeypatch.setattr(
        meta_auth_check.urllib.request,
        "build_opener",
        fake_build_opener,
    )
    handler = meta_auth_check._build_no_redirect_opener()
    response = CloseCountingBytesIO(b"redirect response", status=status)
    headers = Message()
    headers["Location"] = redirect_url
    request = urllib.request.Request(
        "https://graph.facebook.com/v22.0/me?fields=id%2Cname",
        headers={"Authorization": f"Bearer {DUMMY_TOKEN}"},
    )

    class ParentOpener:
        def open(self, request, timeout=None):
            nonlocal second_request_count
            second_request_count += 1
            raise AssertionError("a redirected request must not be issued")

    handler.add_parent(ParentOpener())

    with pytest.raises(meta_auth_check._MetaAuthRedirectBlocked) as exc_info:
        redirect_method = getattr(handler, f"http_error_{status}")
        redirect_method(request, response, status, "Redirect", headers)

    captured_output = capsys.readouterr()
    assert str(exc_info.value) == "META_AUTH_REDIRECT_BLOCKED"
    assert exc_info.value.code == "META_AUTH_REDIRECT_BLOCKED"
    assert second_request_count == 0
    assert response.closed is True
    assert response.close_count == 1
    assert DUMMY_TOKEN not in repr(exc_info.value)
    assert DUMMY_TOKEN not in captured_output.out
    assert DUMMY_TOKEN not in captured_output.err
    _assert_no_secret_material(
        repr(exc_info.value),
        captured_output.out,
        captured_output.err,
    )


def test_redirect_returns_safe_rc_without_traceback(monkeypatch, capsys):
    monkeypatch.setenv("META_ACCESS_TOKEN", DUMMY_TOKEN)
    handler = meta_auth_check._NoRedirectHandler()
    redirect_response = CloseCountingBytesIO(b"redirect response", status=302)
    second_request_count = 0
    captured: dict[str, object] = {}
    redirect_url = (
        "https://redirect.invalid/collect"
        f"?access_token={DUMMY_TOKEN}"
    )

    class RedirectingOpener:
        def open(self, request, timeout):
            nonlocal second_request_count
            captured["request"] = request
            captured["timeout"] = timeout
            handler.redirect_request(
                request,
                redirect_response,
                302,
                "Found",
                {"Location": redirect_url},
                redirect_url,
            )
            second_request_count += 1
            raise AssertionError("a redirected request must not be issued")

    monkeypatch.setattr(meta_auth_check, "enforce_url_policy", lambda url: None)
    monkeypatch.setattr(
        meta_auth_check,
        "_build_no_redirect_opener",
        lambda: RedirectingOpener(),
    )

    rc = meta_auth_check.main()
    captured_output = capsys.readouterr()
    payload = json.loads(captured_output.out)

    assert rc == 2
    assert payload["status"] == "FAIL"
    assert payload["response"] == {"error": "META_AUTH_REDIRECT_BLOCKED"}
    assert second_request_count == 0
    assert redirect_response.close_count == 1
    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert DUMMY_TOKEN not in request.full_url
    assert request.get_header("Authorization") == f"Bearer {DUMMY_TOKEN}"
    assert captured["timeout"] == 30
    _assert_no_secret_material(
        captured_output.out,
        captured_output.err,
        repr(payload["response"]),
        repr(request),
    )


def test_root_meta_check_delegates_without_network(monkeypatch):
    script_path = Path(__file__).resolve().parents[2] / "_meta_me_check.py"
    monkeypatch.setattr(meta_auth_check, "main", lambda: 17)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(script_path), run_name="__main__")

    assert exc_info.value.code == 17

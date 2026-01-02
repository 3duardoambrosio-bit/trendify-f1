# tests/integration/test_http_client.py
import json
import urllib.error
from types import SimpleNamespace
from unittest import mock

import pytest

from synapse.integration.http_client import (
    SimpleHttpClient,
    HttpRequest,
    HttpResponseError,
)


class _FakeResp:
    def __init__(self, status=200, body=b'{"ok": true}', headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_dry_run_returns_json():
    c = SimpleHttpClient(dry_run=True)
    r = c.get("https://example.com")
    assert r.status == 200
    assert r.headers.get("x-dry-run") == "1"
    assert r.json()["dry_run"] is True


def test_post_json_sets_content_type_and_encodes():
    c = SimpleHttpClient(dry_run=True)
    r = c.post_json("https://example.com", {"hola": "mundo"})
    assert r.status == 200


def test_http_4xx_raises_no_retry(monkeypatch):
    c = SimpleHttpClient(retry_max=3, backoff_s=0)
    err = urllib.error.HTTPError(
        url="x",
        code=401,
        msg="nope",
        hdrs=None,
        fp=None,
    )

    def _raise(*args, **kwargs):
        raise err

    with mock.patch("urllib.request.urlopen", side_effect=_raise) as m:
        with pytest.raises(HttpResponseError) as ex:
            c.request(HttpRequest(method="GET", url="https://x"))
        assert ex.value.status == 401
        assert m.call_count == 1  # no retry on 4xx


def test_retry_on_5xx_then_success(monkeypatch):
    c = SimpleHttpClient(retry_max=2, backoff_s=0)

    err = urllib.error.HTTPError(
        url="x",
        code=500,
        msg="server",
        hdrs=None,
        fp=None,
    )

    calls = {"n": 0}

    def _side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise err
        return _FakeResp(status=200, body=b'{"ok": true}')

    with mock.patch("urllib.request.urlopen", side_effect=_side_effect) as m:
        r = c.get("https://x")
        assert r.status == 200
        assert r.json()["ok"] is True
        assert m.call_count == 2

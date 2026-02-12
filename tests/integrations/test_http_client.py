import io
import urllib.error
from unittest import mock

import pytest

from synapse.integrations.http_client import SimpleHttpClient, HttpRequest, HttpResponseError


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


def test_default_is_dry_run_and_never_calls_urlopen():
    c = SimpleHttpClient()  # dry_run=True default

    with mock.patch("urllib.request.urlopen") as m:
        r = c.get("https://example.com")
        assert r.status == 200
        assert r.headers.get("x-dry-run") == "1"
        assert r.json()["dry_run"] is True
        assert m.call_count == 0  # ACERO: no network call


def test_dry_run_false_calls_urlopen():
    c = SimpleHttpClient(dry_run=False, retry_max=0, backoff_s=0)
    with mock.patch("urllib.request.urlopen", return_value=_FakeResp(status=200, body=b'{"ok": true}')) as m:
        r = c.get("https://x")
        assert r.status == 200
        assert r.json()["ok"] is True
        assert m.call_count == 1


def test_http_4xx_raises_no_retry():
    c = SimpleHttpClient(dry_run=False, retry_max=3, backoff_s=0)

    err = urllib.error.HTTPError(
        url="x",
        code=401,
        msg="nope",
        hdrs=None,
        fp=io.BytesIO(b"unauthorized"),
    )

    def _raise(*args, **kwargs):
        raise err

    with mock.patch("urllib.request.urlopen", side_effect=_raise) as m:
        with pytest.raises(HttpResponseError) as ex:
            c.request(HttpRequest(method="GET", url="https://x"))
        assert ex.value.status == 401
        assert m.call_count == 1  # no retry on 4xx


def test_retry_on_5xx_then_success():
    c = SimpleHttpClient(dry_run=False, retry_max=2, backoff_s=0)

    err = urllib.error.HTTPError(
        url="x",
        code=500,
        msg="server",
        hdrs=None,
        fp=io.BytesIO(b"server error"),
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
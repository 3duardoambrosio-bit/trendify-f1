from __future__ import annotations

import json

import synapse.shopify.shopify_writer as m


class _RespObj:
    def __init__(self, *, status_code=None, text=None, body=None, content=None, json_value=None, json_exc=None):
        self.status_code = status_code
        self.text = text
        self.body = body
        self.content = content
        self._json_value = json_value
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_value


def test_coerce_tuple_bytes_body_decodes_utf8():
    status, text = m._coerce_http_response((200, b'{"ok":true}'))
    assert status == 200
    assert text == '{"ok":true}'


def test_coerce_dict_content_bytes_decodes_utf8():
    status, text = m._coerce_http_response({"status_code": 201, "content": b'{"x":1}'})
    assert status == 201
    assert text == '{"x":1}'


def test_coerce_object_text_bytes_decodes_utf8():
    resp = _RespObj(status_code=202, text=b'{"msg":"bytes"}')
    status, text = m._coerce_http_response(resp)
    assert status == 202
    assert text == '{"msg":"bytes"}'


def test_coerce_object_json_fallback_serializes_when_text_missing():
    resp = _RespObj(status_code=203, text=None, body=None, content=None, json_value={"ok": True, "n": 1})
    status, text = m._coerce_http_response(resp)
    assert status == 203
    assert json.loads(text) == {"ok": True, "n": 1}


def test_coerce_object_json_failure_fails_closed_to_empty_text():
    resp = _RespObj(status_code=204, text=None, body=None, content=None, json_exc=RuntimeError("boom"))
    status, text = m._coerce_http_response(resp)
    assert status == 204
    assert text == ""


def test_coerce_none_returns_zero_and_empty_text():
    status, text = m._coerce_http_response(None)
    assert status == 0
    assert text == ""


def test_coerce_bad_status_fails_closed_to_zero():
    resp = _RespObj(status_code="NOPE", text="abc")
    status, text = m._coerce_http_response(resp)
    assert status == 0
    assert text == "abc"

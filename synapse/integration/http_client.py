# synapse/integration/http_client.py
"""
HTTP Client (stdlib) para SYNAPSE.

Objetivo:
- Unificar llamadas HTTP futuras (Shopify/Meta/TikTok) sin meter requests.
- Retry con backoff + timeouts.
- Modo dry-run para no pegarle a internet mientras probamos.

ACERO, NO HUMO:
- Determinista, testeable, mock-friendly.
"""

from __future__ import annotations
from infra.network_guard import enforce_url_policy

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union


class HttpClientError(RuntimeError):
    pass


class HttpTimeoutError(HttpClientError):
    pass


class HttpResponseError(HttpClientError):
    def __init__(self, status: int, body: bytes, message: str = "HTTP error"):
        super().__init__(f"{message} (status={status})")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    timeout_s: float = 20.0


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def _encode_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class SimpleHttpClient:
    """
    Cliente HTTP mínimo y serio:
    - retry_max: reintentos además del primer intento (retry_max=2 => hasta 3 intentos)
    - backoff_s: base, se multiplica (1x, 2x, 4x)
    """

    def __init__(
        self,
        *,
        retry_max: int = 2,
        backoff_s: float = 0.4,
        dry_run: bool = False,
        user_agent: str = "synapse-http/1.0",
    ):
        if retry_max < 0:
            raise ValueError("retry_max must be >= 0")
        if backoff_s < 0:
            raise ValueError("backoff_s must be >= 0")
        self.retry_max = retry_max
        self.backoff_s = backoff_s
        self.dry_run = dry_run
        self.user_agent = user_agent

    def request(self, req: HttpRequest) -> HttpResponse:
        enforce_url_policy(req.url)
        if self.dry_run:
            return HttpResponse(status=200, headers={"x-dry-run": "1"}, body=b'{"dry_run": true}')

        headers = dict(req.headers or {})
        headers.setdefault("User-Agent", self.user_agent)

        attempt = 0
        last_err: Optional[Exception] = None

        while attempt <= self.retry_max:
            try:
                ureq = urllib.request.Request(
                    url=req.url,
                    data=req.body,
                    method=req.method.upper(),
                    headers=headers,
                )
                with urllib.request.urlopen(ureq, timeout=req.timeout_s) as resp:
                    status = int(getattr(resp, "status", 200))
                    resp_headers = dict(getattr(resp, "headers", {}) or {})
                    body = resp.read() if hasattr(resp, "read") else b""
                    if status >= 400:
                        raise HttpResponseError(status=status, body=body, message="Upstream rejected")
                    return HttpResponse(status=status, headers=resp_headers, body=body)
            except urllib.error.HTTPError as e:
                status = int(getattr(e, "code", 500))
                body = e.read() if hasattr(e, "read") else b""
                # 4xx: normalmente no reintentar (mala request / auth)
                if 400 <= status < 500:
                    raise HttpResponseError(status=status, body=body, message="Client error") from e
                last_err = e
            except urllib.error.URLError as e:
                last_err = e
            except TimeoutError as e:
                last_err = e
            except (ValueError, TypeError) as e:
                last_err = e

            attempt += 1
            if attempt <= self.retry_max:
                time.sleep(self.backoff_s * (2 ** (attempt - 1)))

        if isinstance(last_err, TimeoutError):
            raise HttpTimeoutError("timeout") from last_err
        raise HttpClientError("request failed") from last_err

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, timeout_s: float = 20.0) -> HttpResponse:
        return self.request(HttpRequest(method="GET", url=url, headers=headers or {}, timeout_s=timeout_s))

    def post_json(
        self,
        url: str,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
        timeout_s: float = 20.0,
    ) -> HttpResponse:
        h = dict(headers or {})
        h.setdefault("Content-Type", "application/json; charset=utf-8")
        return self.request(HttpRequest(method="POST", url=url, headers=h, body=_encode_json(payload), timeout_s=timeout_s))
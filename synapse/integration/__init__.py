"""Legacy compatibility exports for synapse.integration."""

from __future__ import annotations

from .http_client import (
    HttpClientError,
    HttpRequest,
    HttpResponse,
    HttpResponseError,
    HttpTimeoutError,
    SimpleHttpClient,
)

__all__ = [
    "SimpleHttpClient",
    "HttpRequest",
    "HttpResponse",
    "HttpClientError",
    "HttpTimeoutError",
    "HttpResponseError",
]

"""Legacy compatibility wrapper for synapse.integration.http_client.

Canonical implementation lives in synapse.integrations.http_client.

Important:
- Singular path preserves historical defaults for legacy callers.
- Plural path remains canonical for new integrations.
"""

from __future__ import annotations

from synapse.integrations.http_client import (
    HttpClientError,
    HttpRequest,
    HttpResponse,
    HttpResponseError,
    HttpTimeoutError,
    SimpleHttpClient as _CanonicalSimpleHttpClient,
)


class SimpleHttpClient(_CanonicalSimpleHttpClient):
    """Legacy wrapper preserving singular-path defaults.

    Historical singular callers expect network-enabled behavior by default,
    so dry_run stays False here unless explicitly overridden.
    """

    def __init__(
        self,
        *,
        retry_max: int = 2,
        backoff_s: float = 0.4,
        dry_run: bool = False,
        user_agent: str = "synapse-http/1.0",
    ):
        super().__init__(
            retry_max=retry_max,
            backoff_s=backoff_s,
            dry_run=dry_run,
            user_agent=user_agent,
        )


__all__ = [
    "SimpleHttpClient",
    "HttpRequest",
    "HttpResponse",
    "HttpClientError",
    "HttpTimeoutError",
    "HttpResponseError",
]

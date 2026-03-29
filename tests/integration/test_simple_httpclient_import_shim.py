from __future__ import annotations

from synapse.integration.http_client import (
    HttpClientError as SingularHttpClientError,
    HttpRequest as SingularHttpRequest,
    HttpResponse as SingularHttpResponse,
    HttpResponseError as SingularHttpResponseError,
    HttpTimeoutError as SingularHttpTimeoutError,
    SimpleHttpClient as SingularSimpleHttpClient,
)
from synapse.integrations.http_client import (
    HttpClientError as PluralHttpClientError,
    HttpRequest as PluralHttpRequest,
    HttpResponse as PluralHttpResponse,
    HttpResponseError as PluralHttpResponseError,
    HttpTimeoutError as PluralHttpTimeoutError,
    SimpleHttpClient as PluralSimpleHttpClient,
)


def test_simple_httpclient_import_shim_preserves_legacy_defaults() -> None:
    singular = SingularSimpleHttpClient()
    plural = PluralSimpleHttpClient()

    assert singular.dry_run is False
    assert plural.dry_run is True

    assert SingularHttpRequest is PluralHttpRequest
    assert SingularHttpResponse is PluralHttpResponse
    assert SingularHttpClientError is PluralHttpClientError
    assert SingularHttpTimeoutError is PluralHttpTimeoutError
    assert SingularHttpResponseError is PluralHttpResponseError

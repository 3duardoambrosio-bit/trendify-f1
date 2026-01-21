# synapse/integration/__init__.py
# Nota: no importamos módulos con CLI aquí (evita warnings de runpy).
from .http_client import (
    SimpleHttpClient,
    HttpRequest,
    HttpResponse,
    HttpClientError,
    HttpTimeoutError,
    HttpResponseError,
)
__all__ = [
    "SimpleHttpClient",
    "HttpRequest",
    "HttpResponse",
    "HttpClientError",
    "HttpTimeoutError",
    "HttpResponseError",
]

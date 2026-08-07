from __future__ import annotations

from pathlib import Path

import pytest

from tools.nogo_ast_resolver import (
    has_call_to,
    has_resolved_network_call,
    scan_source_for_forbidden_strings,
)

# Dominios sensibles (dinero real)
SENSITIVE_DOMAINS = (
    "graph.facebook.com",
    "api.dropi.co",
    "myshopify.com",
)

# Si el archivo importa alguno de estos, asumimos que pasa por un http_client ya enforceado.
SAFE_HTTP_CLIENT_IMPORT_TOKENS = (
    "synapse.integrations.http_client",
    "synapse.integration.http_client",
)

EXCLUDE_SUBSTR = (
    "/tests/",
    "/.git/",
    "/.venv/",
    "/venv/",
    "/.claude/",
    "/runs/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/node_modules/",
)


def _repo_root() -> Path:
    # tests/p0/... -> repo root
    return Path(__file__).resolve().parents[2]


def _norm(p: Path) -> str:
    return str(p).replace("\\", "/")


def _is_sensitive_unguarded_network_source(source: str) -> bool:
    if not scan_source_for_forbidden_strings(source, SENSITIVE_DOMAINS):
        return False
    if any(token in source for token in SAFE_HTTP_CLIENT_IMPORT_TOKENS):
        return False
    return has_resolved_network_call(source) and not has_call_to(
        source,
        "enforce_url_policy",
    )


def test_no_sensitive_network_bypass() -> None:
    """
    FAIL-CLOSED gate:
    Si un archivo NO-test contiene dominios sensibles + usa libs de red
    y NO pasa por http_client y NO llama enforce_url_policy(...), revienta.

    Aceptamos falsos positivos: prefiero seguridad sobre conveniencia.
    """
    root = _repo_root()
    offenders: list[str] = []

    for p in root.rglob("*.py"):
        s = _norm(p)

        if any(x in s for x in EXCLUDE_SUBSTR):
            continue

        # Este archivo define el policy; puede contener dominios pero no hace red.
        if s.endswith("/infra/network_guard.py"):
            continue

        txt = p.read_text(encoding="utf-8", errors="ignore")

        if _is_sensitive_unguarded_network_source(txt):
            offenders.append(s)

    assert offenders == [], (
        "NETWORK_BYPASS_DETECTED (sensitive domains + network libs without guardrail). "
        "Fix: route calls through synapse.*.http_client OR add enforce_url_policy(url). "
        f"offenders_count={len(offenders)} offenders={offenders}"
    )


def test_exact_legacy_urlrequest_alias_is_classified_as_offender() -> None:
    source = """
from urllib import request as urlrequest

URL = "https://graph.facebook.com/v25.0/me"
urlrequest.urlopen(URL)
"""

    assert _is_sensitive_unguarded_network_source(source) is True


@pytest.mark.parametrize(
    "source",
    [
        """
import requests as r
URL = "https://graph.facebook.com/v25.0/me"
""",
        """
import urllib.parse as parse
URL = "https://graph.facebook.com/v25.0/me"
parse.urlparse(URL)
""",
        """
import urllib.error as error
URL = "https://graph.facebook.com/v25.0/me"
error.URLError(URL)
""",
        """
URL = "https://graph.facebook.com/v25.0/me"

class LocalClient:
    def get(self, url):
        return url

    def post(self, url):
        return url

client = LocalClient()
client.get(URL)
client.post(URL)
""",
        '''
URL = "https://graph.facebook.com/v25.0/me"
# from urllib import request as urlrequest
# urlrequest.urlopen(URL)
fixture = "urlrequest.urlopen(URL)"
''',
        """
import importlib
URL = "https://graph.facebook.com/v25.0/me"

def load(module_name):
    module = importlib.import_module(module_name)
    getattr(module, "urlopen")(URL)
""",
        """
URL = "https://graph.facebook.com/v25.0/me"

class LocalTransport:
    def request(self, method, url):
        return method, url

transport = LocalTransport()
transport.request("GET", URL)
""",
        """
from typing import TYPE_CHECKING
URL = "https://graph.facebook.com/v25.0/me"

if TYPE_CHECKING:
    import requests as r
    r.get(URL)
""",
        '''
URL = "https://graph.facebook.com/v25.0/me"
dead_fixture = """
import requests as r
r.get(URL)
"""
''',
    ],
)
def test_non_network_or_unresolved_source_is_not_classified_as_offender(
    source: str,
) -> None:
    assert _is_sensitive_unguarded_network_source(source) is False


def test_guarded_network_boundary_is_not_classified_as_offender() -> None:
    source = """
from urllib import request as urlrequest
from synapse.infra.network_guard import enforce_url_policy

URL = "https://graph.facebook.com/v25.0/me"
enforce_url_policy(URL)
urlrequest.urlopen(URL)
"""

    assert _is_sensitive_unguarded_network_source(source) is False


def test_safe_http_client_boundary_remains_allowed() -> None:
    source = """
import requests
from synapse.integrations.http_client import SimpleHttpClient

URL = "https://graph.facebook.com/v25.0/me"
requests.get(URL)
"""

    assert _is_sensitive_unguarded_network_source(source) is False


def test_network_call_without_sensitive_domain_is_not_a_general_lint_error() -> None:
    source = """
import requests
requests.get("https://example.invalid/health")
"""

    assert _is_sensitive_unguarded_network_source(source) is False

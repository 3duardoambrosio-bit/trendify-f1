from __future__ import annotations

import pytest

from tools.nogo_ast_resolver import (
    scan_source_for_forbidden_strings,
    scan_source_for_network_calls,
)


def _tokens_found(source: str, *tokens: str) -> set[str]:
    return {f.token for f in scan_source_for_forbidden_strings(source, tokens)}


def _network_calls(source: str) -> set[str]:
    return {
        finding.canonical_name
        for finding in scan_source_for_network_calls(source)
    }


def test_resolver_detects_shopify_admin_concatenation_old_text_scan_misses() -> None:
    source = 'channel = "shop" + "ify" + "_admin"'

    assert "shopify_admin" not in source
    assert "shopify_admin" in _tokens_found(source, "shopify_admin")


def test_resolver_detects_meta_access_token_adjacent_literals() -> None:
    source = 'name = "meta" "access" "token"'

    assert "meta_access_token" not in source
    assert "meta_access_token" in _tokens_found(source, "meta_access_token")


def test_resolver_detects_meta_access_token_concatenation() -> None:
    source = 'name = "meta" + "_access" + "_token"'

    assert "meta_access_token" not in source
    assert "meta_access_token" in _tokens_found(source, "meta_access_token")


def test_resolver_detects_live_write_join() -> None:
    source = 'marker = "".join(["LIVE", "_WRITE"])'

    assert "LIVE_WRITE" not in source
    assert "LIVE_WRITE" in _tokens_found(source, "LIVE_WRITE")


def test_resolver_detects_network_module_fstring_with_constant_part() -> None:
    source = 'module_name = f"req{\'\'}uests"'

    assert "requests" not in source
    assert "requests" in _tokens_found(source, "requests")


def test_resolver_detects_assigned_constant_reuse() -> None:
    source = """
TOKEN = "graph." + "facebook" + ".com"
url = TOKEN
"""

    assert "graph.facebook.com" not in source
    assert "graph.facebook.com" in _tokens_found(source, "graph.facebook.com")


def test_resolver_tolerates_bom_artifacts_without_crashing() -> None:
    source = "\ufeffname = \"shop\" + \"ify\" + \"_admin\""

    assert "shopify_admin" in _tokens_found(source, "shopify_admin")


def test_resolver_tolerates_mojibake_bom_artifacts_without_crashing() -> None:
    source = "´╗┐name = \"shop\" + \"ify\" + \"_admin\""

    assert "shopify_admin" in _tokens_found(source, "shopify_admin")


def test_resolver_detects_exact_legacy_urlrequest_alias() -> None:
    source = """
from urllib import request as urlrequest
urlrequest.urlopen(URL)
"""

    assert _network_calls(source) == {"urllib.request.urlopen"}


@pytest.mark.parametrize(
    "source",
    [
        "import urllib.request\nurllib.request.urlopen(URL)",
        "import urllib.request as req\nreq.urlopen(URL)",
        "from urllib import request\nrequest.urlopen(URL)",
        "from urllib.request import urlopen\nurlopen(URL)",
        "from urllib.request import urlopen as open_url\nopen_url(URL)",
    ],
)
def test_resolver_detects_urllib_request_aliases(source: str) -> None:
    assert _network_calls(source) == {"urllib.request.urlopen"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import requests as r\nr.get(URL)", "requests.get"),
        ("import requests as r\nr.post(URL)", "requests.post"),
        ("import requests as r\nr.request('GET', URL)", "requests.request"),
        ("from requests import get as http_get\nhttp_get(URL)", "requests.get"),
    ],
)
def test_resolver_detects_requests_aliases(source: str, expected: str) -> None:
    assert _network_calls(source) == {expected}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import httpx as hx\nhx.get(URL)", "httpx.get"),
        ("import httpx as hx\nhx.post(URL)", "httpx.post"),
        ("import httpx as hx\nhx.request('GET', URL)", "httpx.request"),
        ("from httpx import get as http_get\nhttp_get(URL)", "httpx.get"),
    ],
)
def test_resolver_detects_httpx_aliases(source: str, expected: str) -> None:
    assert _network_calls(source) == {expected}


@pytest.mark.parametrize(
    "source",
    [
        "import aiohttp as ah\nah.request('GET', URL)",
        "from aiohttp import request as aio_request\naio_request('GET', URL)",
    ],
)
def test_resolver_detects_aiohttp_aliases(source: str) -> None:
    assert _network_calls(source) == {"aiohttp.request"}


@pytest.mark.parametrize(
    "source",
    [
        """
module = __import__("urllib.request")
module.request.urlopen(URL)
""",
        """
module = __import__("urllib.request", fromlist=["urlopen"])
module.urlopen(URL)
""",
    ],
)
def test_resolver_detects_constant_dunder_import_call(source: str) -> None:

    assert _network_calls(source) == {"urllib.request.urlopen"}


def test_resolver_detects_constant_importlib_call() -> None:
    source = """
import importlib
module = importlib.import_module("urllib.request")
module.urlopen(URL)
"""

    assert _network_calls(source) == {"urllib.request.urlopen"}


def test_resolver_detects_constant_getattr_call_and_alias() -> None:
    source = """
import urllib.request as req
open_url = getattr(req, "urlopen")
open_url(URL)
"""

    assert _network_calls(source) == {"urllib.request.urlopen"}


@pytest.mark.parametrize(
    "source",
    [
        """
def fetch():
    r.get(URL)

import requests as r
""",
        """
import requests as r

class Client:
    r = LocalClient()

    def fetch(self):
        r.get(URL)
""",
        """
if True:
    import requests as r

r.get(URL)
""",
    ],
)
def test_resolver_uses_deterministic_python_scope_rules(source: str) -> None:
    assert _network_calls(source) == {"requests.get"}


@pytest.mark.parametrize(
    "source",
    [
        "import requests as r",
        "import urllib.parse as parse\nparse.urlparse(URL)",
        "import urllib.error as error\nerror.URLError('offline')",
        """
class LocalClient:
    def get(self, url):
        return url

    def post(self, url):
        return url

client = LocalClient()
client.get(URL)
client.post(URL)
""",
        """
# urlrequest.urlopen("https://graph.facebook.com")
fixture = 'urlrequest.urlopen("https://graph.facebook.com")'
""",
        """
import importlib

def load(module_name):
    module = importlib.import_module(module_name)
    getattr(module, "urlopen")(URL)
""",
        """
def load(module_name):
    module = __import__(module_name)
    module.urlopen(URL)
""",
        """
import requests as r

class LocalClient:
    def get(self, url):
        return url

r = LocalClient()
r.get(URL)
""",
        """
import requests

def fetch(requests):
    requests.get(URL)
""",
        """
import requests as r

def fetch():
    r.get(URL)
    r = LocalClient()
""",
        """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests as r
    r.get(URL)
""",
    ],
)
def test_resolver_avoids_unresolved_or_non_network_false_positives(
    source: str,
) -> None:
    assert _network_calls(source) == set()

from __future__ import annotations

from tools.nogo_ast_resolver import scan_source_for_forbidden_strings


def _tokens_found(source: str, *tokens: str) -> set[str]:
    return {f.token for f in scan_source_for_forbidden_strings(source, tokens)}


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

from __future__ import annotations

from pathlib import Path

from tools.nogo_ast_resolver import has_call_to, scan_source_for_forbidden_strings

# Dominios sensibles (dinero real)
SENSITIVE_DOMAINS = (
    "graph.facebook.com",
    "api.dropi.co",
    "myshopify.com",
)

# Señales de librerías de red (bypass típico)
NETWORK_LIB_TOKENS = (
    "requests",
    "httpx",
    "urllib.request",
    "aiohttp",
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

        sensitive_findings = scan_source_for_forbidden_strings(txt, SENSITIVE_DOMAINS)
        if not sensitive_findings:
            continue

        if any(token in txt for token in SAFE_HTTP_CLIENT_IMPORT_TOKENS):
            continue

        uses_network_lib = bool(scan_source_for_forbidden_strings(txt, NETWORK_LIB_TOKENS))
        has_enforce_call = has_call_to(txt, "enforce_url_policy")

        if uses_network_lib and not has_enforce_call:
            offenders.append(s)

    assert offenders == [], (
        "NETWORK_BYPASS_DETECTED (sensitive domains + network libs without guardrail). "
        "Fix: route calls through synapse.*.http_client OR add enforce_url_policy(url). "
        f"offenders_count={len(offenders)} offenders={offenders}"
    )

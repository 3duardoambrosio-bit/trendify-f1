from __future__ import annotations

from pathlib import Path
import re

# Dominios sensibles (dinero real)
SENSITIVE_DOMAINS = (
    "graph.facebook.com",
    "api.dropi.co",
    "myshopify.com",
)

# Señales de librerías de red (bypass típico)
NETWORK_LIB_RX = (
    r"\brequests\b",
    r"\bhttpx\b",
    r"\burllib\.request\b",
    r"\baiohttp\b",
)

# Si el archivo importa alguno de estos, asumimos que pasa por un http_client ya enforceado.
SAFE_HTTP_CLIENT_IMPORT_RX = (
    r"\bsynapse\.integrations\.http_client\b",
    r"\bsynapse\.integration\.http_client\b",
)

EXCLUDE_SUBSTR = (
    "/tests/",
    "/.git/",
    "/.venv/",
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

        if not any(dom in txt for dom in SENSITIVE_DOMAINS):
            continue

        # Si importa el http_client enforceado, lo consideramos “ruta segura”.
        if any(re.search(rx, txt) for rx in SAFE_HTTP_CLIENT_IMPORT_RX):
            continue

        uses_network_lib = any(re.search(rx, txt) for rx in NETWORK_LIB_RX)
        has_enforce_call = "enforce_url_policy(" in txt

        if uses_network_lib and not has_enforce_call:
            offenders.append(s)

    assert offenders == [], (
        "NETWORK_BYPASS_DETECTED (sensitive domains + network libs without guardrail). "
        "Fix: route calls through synapse.*.http_client OR add enforce_url_policy(url). "
        f"offenders_count={len(offenders)} offenders={offenders}"
    )
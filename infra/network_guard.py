from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse

from infra.feature_flags import FeatureFlags
from infra.log_sanitizer import INVALID_URL_REDACTED, redact_url


# Dominios dinero real que deben estar gated por flags.
_DOMAIN_TO_SYSTEM: Dict[str, str] = {
    "graph.facebook.com": "meta",
    "api.dropi.co": "dropi",
    "myshopify.com": "shopify",
}
_INVALID_URL_REASON = (
    f"NETWORK_BLOCKED_INVALID_URL: url={INVALID_URL_REDACTED}"
)


def _host_of(url: str) -> str:
    u = urlparse(url)
    host = (u.netloc or "").lower().strip()
    # userinfo@host:port -> host
    if "@" in host:
        host = host.split("@", 1)[1]
    # host:port -> host
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def classify_system(url: str) -> Optional[str]:
    """
    Devuelve el sistema ("meta"/"dropi"/"shopify") si el URL es de un dominio sensible.
    """
    safe_url = redact_url(url)
    if safe_url == INVALID_URL_REDACTED:
        return None
    try:
        host = _host_of(safe_url)
    except Exception:
        return None
    if not host:
        return None
    for dom, sys in _DOMAIN_TO_SYSTEM.items():
        if host == dom or host.endswith("." + dom):
            return sys
    return None


@dataclass(frozen=True)
class NetworkDecision:
    allowed: bool
    system: Optional[str] = None
    reason: Optional[str] = None


def decide_url(url: str) -> NetworkDecision:
    safe_url = redact_url(url)
    if safe_url == INVALID_URL_REDACTED:
        return NetworkDecision(False, None, _INVALID_URL_REASON)

    try:
        sys = classify_system(safe_url)
    except Exception:
        return NetworkDecision(False, None, _INVALID_URL_REASON)

    if sys is None:
        return NetworkDecision(True, None, None)

    flags = FeatureFlags.from_env()
    if flags.allow_network(sys):
        return NetworkDecision(True, sys, None)

    return NetworkDecision(
        False,
        sys,
        f"NETWORK_BLOCKED_BY_FLAGS: system={sys} url={safe_url} "
        f"(set SYNAPSE_DRY_RUN=0 and SYNAPSE_LIVE_{sys.upper()}=1)",
    )


def enforce_url_policy(url: str) -> None:
    """
    Enforce fail-closed: si NO está permitido, lanza RuntimeError.
    """
    d = decide_url(url)
    if d.allowed:
        return
    raise RuntimeError(d.reason or "NETWORK_BLOCKED_BY_FLAGS")

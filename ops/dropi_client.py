from __future__ import annotations

from infra.network_guard import enforce_url_policy

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
READ_ONLY_POST_PATHS = frozenset({
    "/products/index",
})


@dataclass
class DropiClientConfig:
    base_url: str
    integration_key: str
    timeout_s: int = 30
    rate_limit_s: float = 0.25
    user_agent: str = "SYNAPSE-MVS/1.0"


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in TRUE_ENV_VALUES


def _normalize_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        raise RuntimeError("Dropi path is required")
    return value if value.startswith("/") else "/" + value


def _require_live_dropi_network(method: str, path: str) -> None:
    normalized = _normalize_path(path)
    if not _env_flag("SYNAPSE_LIVE_DROPI"):
        raise RuntimeError(
            f"Dropi live network blocked for {method} {normalized}: "
            "SYNAPSE_LIVE_DROPI is not enabled"
        )
    if _env_flag("SYNAPSE_DRY_RUN"):
        raise RuntimeError(
            f"Dropi live network blocked for {method} {normalized}: "
            "SYNAPSE_DRY_RUN is enabled"
        )


def _require_live_dropi_write(path: str) -> None:
    normalized = _normalize_path(path)
    _require_live_dropi_network("POST_WRITE", normalized)
    if not _env_flag("SYNAPSE_LIVE_WRITE"):
        raise RuntimeError(
            f"Dropi live write blocked for {normalized}: "
            "SYNAPSE_LIVE_WRITE is not enabled"
        )
    if not _env_flag("SYNAPSE_DROPI_WRITE_APPROVED"):
        raise RuntimeError(
            f"Dropi live write blocked for {normalized}: "
            "SYNAPSE_DROPI_WRITE_APPROVED is not enabled"
        )


class DropiClient:
    """Minimal HTTP client for Dropi Integrations API.

    Safety contract:
    - live network is blocked by default;
    - read-only POST endpoints must use post_readonly() and be allowlisted;
    - generic post() is treated as a write path and requires explicit write approval.
    """

    def __init__(self, cfg: DropiClientConfig) -> None:
        self.cfg = cfg.rstrip_slashes()
        self._last_call = 0.0

    def _throttle(self) -> None:
        gap = self.cfg.rate_limit_s
        if gap <= 0:
            return
        now = time.time()
        wait = (self._last_call + gap) - now
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _headers(self) -> Dict[str, str]:
        # Dual key header for compatibility.
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.cfg.user_agent,
            "dropi-integration-key": self.cfg.integration_key,
            "dropi-integracion-key": self.cfg.integration_key,
        }

    def _url(self, path: str) -> str:
        base = self.cfg.base_url.rstrip("/")
        path2 = _normalize_path(path)
        return base + path2

    def get(self, path: str) -> Dict[str, Any]:
        normalized = _normalize_path(path)
        _require_live_dropi_network("GET", normalized)
        self._throttle()
        enforce_url_policy(self._url(normalized))
        req = urllib.request.Request(self._url(normalized), headers=self._headers(), method="GET")
        return self._do(req)

    def post_readonly(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_path(path)
        if normalized not in READ_ONLY_POST_PATHS:
            raise RuntimeError(f"Dropi read-only POST path is not allowlisted: {normalized}")
        _require_live_dropi_network("POST_READONLY", normalized)
        return self._post_request(normalized, body)

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_path(path)
        _require_live_dropi_write(normalized)
        return self._post_request(normalized, body)

    def _post_request(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._throttle()
        data = json.dumps(body).encode("utf-8")
        enforce_url_policy(self._url(path))
        req = urllib.request.Request(self._url(path), data=data, headers=self._headers(), method="POST")
        return self._do(req)

    def _do(self, req: urllib.request.Request) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Dropi HTTPError {e.code}: {raw[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Dropi URLError: {e}")
        except Exception as e:
            raise RuntimeError(f"Dropi error: {e}")


def _strip(s: str) -> str:
    return s.strip() if isinstance(s, str) else s


def _cfg_from_env() -> DropiClientConfig:
    key = os.getenv("DROPI_INTEGRATION_KEY") or os.getenv("DROPi_INTEGRATION_KEY") or ""
    if not key:
        raise RuntimeError("Missing env var: DROPI_INTEGRATION_KEY")
    base = os.getenv("DROPI_BASE_URL", "https://api.dropi.co/integrations")
    timeout_s = int(os.getenv("DROPI_TIMEOUT_S", "30"))
    rate_limit_s = float(os.getenv("DROPI_RATE_LIMIT_S", "0.25"))
    return DropiClientConfig(base_url=base, integration_key=key, timeout_s=timeout_s, rate_limit_s=rate_limit_s)


# small helper to make config resilient
def _rstrip_slashes(self: DropiClientConfig) -> DropiClientConfig:
    self.base_url = self.base_url.rstrip("/")
    return self


DropiClientConfig.rstrip_slashes = _rstrip_slashes  # type: ignore[attr-defined]

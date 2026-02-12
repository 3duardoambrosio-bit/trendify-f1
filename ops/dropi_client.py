from __future__ import annotations
from infra.network_guard import enforce_url_policy

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import urllib.request
import urllib.error

@dataclass
class DropiClientConfig:
    base_url: str
    integration_key: str
    timeout_s: int = 30
    rate_limit_s: float = 0.25
    user_agent: str = "SYNAPSE-MVS/1.0"

class DropiClient:
    """Minimal HTTP client for Dropi Integrations API.
    Sends both `dropi-integration-key` and the frequently seen typo `dropi-integracion-key`.
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
        path2 = path if path.startswith("/") else "/" + path
        return base + path2

    def get(self, path: str) -> Dict[str, Any]:
        self._throttle()
        enforce_url_policy(self._url(path))
        req = urllib.request.Request(self._url(path), headers=self._headers(), method="GET")
        return self._do(req)

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
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

DropiClientConfig.rstrip_slashes = _rstrip_slashes  # type: ignore
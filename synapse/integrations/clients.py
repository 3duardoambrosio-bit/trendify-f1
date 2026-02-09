from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from synapse.integrations.config import (
    DropiConfig,
    MetaConfig,
    ShopifyConfig,
    load_dropi_config,
    load_meta_config,
    load_shopify_config,
)
from synapse.integrations.errors import INTEGRATION_NOT_CONFIGURED, IntegrationError


class ShopifyClient(Protocol):
    def health(self) -> Dict[str, Any]: ...
    def upsert_product(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...


class DropiClient(Protocol):
    def health(self) -> Dict[str, Any]: ...
    def forward_order(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...


class MetaClient(Protocol):
    def health(self) -> Dict[str, Any]: ...
    def send_capi_event(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...


@dataclass
class _DisabledClient:
    name: str
    reason: IntegrationError = INTEGRATION_NOT_CONFIGURED

    def health(self) -> Dict[str, Any]:
        return {"ok": False, "client": self.name, "error": str(self.reason)}

    def _disabled(self) -> Dict[str, Any]:
        return {"ok": False, "client": self.name, "error": str(self.reason)}


@dataclass
class DisabledShopify(_DisabledClient):
    def upsert_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._disabled()


@dataclass
class DisabledDropi(_DisabledClient):
    def forward_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._disabled()


@dataclass
class DisabledMeta(_DisabledClient):
    def send_capi_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._disabled()


def build_shopify_client(cfg: Optional[ShopifyConfig] = None) -> ShopifyClient:
    cfg = cfg or load_shopify_config()
    if not cfg.enabled or not cfg.shop_domain or not cfg.access_token:
        return DisabledShopify(name="shopify")
    return DisabledShopify(
        name="shopify",
        reason=IntegrationError("NOT_IMPLEMENTED", "Shopify real client not wired yet."),
    )


def build_dropi_client(cfg: Optional[DropiConfig] = None) -> DropiClient:
    cfg = cfg or load_dropi_config()
    if not cfg.enabled or not cfg.api_base or not cfg.api_key:
        return DisabledDropi(name="dropi")
    return DisabledDropi(
        name="dropi",
        reason=IntegrationError("NOT_IMPLEMENTED", "Dropi real client not wired yet."),
    )


def build_meta_client(cfg: Optional[MetaConfig] = None) -> MetaClient:
    cfg = cfg or load_meta_config()
    if not cfg.enabled or not cfg.pixel_id or not cfg.access_token:
        return DisabledMeta(name="meta")
    return DisabledMeta(
        name="meta",
        reason=IntegrationError("NOT_IMPLEMENTED", "Meta real client not wired yet."),
    )